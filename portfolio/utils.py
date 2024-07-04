from datetime import datetime
import yfinance as yf
import requests
import json
from concurrent.futures import ThreadPoolExecutor

from portfolio.models import Ticker, Asset, Performance, Snapshot, db

import logging

logging.basicConfig(level=logging.INFO)


def update_tickers(ticker):
    try:

        yticker = yf.Ticker(ticker.token).fast_info
        market_price = yticker['last_price']
        previous_close_price = yticker['previous_close']

        ticker.price = market_price
        ticker.previous_close_price = previous_close_price
        ticker.created_at = datetime.utcnow()

    except Exception as exc:
        logging.error(f"Failed to update tickers: {exc}")


def update_prices():
    tickers = Ticker.query.filter(Ticker.token != "BaseCurrency").all()
    # ticker_tokens = [ticker.token for ticker in tickers]

    # ticker_chunks = [tickers[i:i + 100] for i in range(0, len(tickers), 3)]  # Adjust chunk size as needed

    with ThreadPoolExecutor(max_workers=5) as executor:  # Adjust max_workers as needed
        futures = [executor.submit(update_tickers, ticker) for ticker in tickers]

        for future in futures:
            try:
                future.result()
            except Exception as exc:
                logging.error(f"Exception occurred: {exc}")

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
