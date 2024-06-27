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


@app.route("/<sector_name>", methods=["GET"])
@login_required
def sector(sector_name=None):
    user_id = session.get("user")

    # assets data
    assets = (
        Asset.query
        .filter(Asset.user_id == user_id)
        .filter(Asset.sector == sector_name)
        .order_by(Asset.value.desc())
        .all()
    )

    # get all assets performance of the selected sector
    # portfolio data
    portfolio = (
        db.session.query(
            db.func.sum(Asset.value).label("value"),
            db.func.sum(Asset.pnl_today).label("pnl_today"),
            (100 * db.func.sum(Asset.pnl_today) / db.func.sum(Asset.value)).label("change"),
            db.func.sum(Asset.target).label("total_target"),
            db.func.sum(Asset.unrealized_pnl).label("unrealized_pnl"),
        )
        .filter(Asset.user_id == user_id)
        .filter(Asset.sector == sector_name)
        .order_by(db.func.sum(Asset.value).desc())
        .first()
    )

    last_scrape = (
        Ticker.query.filter(Ticker.token != "BaseCurrency")
        .first()
        .created_at.strftime("%m/%d/%Y %H:%M")
    )

    return render_template(
        "sector.html",
        assets=assets,
        portfolio=portfolio,
        last_scrape=last_scrape,
    )


@app.route("/", methods=["GET"])
@app.route("/<user_id>", methods=["GET"])
@login_required
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

    sectors = (
        db.session.query(
            Asset.sector,
            db.func.sum(Asset.value).label("value"),
            db.func.sum(Asset.pnl_today).label("pnl"),
            (100 * db.func.sum(Asset.pnl_today) / db.func.sum(Asset.value)).label("change"),
            db.func.sum(Asset.target).label("target"),
        )   
        .filter(Asset.user_id == user_id)
        .group_by(Asset.sector)
        .order_by(db.func.sum(Asset.value).desc())
        .all()
    )

    select_sector = request.args.get('sector')
    if select_sector:
        assets = (
            Asset.query.filter(Asset.user_id == user_id).filter(Asset.sector == select_sector).order_by(Asset.value.desc()).all()
        )
    else:
        assets = (
            Asset.query.filter(Asset.user_id == user_id).order_by(Asset.value.desc()).all()
        )

    #if select_sector:
    #    return select_sector
    #else:
    #    return "nada"


    if assets:
        # portfolio stats
        if select_sector:
            value = (
                db.session.query(db.func.sum(Asset.value).label("value"))
                .filter(Asset.user_id == user_id)
                .filter(Asset.sector == select_sector)
                .first()
                .value
            )
        else:
            value = (
                db.session.query(db.func.sum(Asset.value).label("value"))
                .filter(Asset.user_id == user_id)
                .first()
                .value
            )

        pnl_today = 0
        unrealized_pnl = 0
        total_percentage = 0
        total_target = 0
        for asset in assets:
            pnl_today += asset.pnl_today
            unrealized_pnl += asset.unrealized_pnl
            total_percentage += asset.percentage
            total_target += asset.target
        change = 100 * ((value + pnl_today) / value - 1)
        portfolio = {
            "pnl_today": pnl_today,
            "value": value,
            "change": change,
            "unrealized_pnl": unrealized_pnl,
            "total_percentage": total_percentage,
            "total_target": total_target,
        }
    else:
        portfolio = None

    # performance stats
    stats = (
        Performance.query.filter(Performance.user_id == user_id)
        .filter(extract("year", Performance.created_at) == 2024)
        .group_by(
            extract("year", Performance.created_at),
            extract("month", Performance.created_at),
            extract("day", Performance.created_at),
        )
        .order_by(Performance.created_at.asc())
        .all()
    )

    # Add current value
    performance_now = Performance(user_id=user_id, value=portfolio["value"], pnl=portfolio["pnl_today"], change=portfolio["change"], created_at=datetime.utcnow())
    stats.append(performance_now)


    # max drawdown
    vals = [s.value for s in stats]
    i = np.argmax(np.maximum.accumulate(vals) - vals) # end of the period
    j = np.argmax(vals[:i]) # start of period
    drawdown = {
        "start": stats[j].created_at,
        "end": stats[i].created_at,
        "start_value": stats[j].value,
        "end_value": stats[i].value,
        "per": (stats[i].value - stats[j].value) / stats[j].value ,
    }


    # portfolio from all time highs
    ath_portfolio = max(vals)
    ath_down_value = portfolio["value"] - ath_portfolio
    ath_down_per = ath_down_value/ath_portfolio
    ath = {
        "value": ath_portfolio,
        "down": ath_down_value,
        "per": ath_down_per
    }
    
    

    # calculate win/loss day ratio
    win_days = 0
    lose_days = 0
    win_total = 0
    lose_total = 0

    win_max = 0
    lose_max = 0

    for day in stats:
        if day.pnl > 0:
            win_days+=1
            win_total+=day.pnl
            if day.pnl > win_max:
                win_max = day.pnl
        else:
            lose_days+=1
            lose_total+=day.pnl
            if day.pnl < lose_max:
                lose_max = day.pnl

    win_lose_stats = {
        "win_days": win_days,
        "win_total": win_total,
        "win_average": win_total / win_days,
        "win_max": win_max,
        "lose_days": lose_days,
        "lose_total": lose_total,
        "lose_average": lose_total / lose_days,
        "lose_max": lose_max,
    }
           



    ## calculate rolling moving average on volatility


    for entry in stats[::-1]:  # Iterate in reverse order
        entry.move = entry.pnl / entry.value if entry.value != 0 else 0


    # Initialize variables for rolling average calculation
    rolling_avg_30d = []
    rolling_days = 30

    # Calculate rolling average of move over a 30-day window
    for i in range(len(stats) - 1, -1, -1):  # Iterate from last to first
        rolling_sum = 0
        rolling_count = 0
        window_size = min(i + 1, rolling_days)  # Adjust window size dynamically
    
        for j in range(i, i - window_size, -1):  # Iterate backwards up to 30 days or until start of list
            entry = stats[j]
            rolling_sum += abs(entry.move)
            rolling_count += 1

        if rolling_count > 0:
            rolling_avg_30d.insert(0, rolling_sum / rolling_count)
        else:
            rolling_avg_30d.insert(0, 0)  # Handle case where not enough data points in the window


    # Add rolling_avg_30d to stats as a new attribute
    for entry, avg in zip(stats, rolling_avg_30d):
        entry.annualized_vol_30d = avg * np.sqrt(365)
        entry.rolling_avg_30d = avg






    last_scrape = (
        Ticker.query.filter(Ticker.token != "BaseCurrency")
        .first()
        .created_at.strftime("%m/%d/%Y %H:%M")
    )

    # detect device width
    user_agent = request.headers.get("User-Agent")

    return render_template(
        "index.html",
        assets=assets,
        sectors=sectors,
        portfolio=portfolio,
        stats=stats,
        drawdown=drawdown,
        ath=ath,
        win_lose_stats=win_lose_stats,
        last_scrape=last_scrape,
        realized=False,
        user_agent=user_agent,
        select_sector=select_sector
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
            buy_price=buy_price,
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
        asset.ticker.price = form.ticker_price.data
        db.session.commit()
        flash(
            f"Your asset <{asset.ticker.description} is updated with shares {asset.shares}"
        )
        return redirect(url_for("index"))
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
    return redirect(url_for("asset"))


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
