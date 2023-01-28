import yfinance as yf

from portfolio.models import Ticker, Asset, Performance, Snapshot, db


def update_prices():
    tickers = Ticker.query.filter(Ticker.token != "BaseCurrency").all()

    for ticker in tickers:
        if ticker.token == "BaseCurrency":
            click.echo("skip base currency")
            continue

        yticker = yf.Ticker(ticker.token).basic_info
        market_price = yticker['last_price']
        previous_close_price = yticker['previous_close']

        ticker.price = market_price
        ticker.previous_close_price = previous_close_price

    db.session.commit()
