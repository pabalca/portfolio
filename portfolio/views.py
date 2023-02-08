from datetime import datetime, timedelta
from flask import abort, flash, redirect, render_template, session, url_for, request
from sqlalchemy import func, extract

from portfolio import app
from portfolio.models import User, Ticker, Asset, Performance, Snapshot, TelegramAlert, db
from portfolio.forms import LoginForm, RegisterForm, TickerForm, AssetForm, TelegramAlertForm
from portfolio.utils import update_prices, send_message
from portfolio.decorators import login_required


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


@app.route("/", methods=["GET"])
@login_required
def index():
    assets = (
        Asset.query.filter(Asset.user_id == session.get("user"))
        .order_by(Asset.value.desc())
        .all()
    )
    sectors = (
        db.session.query(Asset.sector, db.func.sum(Asset.value).label("value"))
        .filter(Asset.user_id == session.get("user"))
        .group_by(Asset.sector)
        .all()
    )

    if assets:
        # portfolio stats
        value = (
            db.session.query(db.func.sum(Asset.value).label("value"))
            .filter(Asset.user_id == session.get("user"))
            .first()
            .value
        )
        pnl_today = 0
        unrealized_pnl = 0
        total_percentage = 0
        for asset in assets:
            pnl_today += asset.pnl_today
            unrealized_pnl += asset.unrealized_pnl
            total_percentage += asset.percentage
        change = 100 * ((value + pnl_today) / value - 1)
        portfolio = {"pnl_today": pnl_today, "value": value, "change": change, "unrealized_pnl": unrealized_pnl, "total_percentage": total_percentage}
    else:
        portfolio = None

    # performance stats
    stats = (
        Performance.query.filter(Performance.user_id == session.get("user"))
        .group_by(extract('year', Performance.created_at), extract('month', Performance.created_at), extract('day', Performance.created_at))
        .order_by(Performance.created_at.asc())
        .all()
    )

    last_scrape = (
        Ticker.query.filter(Ticker.token != "BaseCurrency").first().created_at.strftime("%m/%d/%Y %H:%M")
    )

    return render_template(
        "index.html", assets=assets, sectors=sectors, portfolio=portfolio, stats=stats, last_scrape=last_scrape
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

    if form.validate_on_submit():
        ticker = form.ticker.data
        shares = form.shares.data
        sector = form.sector.data
        target = form.target.data
        buy_price = form.buy_price.data
        a = Asset(
            user_id=session.get("user"),
            ticker_id=ticker,
            shares=shares,
            sector=sector,
            target=target,
        )
        db.session.add(a)
        db.session.commit()
        flash(f"Your asset <{ticker} is saved.")
        return redirect(url_for("asset"))

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

    if form.validate_on_submit():
        asset.shares = form.shares.data
        asset.sector = form.sector.data
        asset.target = form.target.data
        asset.buy_price = form.buy_price.data
        db.session.commit()
        flash(
            f"Your asset <{asset.ticker.description} is updated with shares {asset.shares}"
        )
        return redirect(url_for("asset"))
    form.shares.data = asset.shares
    form.target.data = asset.target
    form.buy_price.data = asset.buy_price

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
    return redirect(url_for("asset"))


@app.route("/scrape", methods=["GET"])
@login_required
def scrape():
    now = datetime.utcnow()
    last_scrape = (
        Ticker.query.filter(Ticker.token != "BaseCurrency").first().created_at
    )

    if not (last_scrape + timedelta(minutes=1)) >= now:
        update_prices()
        #flash(
        #    f"prices successfully updated :)"
        #)
    return redirect(url_for("index"))


@app.route("/telegram_alert", methods=["GET"])
@login_required
def telegram_alert():
    tg = (
        TelegramAlert.query.filter(Asset.user_id == session.get("user"))
        .first()
    )
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
            telegram_alert = TelegramAlert(user_id=session.get("user"), api_token=api_token, api_chat=api_chat, enabled=enabled)
            db.session.add(telegram_alert)
        db.session.commit()
        flash(
            f"Your TelegramAlert to chat is updated."
        )
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
    tg = (
        TelegramAlert.query.filter(TelegramAlert.user_id == session.get("user"))
        .first()
    )
    if not tg or not tg.enabled:
        flash(f"Your alerts are disabled. Please enable before testing {tg}.")
        return redirect(url_for("telegram_alert"))

    result = send_message(tg.api_url, tg.api_token, tg.api_chat, "test message")
    flash(result)
    return redirect(url_for("telegram_alert"))

    
