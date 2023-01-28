import click
import requests
import time
from datetime import datetime
import yfinance as yf

from portfolio import app
from portfolio.models import User, Ticker, Asset, Performance, Snapshot, db
from portfolio.utils import update_prices


@app.shell_context_processor
def make_shell_context():
    return dict(
        db=db,
        Ticker=Ticker,
        Asset=Asset,
        Performance=Performance,
        Snapshot=Snapshot,
        User=User,
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
        ("All-World", "VWCE.DE", "eur"),
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

        yticker = yf.Ticker(ticker.token).basic_info
        market_price = yticker["last_price"]
        previous_close_price = yticker["previous_close"]

        ticker.price = market_price
        ticker.previous_close_price = previous_close_price
        click.echo(f"{ticker.description} = {ticker.price} updated")

    db.session.commit()


@app.cli.command()
def performance():

    user_ids = [ user.id for user in User.query.all()]

    for user_id in user_ids:
        assets = Asset.query.filter(Asset.user_id == user_id).all()

        # TODO: calculate pnl in database
        value = 0
        pnl = 0
        for asset in assets:
            value += asset.value
            pnl += asset.pnl
        change = 100 * ((value + pnl) / value - 1)

        p = Performance(
            value=value,
            pnl=pnl,
            change=change,
            user_id=user_id
        )
        db.session.add(p)

    db.session.commit()
    click.echo(f"<Performance> {p.user_id} {p.created_at} = {p.value}")


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
