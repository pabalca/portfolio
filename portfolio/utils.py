from datetime import datetime
import yfinance as yf
import requests
import json

from portfolio.models import Ticker, Asset, Performance, Snapshot, db


def update_prices():
    tickers = Ticker.query.filter(Ticker.token != "BaseCurrency").all()

    for ticker in tickers:
        if ticker.token == "BaseCurrency":
            click.echo("skip base currency")
            continue

        yticker = yf.Ticker(ticker.token).fast_info
        market_price = yticker['last_price']
        previous_close_price = yticker['previous_close']

        ticker.price = market_price
        ticker.previous_close_price = previous_close_price
        ticker.created_at = datetime.utcnow()

    db.session.commit()


def send_message(api, token, chat_id, message):
    try:
        r = requests.post(
            api + token + "/sendMessage",
            params={"chat_id": chat_id, "parse_mode": "Markdown", "text": message},
        )
        if r.json()["ok"]:
            return "All good"
        else:
            return "Alert sent but received error."
    except Exception as e:
        return f"Error sending alert. Exception {e}"
