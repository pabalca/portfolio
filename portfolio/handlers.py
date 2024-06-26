import click
import requests
import time
from datetime import datetime
import yfinance as yf

from portfolio import app
from portfolio.models import (
    User,
    Ticker,
    Asset,
    Performance,
    Snapshot,
    TelegramAlert,
    db,
)
from portfolio.utils import update_prices, send_message


@app.shell_context_processor
def make_shell_context():
    return dict(
        db=db,
        Ticker=Ticker,
        Asset=Asset,
        Performance=Performance,
        Snapshot=Snapshot,
        User=User,
        TelegramAlert=TelegramAlert,
    )


@app.cli.command()
@click.option("--drop", is_flag=True, help="Create after drop.")
def initdb(drop):
    if drop:
        db.drop_all()
    db.create_all()
    click.echo("Initialized database.")

    # BaseCurrency
    t = Ticker(
        description="EUR",
        token="BaseCurrency",
        price=1,
        previous_close_price=1,
        currency="eur",
    )
    db.session.add(t)

    dataset = [
        ("USD", "EUR=X", "eur"),
        ("Gold", "GC=F", "usd"),
        ("Meta", "META", "usd"),
        ("Coinbase", "COIN", "usd"),
        ("Mara", "MARA", "usd"),
        ("Hut8", "HUT", "usd"),
        ("Core", "CORZQ", "usd"),
        ("Google", "GOOGL", "usd"),
        ("Tesla", "TSLA", "usd"),
        ("Index", "VWCE.DE", "eur"),
        ("Bitcoin", "BTC-USD", "usd"),
        ("Ethereum", "ETH-USD", "usd"),
    ]
    for d in dataset:
        t = Ticker(description=d[0], token=d[1], currency=d[2])
        db.session.add(t)
        click.echo(f"Ticker <{d[0]} added")
    db.session.commit()


@app.cli.command()
def scrape():
    tickers = Ticker.query.filter(Ticker.token != "BaseCurrency").all()

    for ticker in tickers:
        if ticker.token == "BaseCurrency":
            click.echo("skip base currency")
            continue

        yticker = yf.Ticker(ticker.token).fast_info
        market_price = yticker["last_price"]
        previous_close_price = yticker["previous_close"]

        ticker.price = market_price
        ticker.previous_close_price = previous_close_price
        ticker.created_at = datetime.utcnow()
        click.echo(f"{ticker.description} = {ticker.price} updated")

    db.session.commit()


def calculate_performance():
    pp = list()

    user_ids = [user.id for user in User.query.all()]

    for user_id in user_ids:
        assets = Asset.query.filter(Asset.user_id == user_id).all()
        if not assets:
            continue

        # TODO: calculate pnl in database
        value = 0
        pnl = 0
        for asset in assets:
            value += asset.value
            pnl += asset.pnl
        change = 100 * ((value + pnl) / value - 1)

        p = Performance(value=value, pnl=pnl, change=change, user_id=user_id)
        pp.append(p)
    return pp


@app.cli.command()
def performance():

    pp = calculate_performance()
    for p in pp:
        db.session.add(p)
        click.echo(f"<Performance> {p.user_id} {p.created_at} = {p.value}")

    db.session.commit()


@app.cli.command()
def alert_move():
    """
    Send report if portfolio changed more than threshold in a day
    """

    user_ids = [user.id for user in User.query.all()]
    for user_id in user_ids:
        tg = (
            TelegramAlert.query.filter(TelegramAlert.enabled == True)
            .filter(TelegramAlert.user_id == user_id)
            .first()
        )

        if not tg:
            continue

        # get last performance report
        pp = calculate_performance()
        for pf in pp:
            if pf.user_id == user_id:

                plus_symbol = "+" if pf.pnl >= 0 else ""
                message = "\n".join(
                    (
                        f"`Portfolio moved {'{0:0.2f}'.format(pf.change)}%`",
                        f"PNL       *{plus_symbol}{'{:,.0f}'.format(pf.pnl)}*",
                        f"VALUE   *{'{:,.0f}'.format(pf.value)}*",
                    )
                )
                click.echo(f"Sending report for {user_id}")
                result = send_message(tg.api_url, tg.api_token, tg.api_chat, message)
                click.echo(result)


@app.cli.command()
def alert_target():
    """
    Send alert if asset percentage is over target% + threshold
    """

    user_ids = [user.id for user in User.query.all()]
    for user_id in user_ids:
        tg = (
            TelegramAlert.query.filter(TelegramAlert.enabled == True)
            .filter(TelegramAlert.user_id == user_id)
            .first()
        )

        if not tg:
            continue

        # get last performance report
        assets = (
            Asset.query.filter(Asset.user_id == user_id)
            .filter(Asset.sector != "cash")
            .order_by(Asset.value.desc())
            .all()
        )

        message = ""

        for asset in assets:
            # skip assets that are less than 3%
            if asset.percentage <=0.03:
                continue

            if 100*asset.percentage >= 1.1 * asset.target:
                message += f"`{asset.ticker.description}` is *{'{0:0.2f}'.format(100*asset.percentage)}%*  target={asset.target} threshold={'{0:0.2f}'.format(1.1*asset.target)}%\n"
                click.echo(f"{asset.ticker.description} is {'{0:0.2f}'.format(100*asset.percentage)}%  target={asset.target} user_id={user_id} threshold={'{0:0.2f}'.format(1.1*asset.target)}% ")
            elif 100*asset.percentage <= 0.9 * asset.target:
                message += f"`{asset.ticker.description}` is *{'{0:0.2f}'.format(100*asset.percentage)}%*  target={asset.target} threshold={'{0:0.2f}'.format(0.9*asset.target)}%\n"
                click.echo(f"{asset.ticker.description} is {'{0:0.2f}'.format(100*asset.percentage)}%  target={asset.target} user_id={user_id}")

        result = send_message(tg.api_url, tg.api_token, tg.api_chat, message)
        click.echo(result)


@app.cli.command()
def save_snapshot():
    assets = Asset.query.all()
    for asset in assets:
        s = Snapshot(
            ticker_token=asset.ticker.token,
            ticker_name=asset.ticker.description,
            ticker_price=asset.ticker.price,
            shares=asset.shares,
            sector=asset.sector,
            value=asset.value,
            user_id=asset.user_id,
        )
        db.session.add(s)
    db.session.commit()
