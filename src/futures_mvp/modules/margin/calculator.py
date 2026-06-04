from dataclasses import dataclass
from decimal import Decimal

from futures_mvp.domain.decimal import require_decimal
from futures_mvp.domain.enums import MarginPriceBasis, MarginResultStatus
from futures_mvp.domain.models import (
    AccountContext,
    MarginRequirement,
    MarginResult,
    MarginRule,
    Position,
)


@dataclass(frozen=True)
class ResolvedMarginPrices:
    long_price: Decimal
    short_price: Decimal
    snapshot_price: Decimal


class MarginCalculator:
    def calculate(
        self,
        position: Position | None,
        rule: MarginRule | None,
        account: AccountContext,
        *,
        latest_price: Decimal | None = None,
        settlement_price: Decimal | None = None,
    ) -> MarginResult:
        if position is None:
            return MarginResult(
                status=MarginResultStatus.REJECTED_MISSING_POSITION,
                reason="missing_position",
                account_id=account.account_id,
            )
        if rule is None:
            return MarginResult(
                status=MarginResultStatus.REJECTED_MISSING_RULE,
                reason="missing_margin_rule",
                account_id=position.account_id,
                instrument_id=position.instrument_id,
            )
        if position.account_id != account.account_id:
            return MarginResult(
                status=MarginResultStatus.ERROR,
                reason="margin_identity_mismatch: account_id",
                account_id=position.account_id,
                instrument_id=position.instrument_id,
            )
        if rule.instrument_id != position.instrument_id:
            return MarginResult(
                status=MarginResultStatus.ERROR,
                reason="margin_identity_mismatch: instrument_id",
                account_id=position.account_id,
                instrument_id=position.instrument_id,
            )

        resolved_prices = resolve_margin_prices(
            position,
            rule,
            latest_price=latest_price,
            settlement_price=settlement_price,
        )
        if resolved_prices is None:
            return MarginResult(
                status=MarginResultStatus.REJECTED_MISSING_PRICE,
                reason="missing_margin_price",
                account_id=position.account_id,
                instrument_id=position.instrument_id,
            )

        long_qty = position.long_today_qty + position.long_yesterday_qty
        short_qty = position.short_today_qty + position.short_yesterday_qty
        long_initial = (
            long_qty
            * resolved_prices.long_price
            * rule.contract_multiplier
            * rule.long_initial_margin_rate
        )
        short_initial = (
            short_qty
            * resolved_prices.short_price
            * rule.contract_multiplier
            * rule.short_initial_margin_rate
        )
        long_maintenance = (
            long_qty
            * resolved_prices.long_price
            * rule.contract_multiplier
            * rule.long_maintenance_margin_rate
        )
        short_maintenance = (
            short_qty
            * resolved_prices.short_price
            * rule.contract_multiplier
            * rule.short_maintenance_margin_rate
        )
        total_initial = long_initial + short_initial
        total_maintenance = long_maintenance + short_maintenance
        is_sufficient = account.available_cash >= total_initial
        requirement = MarginRequirement(
            account_id=position.account_id,
            instrument_id=position.instrument_id,
            long_initial_margin=long_initial,
            short_initial_margin=short_initial,
            total_initial_margin=total_initial,
            long_maintenance_margin=long_maintenance,
            short_maintenance_margin=short_maintenance,
            total_maintenance_margin=total_maintenance,
            margin_used=total_initial,
            required_cash=total_initial,
            is_sufficient=is_sufficient,
            reason=None if is_sufficient else "insufficient_cash",
        )
        if not is_sufficient:
            return MarginResult(
                status=MarginResultStatus.REJECTED_INSUFFICIENT_CASH,
                requirement=requirement,
                reason="insufficient_cash",
                account_id=position.account_id,
                instrument_id=position.instrument_id,
            )
        return MarginResult(
            status=MarginResultStatus.CALCULATED,
            requirement=requirement,
            reason=None,
            account_id=position.account_id,
            instrument_id=position.instrument_id,
        )


def resolve_margin_prices(
    position: Position,
    rule: MarginRule,
    *,
    latest_price: Decimal | None = None,
    settlement_price: Decimal | None = None,
) -> ResolvedMarginPrices | None:
    long_qty = position.long_today_qty + position.long_yesterday_qty
    short_qty = position.short_today_qty + position.short_yesterday_qty
    if rule.price_basis == MarginPriceBasis.MANUAL:
        return _same_price(rule.price)
    if rule.price_basis == MarginPriceBasis.LAST_PRICE:
        return _same_price(latest_price)
    if rule.price_basis == MarginPriceBasis.SETTLEMENT_PRICE:
        return _same_price(settlement_price)
    if rule.price_basis == MarginPriceBasis.AVG_PRICE:
        if long_qty > 0 and position.long_avg_price <= 0:
            return None
        if short_qty > 0 and position.short_avg_price <= 0:
            return None
        long_price = position.long_avg_price if long_qty > 0 else Decimal("0")
        short_price = position.short_avg_price if short_qty > 0 else Decimal("0")
        total_qty = long_qty + short_qty
        if total_qty == 0:
            snapshot_price = Decimal("0")
        else:
            snapshot_price = ((long_qty * long_price) + (short_qty * short_price)) / total_qty
        return ResolvedMarginPrices(
            long_price=long_price,
            short_price=short_price,
            snapshot_price=snapshot_price,
        )
    return None


def _same_price(price: Decimal | None) -> ResolvedMarginPrices | None:
    if price is None:
        return None
    typed_price = require_decimal(price)
    if typed_price <= 0:
        return None
    return ResolvedMarginPrices(
        long_price=typed_price,
        short_price=typed_price,
        snapshot_price=typed_price,
    )
