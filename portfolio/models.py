import uuid
from datetime import datetime
import pyotp

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.sql import case


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


class Asset(db.Model):
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String, db.ForeignKey(User.id))
    ticker_id = db.Column(db.String, db.ForeignKey(Ticker.id))
    ticker = db.relationship(Ticker, backref="ticker")
    ticker_currency = association_proxy(
        "ticker", "currency"
    )  # used for query in value.expression
    shares = db.Column(db.Float)
    target = db.Column(db.Float, default=0)
    sector = db.Column(db.String)
    buy_price = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Asset> {self.ticker} {self.shares}"

    @property
    def percentage(self):
        total = (
            db.session.query(Asset.user_id, db.func.sum(Asset.value).label("value"))
            .filter(Asset.user_id == self.user_id)
            .first()
            .value
        )
        return self.value / total

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

    @property
    def unrealized_pnl(self):
        return self.value * (1 - 1/(1+self.unrealized_percentage))

    @property
    def pnl(self):
        return self.value * self.ticker.price_change / 100

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
