from decimal import Decimal
from typing import Any

from futures_mvp.domain.errors import DecimalRequiredError


def require_decimal(value: Any) -> Decimal:
    if isinstance(value, float):
        raise DecimalRequiredError("float is forbidden; use Decimal or a decimal string")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | str):
        return Decimal(value)
    raise DecimalRequiredError(f"expected Decimal-compatible value, got {type(value).__name__}")
