user_id = "1ab43d09-21ac-43c6-b46b-b08ad3e0b760"

portfolio = (
    db.session.query(
        db.func.sum(Asset.value).label("value"),
        db.func.sum(Asset.pnl_today).label("pnl_today"),
        (100 * db.func.sum(Asset.pnl_today) / db.func.sum(Asset.value)).label("change"),
        db.func.sum(Asset.target).label("total_target"),
        db.func.sum(Asset.percentage).label("total_percentage"),
        db.func.sum(Asset.unrealized_pnl).label("unrealized_pnl"),
    )
    .filter(Asset.user_id == user_id)
    .order_by(db.func.sum(Asset.value).desc())
    .first()
)



portfolio = {
    "pnl_today": sum([asset.pnl for asset in assets]),
    "value": sum([asset.pnl for asset in assets]),
    "change": change,
    "unrealized_pnl": unrealized_pnl,
    "total_percentage": total_percentage,
    "total_target": total_target,
}

