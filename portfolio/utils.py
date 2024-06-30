from datetime import datetime
import yfinance as yf
import requests
import json
from concurrent.futures import ThreadPoolExecutor

from portfolio.models import Ticker, Asset, Performance, Snapshot, db


def update_ticker(ticker):
    if ticker.token == "BaseCurrency":
        # click.echo("skip base currency")
        return

    yticker = yf.Ticker(ticker.token).fast_info
    market_price = yticker['last_price']
    previous_close_price = yticker['previous_close']

    ticker.price = market_price
    ticker.previous_close_price = previous_close_price
    ticker.created_at = datetime.utcnow()

    # click.echo(f"{ticker.description} = {ticker.price} updated")

# Function to update prices using multithreading
def update_prices():
    tickers = Ticker.query.filter(Ticker.token != "BaseCurrency").all()

    with ThreadPoolExecutor(max_workers=10) as executor:  # Adjust max_workers as needed
        futures = [executor.submit(update_ticker, ticker) for ticker in tickers]

        for future in futures:
            try:
                future.result()  # Wait for completion and handle exceptions if any
            except Exception as exc:
                # click.echo(f"Exception occurred: {exc}")
                pass

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
