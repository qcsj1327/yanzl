from datetime import UTC, datetime
from decimal import Decimal

from futures_mvp.domain.enums import TradeIdentitySource
from futures_mvp.domain.models import stable_json_sha256


def _decimal_value(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _datetime_value(value: datetime) -> str:
    if value.tzinfo is not None and value.utcoffset() is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.isoformat()


def _required_string(value: str, *, field_name: str) -> str:
    if not value:
        raise ValueError(f"{field_name} is required for derived trade identity")
    return value


def build_exchange_trade_id_fallback(
    *,
    account_id: str,
    exchange: str,
    order_id: str,
    report_id: str,
    cumulative_filled_qty: Decimal,
    fill_price: Decimal,
    report_ts: datetime,
) -> str:
    payload = {
        "account_id": _required_string(account_id, field_name="account_id"),
        "cumulative_filled_qty": _decimal_value(cumulative_filled_qty),
        "exchange": _required_string(exchange, field_name="exchange"),
        "fill_price": _decimal_value(fill_price),
        "order_id": _required_string(order_id, field_name="order_id"),
        "report_id": _required_string(report_id, field_name="report_id"),
        "report_ts": _datetime_value(report_ts),
    }
    return "derived_" + stable_json_sha256(payload)


def build_trade_identity(
    *,
    account_id: str,
    exchange: str,
    exchange_trade_id: str | None,
    order_id: str,
    report_id: str,
    cumulative_filled_qty: Decimal,
    fill_price: Decimal,
    report_ts: datetime,
) -> tuple[str, TradeIdentitySource]:
    if exchange_trade_id is not None and exchange_trade_id.strip():
        return exchange_trade_id.strip(), TradeIdentitySource.EXCHANGE_TRADE_ID

    return (
        build_exchange_trade_id_fallback(
            account_id=account_id,
            exchange=exchange,
            order_id=order_id,
            report_id=report_id,
            cumulative_filled_qty=cumulative_filled_qty,
            fill_price=fill_price,
            report_ts=report_ts,
        ),
        TradeIdentitySource.DERIVED_FROM_REPORT,
    )
