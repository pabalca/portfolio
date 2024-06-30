import uuid
from datetime import datetime
import pyotp
import numpy as np
import pandas as pd

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.sql import case
from sqlalchemy import extract



db = SQLAlchemy()


def generate_uuid():
    return str(uuid.uuid4())


def usd_rate():
    return Ticker.query.filter(Ticker.description == "USD").first().price


def generate_secret():
    return pyotp.random_base32()


class User(db.Model):
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    secret = db.Column(db.String, default=generate_secret)

    def __repr__(self):
        return f"<User> {self.id}"

    def verify_password(self, pwd):
        return pyotp.TOTP(self.secret).verify(pwd)

    @property
    def qr(self):
        return pyotp.TOTP(self.secret).provisioning_uri(
            name="pabs'portfolio", issuer_name="webapp"
        )


class Ticker(db.Model):
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    description = db.Column(db.String)
    token = db.Column(db.String)
    price = db.Column(db.Float)
    previous_close_price = db.Column(db.Float)
    currency = db.Column(db.String)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Ticker> {self.token} {self.price}"

    def __init__(
        self, description, token, currency, price=None, previous_close_price=None
    ):
        self.description = description
        self.token = token
        self.currency = currency
        if not price or not previous_close_price:
            import yfinance as yf

            yticker = yf.Ticker(token).fast_info
            self.price = yticker["last_price"]
            self.previous_close_price = yticker["previous_close"]
        else:
            self.price = price
            self.previous_close_price = previous_close_price

    @property
    def price_change(self):
        return 100 * (self.price / self.previous_close_price - 1)


class Wallet(db.Model):
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String, db.ForeignKey(User.id))
    name = db.Column(db.String)
    target = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='wallets')

    def __repr__(self):
        return f"<Wallet> {self.name} {self.target}"


class Asset(db.Model):
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String, db.ForeignKey(User.id))
    ticker_id = db.Column(db.String, db.ForeignKey(Ticker.id))
    ticker = db.relationship(Ticker, backref="ticker")

    wallet_id = db.Column(db.String, db.ForeignKey(Wallet.id))
    wallet = db.relationship(Wallet, backref="assets")

    ticker_currency = association_proxy(
        "ticker", "currency"
    )  # used for query in value.expression
    shares = db.Column(db.Float)
    target = db.Column(db.Float, default=0)
    sector = db.Column(db.String)
    buy_price = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


    user = db.relationship('User', backref='assets')



    def __repr__(self):
        return f"<Asset> {self.ticker} {self.shares}"

    @hybrid_property
    def value(self):
        if self.ticker.currency == "usd":
            return self.shares * self.ticker.price * usd_rate()
        else:
            return self.shares * self.ticker.price

    @value.expression
    def value(cls):
        ticker_price = (
            db.select(Ticker.price).where(cls.ticker_id == Ticker.id).as_scalar()
        )

        return case(
            (cls.ticker_currency == "usd", cls.shares * ticker_price * usd_rate()),
            else_=cls.shares * ticker_price,
        )

    @hybrid_property
    def pnl_today(self):
        return self.value * self.ticker.price_change / 100

    @pnl_today.expression
    def pnl_today(cls):
        ticker_price = (
            db.select(Ticker.price).where(cls.ticker_id == Ticker.id).as_scalar()
        )
        ticker_price_previous = (
            db.select(Ticker.previous_close_price).where(cls.ticker_id == Ticker.id).as_scalar()
        )
        ticker_price_change = 100 * (ticker_price / ticker_price_previous - 1)
        return cls.value * ticker_price_change / 100

    @property
    def unrealized_percentage(self):
        return (self.ticker.price - self.buy_price) / self.buy_price

    @hybrid_property
    def unrealized_pnl(self):
        unr_per = (self.ticker.price - self.buy_price) / self.buy_price
        return self.value * (1 - 1/(1+unr_per))

    @unrealized_pnl.expression
    def unrealized_pnl(cls):
        ticker_price = (
            db.select(Ticker.price).where(cls.ticker_id == Ticker.id).as_scalar()
        )

        unr_per = (ticker_price - cls.buy_price) / cls.buy_price
        return cls.value * (1 - 1 / (1 + unr_per))


    @property
    def percentage(self):
        total = (
            db.session.query(Asset.user_id, db.func.sum(Asset.value).label("total"))
            .filter(Asset.user_id == self.user_id)
            .filter(Asset.sector == self.sector) # filter by sector, portfolio of portfolios
            .first()
            .total
        )
        return 100 * self.value / total

    @property
    def pnl(self):
        return self.value * self.ticker.price_change / 100
    
    def calculate_deltas(self, portfolio_value):
        self.delta_value = self.target / 100 * portfolio_value - self.value
        self.delta_value_shares = self.delta_value / (self.value / self.shares)
        self.final_value = self.target / 100 * portfolio_value


# portfolio stats over time
class Performance(db.Model):
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String, db.ForeignKey(User.id))
    sector = db.Column(db.String)
    value = db.Column(db.Float)
    pnl = db.Column(db.Float)
    change = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Performance> {self.created_at} =  {self.pnl}"

    @hybrid_property 
    def performance_day(self):
        return self.created_at.strftime("%Y-%m-%d")


# what portfolio did I have in a specific date?
class Snapshot(db.Model):
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String, db.ForeignKey(User.id))
    ticker_token = db.Column(db.String)
    ticker_name = db.Column(db.String)
    ticker_price = db.Column(db.String)
    shares = db.Column(db.Float)
    sector = db.Column(db.String)
    value = db.Column(db.String)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Snapshot> {self.ticker_name} {self.shares} {self.created_at}"


class TelegramAlert(db.Model):
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String, db.ForeignKey(User.id))
    api_url = db.Column(db.String, default="https://api.telegram.org/")
    api_token = db.Column(db.String)
    api_chat = db.Column(db.String)
    enabled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<TelegramAlert {self.user_id} = {self.enabled}"


class Portfolio:
    def __init__(self, assets):
        self.assets = assets
        self._history_cache = None

    @property
    def value(self):
        return sum(asset.value for asset in self.assets)

    @property
    def pnl_today(self):
        return sum(asset.pnl_today for asset in self.assets)

    @property
    def change(self):
        total_value = self.value
        return (100 * self.pnl_today / total_value) if total_value != 0 else 0

    @property
    def total_target(self):
        return sum(asset.target for asset in self.assets)

    @property
    def unrealized_pnl(self):
        return sum(asset.unrealized_pnl for asset in self.assets)

    def calculate_asset_deltas(self):
        portfolio_value = self.value
        for asset in self.assets:
            asset.calculate_deltas(portfolio_value)

    @property
    def history(self):
        if self._history_cache is None:
            stats = (
                Performance.query.filter(Performance.user_id == self.assets[0].user_id)
                .filter(extract("year", Performance.created_at) == 2024)
                .group_by(
                    extract("year", Performance.created_at),
                    extract("month", Performance.created_at),
                    extract("day", Performance.created_at),
                )
                .order_by(Performance.created_at.asc())
                .all()
            )
            stats_now = Performance(
                user_id=self.assets[0].user_id,
                value=self.value,
                pnl=self.pnl_today,
                change=self.change,
                created_at=datetime.utcnow()
            )
            stats.append(stats_now)

            # add rolling volatility to history
            data = {
                'value': [stat.value for stat in stats],
                'pnl': [stat.pnl for stat in stats],
                'created_at': [stat.created_at for stat in stats]
            }
            df = pd.DataFrame(data)
            df['move'] = df['pnl'] / df['value']

            # Calculate rolling average of move over a 30-day window
            df['rolling_avg_90d'] = df['move'].abs().rolling(window=90, min_periods=1).mean()
            df['rolling_avg_30d'] = df['move'].abs().rolling(window=30, min_periods=1).mean()
            df['rolling_avg_7d'] = df['move'].abs().rolling(window=7, min_periods=1).mean()

            # Map the calculated volatilities back to the Performance objects
            for stat, row in zip(stats, df.itertuples(index=False)):
                stat.vol_90d = 100 * row.rolling_avg_90d
                stat.vol_30d = 100 * row.rolling_avg_30d
                stat.vol_7d = 100 * row.rolling_avg_7d

            self._history_cache = stats
        return self._history_cache

    @property
    def ytd(self):
        stats = self.history
        start_value = stats[0].value
        return {
            "value": self.value - start_value,
            "change": 100 * (self.value - start_value) / start_value
        }

    @property
    def pnl(self):
        stats = self.history
        return {
            "ytd": {
                "value": self.value - stats[0].value,
                "change": 100 * (self.value - stats[0].value) / stats[0].value
            },
            "yesterday": {
                "value": self.value - stats[-2].value, # last value is now, so yesterday is -2
                "change": 100 * (self.value - stats[-2].value) / stats[-2].value
            },
            "last_week": {
                "value": self.value - stats[-8].value,
                "change": 100 * (self.value - stats[-8].value) / stats[-8].value
            },
            "last_month": {
                "value": self.value - stats[-31].value,
                "change": 100 * (self.value - stats[-31].value) / stats[-31].value
            },
            "last_quarter": {
                "value": self.value - stats[-91].value,
                "change": 100 * (self.value - stats[-91].value) / stats[-91].value
            }
        }

    @property
    def ath(self):
        stats = self.history
        ath_portfolio = max([stat.value for stat in stats])
        ath_down_value = (self.value - ath_portfolio)
        ath_down_change = 100*ath_down_value/ath_portfolio
        return {
            "value": ath_portfolio,
            "change": ath_down_change,
            "distance": ath_down_value,
        }

    @property
    def drawdown(self):
        # max drawdown
        stats = self.history
        vals = [stat.value for stat in stats]
        i = np.argmax(np.maximum.accumulate(vals) - vals) # end of the period
        j = np.argmax(vals[:i]) # start of period
        return {
            # "start": stats[j].created_at,
            # "end": stats[i].created_at,
            # "start_value": stats[j].value,
            # "end_value": stats[i].value,
            "value": stats[i].value - stats[j].value,
            "change": 100 * (stats[i].value - stats[j].value) / stats[j].value,
        }

    @property
    def volatility(self):
        stats = self.history

        # Create a DataFrame from stats
        data = {
            'value': [stat.value for stat in stats],
            'pnl': [stat.pnl for stat in stats],
            'created_at': [stat.created_at for stat in stats]
        }
        df = pd.DataFrame(data)
        df['move'] = df['pnl'] / df['value']

        # Calculate rolling average of move over a 30-day window
        df['rolling_avg_90d'] = df['move'].abs().rolling(window=90, min_periods=1).mean()
        df['rolling_avg_30d'] = df['move'].abs().rolling(window=30, min_periods=1).mean()
        df['rolling_avg_7d'] = df['move'].abs().rolling(window=7, min_periods=1).mean()
        df['rolling_avg_ytd'] = df['move'].abs().mean()


        #df['annualized_vol_30d'] = df['rolling_avg_30d'] * np.sqrt(365)

        latest_volatility = df.iloc[-1]

        return {
            "weekly": {
                "value": self.value * latest_volatility['rolling_avg_7d'],
                "change": 100 * latest_volatility['rolling_avg_7d']
            },
            "monthly": {
                "value": self.value * latest_volatility['rolling_avg_30d'],
                "change": 100 * latest_volatility['rolling_avg_30d']
            },
            "quarterly": {
                "value": self.value * latest_volatility['rolling_avg_90d'],
                "change": 100 * latest_volatility['rolling_avg_90d']
            },
            "ytd": {
                "value": self.value * latest_volatility['rolling_avg_ytd'],
                "change": 100 * latest_volatility['rolling_avg_ytd']
            }
        }

    @property
    def sharpe_ratio(self):
        stats = self.history
        start_value = stats[0].value

        rf_rate = 0.05  # Example: Risk-free rate assumed to be 2%

        # Calculate excess return
        excess_return = (self.value - start_value) / start_value

        # Calculate standard deviation of excess return
        std_excess_return = np.std([((stat.value - start_value) / start_value) for stat in stats])

        # Calculate Sharpe ratio
        if std_excess_return != 0:
            sharpe_ratio = (excess_return - rf_rate) / std_excess_return
        else:
            sharpe_ratio = 0  # Handle division by zero scenario

        return sharpe_ratio