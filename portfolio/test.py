
user_id = "1ab43d09-21ac-43c6-b46b-b08ad3e0b760"
sector_name = "crypto"

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

assets = (
    Asset.query
    .filter(Asset.user_id == user_id)
    .filter(Asset.sector == sector_name)
    .order_by(Asset.value.desc())
    .all()
)

sectors = (
    db.session.query(
        Asset.sector,
        db.func.sum(Asset.value).label("value"),
        db.func.sum(Asset.pnl_today).label("pnl"),
        (100 * db.func.sum(Asset.pnl_today) / db.func.sum(Asset.value)).label("change"),
        db.func.sum(Asset.target).label("target"),
        Asset.wallet_id
    )
    .filter(Asset.user_id == user_id)
    .group_by(Asset.sector)
    .order_by(db.func.sum(Asset.value).desc())
    .all()
)