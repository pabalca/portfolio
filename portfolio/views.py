from datetime import datetime, timedelta
from flask import abort, flash, redirect, render_template, session, url_for, request
from sqlalchemy import func, extract

from portfolio import app
from portfolio.models import (
    User,
    Ticker,
    Asset,
    Performance,
    Snapshot,
    TelegramAlert,
    Wallet,
    Portfolio,
    db,
)

from portfolio.forms import (
    LoginForm,
    RegisterForm,
    TickerForm,
    AssetForm,
    TelegramAlertForm,
)
from portfolio.utils import update_prices, send_message
from portfolio.decorators import login_required
import numpy as np

# Custom Jinja2 filter to format numbers to two decimal places
def format_decimal(value):
    return '{:,.2f}'.format(value)


def format_int(value):
    return '{:,.0f}'.format(value)


app.jinja_env.filters['format_decimal'] = format_decimal
app.jinja_env.filters['format_int'] = format_int


@app.route("/mobile", methods=["GET", "POST"])
def mobile():
    return render_template("mobile.html", wallet_name="wallet_name")


@app.route("/register", methods=["GET", "POST"])
def register():
    secret, qr = None, None
    form = RegisterForm()
    if form.validate_on_submit():
        u = User()
        db.session.add(u)
        db.session.commit()
        qr = u.qr
        secret = u.secret
    return render_template("register.html", form=form, qr=qr, secret=secret)


@app.route("/login/", methods=["GET", "POST"])
def login():
    session["logged_in"] = False
    form = LoginForm()
    if form.validate_on_submit():
        challenge = form.challenge.data
        users = User.query.all()
        for user in users:
            if user.verify_password(challenge):
                session["logged_in"] = True
                session["user"] = user.id
                return redirect(url_for("index"))
    return render_template("login.html", form=form, session=session)


@app.route("/logout")
def logout():
    session["logged_in"] = False
    return redirect(url_for("login"))


@app.route("/wallet/<wallet_id>", methods=["GET"])
@login_required
def wallet(wallet_id=None):
    user_id = session.get("user")
    user = User.query.get(user_id)

    # TODO: order_by value in database
    assets = sorted(
        Wallet.query.get(wallet_id).assets,
        key=lambda asset: asset.value,
        reverse=True
    )

    portfolio = Portfolio(assets)
    portfolio.calculate_asset_deltas()
    portfolio.calculate_percentage()

    last_scrape = (
        Ticker.query.filter(Ticker.token != "BaseCurrency")
        .first()
        .created_at.strftime("%m/%d/%Y %H:%M")
    )

    return render_template(
        "sector.html",
        user=user,
        assets=assets,
        portfolio=portfolio,
        last_scrape=last_scrape,
    )


@app.route("/total", methods=["GET"])
@login_required
def total():
    user_id = session.get("user")
    user = User.query.get(user_id)

    # TODO: order_by value in database
    assets = sorted(user.assets, key=lambda asset: asset.value, reverse=True)

    portfolio = Portfolio(assets)
    portfolio.calculate_asset_deltas()
    portfolio.calculate_percentage(normalize_target=True)

    last_scrape = (
        Ticker.query.filter(Ticker.token != "BaseCurrency")
        .first()
        .created_at.strftime("%m/%d/%Y %H:%M")
    )

    return render_template(
        "sector.html",
        user=user,
        assets=assets,
        portfolio=portfolio,
        last_scrape=last_scrape,
    )


@app.route("/", methods=["GET"])
@app.route("/<user_id>", methods=["GET"])
# @login_required
def index(user_id=None):
    # viewonly mode
    if user_id:
        # check that the requested user exists.
        if not User.query.filter(User.id == user_id).first():
            return redirect(url_for("login"))
        session["logged_in"] = True
        session["user"] = user_id
        update_prices()
        return redirect(url_for("index"))
    else:
        # user used the default login method
        # get user from the session object
        user_id = session.get("user")

    user = User.query.get(user_id)
    wallets = user.wallets

    portfolio = Portfolio(user.assets)
    sectors = []
    for w in wallets:
        ass = w.assets
        sectors.append(Portfolio(w.assets))


    # TODO: order_by value in database
    # assets = sorted(user.assets, key=lambda asset: asset.value, reverse=True)
    # portfolio = Portfolio(assets)
    # portfolio.calculate_asset_deltas()

    # sectors = (
    #    db.session.query(
    #        Asset.sector,
    #        db.func.sum(Asset.value).label("value"),
    #        db.func.sum(Asset.pnl_today).label("pnl"),
    #        (100 * db.func.sum(Asset.pnl_today) / db.func.sum(Asset.value)).label("change"),
    #        db.func.sum(Asset.target).label("target"),
    #        Asset.wallet_id
    #    )
    #    .filter(Asset.user_id == user_id)
    #    .group_by(Asset.wallet_id)
    #    .order_by(db.func.sum(Asset.value).desc())
    #    .all()
    #)

    last_scrape = (
        Ticker.query.filter(Ticker.token != "BaseCurrency")
        .first()
        .created_at.strftime("%m/%d/%Y %H:%M")
    )

    # detect device width
    user_agent = request.headers.get("User-Agent")

    return render_template(
        "index.html",
        portfolio=portfolio,
        sectors=sectors,
        wallets=wallets,
        stats=portfolio.history,
        last_scrape=last_scrape,
        realized=False,
        user_agent=user_agent,
    )


@app.route("/chart", methods=["GET"])
@login_required
def chart():
    user_id = session.get("user")
    user = User.query.get(user_id)

    # TODO: order_by value in database
    assets = sorted(user.assets, key=lambda asset: asset.value, reverse=True)

    portfolio = Portfolio(assets)

    return render_template(
        "chart.html",
        user=user,
        portfolio=portfolio,
        stats=portfolio.history
    )

@app.route("/ticker", methods=["GET", "POST"])
@login_required
def ticker():
    form = TickerForm()
    tickers = Ticker.query.order_by(Ticker.created_at.desc())

    if form.validate_on_submit():
        description = form.description.data
        token = form.token.data
        price = form.price.data
        currency = form.currency.data
        t = Ticker(
            description=description,
            token=token,
            price=price,
            currency=currency,
            kind=kind,
        )
        db.session.add(t)
        db.session.commit()
        flash(f"Your ticker <{token} is saved.")
        return redirect(url_for("index"))
    tickers = tickers.all()

    return render_template("ticker.html", tickers=tickers, form=form)


@app.route("/asset", methods=["GET", "POST"])
@login_required
def asset():
    form = AssetForm()
    assets = Asset.query.filter(Asset.user_id == session.get("user")).order_by(
        Asset.value.desc()
    )

    assets_ticker_ids = [asset.ticker_id for asset in assets]
    tickers = Ticker.query.all()
    form.ticker.choices = [
        (ticker.id, ticker.description)
        for ticker in tickers
        # if there is already a position, just edit that one.
        if ticker.id not in assets_ticker_ids
    ]

    user_id = session.get("user")
    user = User.query.get(user_id)
    wallets = user.wallets
    form.wallet.choices = [(w.id, w.name) for w in wallets]

    if form.validate_on_submit():
        ticker = form.ticker.data
        shares = form.shares.data
        wal = form.wallet.data
        target = form.target.data
        buy_price = form.buy_price.data
        a = Asset(
            user_id=session.get("user"),
            ticker_id=ticker,
            shares=shares,
            wallet_id=wal,
            target=target,
            buy_price=buy_price,
        )
        db.session.add(a)
        db.session.commit()
        flash(f"Your asset <{ticker} is saved.")
        return redirect(url_for("wallet", wallet_id=a.wallet_id))

    return render_template("asset.html", assets=assets.all(), form=form)


@app.route("/edit_asset/<asset_id>", methods=["GET", "POST"])
@login_required
def edit_asset(asset_id):
    asset = (
        Asset.query.filter(Asset.user_id == session.get("user"))
        .filter(Asset.id == asset_id)
        .first()
    )

    if not asset:
        abort(404)

    form = AssetForm(sector=asset.sector)
    form.ticker.choices = [asset.ticker.description]

    priority_wallet = asset.wallet_id
    wallets = asset.user.wallets
    sorted_wallets = sorted(wallets, key=lambda x: (x.id != priority_wallet, x.id))
    form.wallet.choices = [(w.id, w.name) for w in sorted_wallets]

    if form.validate_on_submit():
        asset.shares = form.shares.data
        # asset.sector = form.sector.data
        asset.wallet_id = form.wallet.data
        asset.target = form.target.data
        asset.buy_price = form.buy_price.data
        asset.ticker.price = form.ticker_price.data
        db.session.commit()
        flash(
            f"Your asset <{asset.ticker.description} is updated with shares {asset.shares}"
        )
        return redirect(url_for("wallet", wallet_id=asset.wallet_id))
        # return redirect(url_for("index"))

    form.shares.data = asset.shares
    form.target.data = asset.target
    form.buy_price.data = asset.buy_price
    form.ticker_price.data = asset.ticker.price

    return render_template("edit_asset.html", form=form, asset_id=asset_id)


@app.route("/delete_asset/<asset_id>", methods=["GET", "POST"])
@login_required
def delete_asset(asset_id):
    asset = (
        Asset.query.filter(Asset.user_id == session.get("user"))
        .filter(Asset.id == asset_id)
        .first()
    )

    if not asset:
        abort(404)

    asset_name = asset.ticker.description
    db.session.delete(asset)
    db.session.commit()
    flash(f"Your asset <{asset_name}> is deleted.")
    return redirect(url_for("wallet", wallet_id=asset.wallet_id))


@app.route("/scrape", methods=["GET"])
@login_required
def scrape():
    now = datetime.utcnow()
    last_scrape = Ticker.query.filter(Ticker.token != "BaseCurrency").first().created_at

    if not (last_scrape + timedelta(minutes=1)) >= now:
        update_prices()
        # flash(
        #    f"prices successfully updated :)"
        # )
    return redirect(url_for("index"))


@app.route("/telegram_alert", methods=["GET"])
@login_required
def telegram_alert():
    tg = TelegramAlert.query.filter(Asset.user_id == session.get("user")).first()
    form = TelegramAlertForm()

    if form.validate_on_submit():
        api_token = form.api_token.data
        api_chat = form.api_chat.data
        enabled = form.enabled.data
        # already exists
        if tg:
            tg.api_token = api_token
            tg.api_chat = api_chat
            tg.enabled = enabled
        else:
            telegram_alert = TelegramAlert(
                user_id=session.get("user"),
                api_token=api_token,
                api_chat=api_chat,
                enabled=enabled,
            )
            db.session.add(telegram_alert)
        db.session.commit()
        flash(f"Your TelegramAlert to chat is updated.")
        return redirect(url_for("telegram_alert"))

    # already exists
    if tg:
        form.api_token.data = tg.api_token
        form.api_chat.data = tg.api_chat
        form.enabled.data = tg.enabled

    return render_template("telegram_alert.html", form=form)


@app.route("/test_alert>", methods=["GET"])
@login_required
def test_alert():
    tg = TelegramAlert.query.filter(
        TelegramAlert.user_id == session.get("user")
    ).first()
    if not tg or not tg.enabled:
        flash(f"Your alerts are disabled. Please enable before testing {tg}.")
        return redirect(url_for("telegram_alert"))

    result = send_message(tg.api_url, tg.api_token, tg.api_chat, "test message")
    flash(result)
    return redirect(url_for("telegram_alert"))
