from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from futures_mvp.modules.broker_adapter.read_only import (
    BrokerReadOnlyResult,
    BrokerReadOnlyStatus,
    BrokerSnapshot,
)


class BrokerShadowCompareStatus(StrEnum):
    MATCH = "MATCH"
    DIFFERENCE = "DIFFERENCE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class DifferenceEntry:
    category: str
    key: str
    paper_value: str
    broker_value: str
    severity: str = "INFO"


@dataclass(frozen=True)
class DifferenceReport:
    status: BrokerShadowCompareStatus
    differences: tuple[DifferenceEntry, ...] = ()
    reason: str | None = None
    diagnostics: tuple[str, ...] = (
        "Research -> Paper -> Broker 快照 -> Compare",
        "只读",
        "不写数据库",
    )


def compare_paper_to_broker_snapshot(
    paper_result: object,
    broker_result: BrokerReadOnlyResult,
) -> DifferenceReport:
    if broker_result.status is BrokerReadOnlyStatus.BLOCKED:
        return DifferenceReport(
            status=BrokerShadowCompareStatus.BLOCKED,
            reason=broker_result.reason or "Broker 快照已阻断",
            diagnostics=(
                "Broker 快照已阻断",
                *broker_result.diagnostics,
            ),
        )
    if broker_result.snapshot is None:
        return DifferenceReport(
            status=BrokerShadowCompareStatus.BLOCKED,
            reason="Broker 快照缺失",
            diagnostics=("Broker 快照缺失", "不比较"),
        )
    if str(getattr(paper_result, "status", "")) == "BLOCKED":
        return DifferenceReport(
            status=BrokerShadowCompareStatus.BLOCKED,
            reason=str(getattr(paper_result, "reason", "") or "Paper 结果已阻断"),
            diagnostics=("Paper 结果已阻断", "不修改 Broker"),
        )

    differences = _compare_values(paper_result, broker_result.snapshot)
    if differences:
        return DifferenceReport(
            status=BrokerShadowCompareStatus.DIFFERENCE,
            differences=differences,
        )
    return DifferenceReport(status=BrokerShadowCompareStatus.MATCH)


def _compare_values(
    paper_result: object,
    broker_snapshot: BrokerSnapshot,
) -> tuple[DifferenceEntry, ...]:
    differences: list[DifferenceEntry] = []
    paper_portfolio = getattr(paper_result, "portfolio", None)
    differences.extend(
        _diff_scalar(
            category="account",
            key="equity",
            paper_value=_decimal_text(getattr(paper_portfolio, "equity", Decimal("0"))),
            broker_value=_decimal_text(broker_snapshot.account.equity),
        )
    )
    differences.extend(
        _diff_scalar(
            category="account",
            key="cash",
            paper_value=_decimal_text(getattr(paper_portfolio, "cash", Decimal("0"))),
            broker_value=_decimal_text(broker_snapshot.account.cash),
        )
    )
    differences.extend(
        _diff_scalar(
            category="count",
            key="positions",
            paper_value=str(len(tuple(_iter(getattr(paper_result, "positions", ()))))),
            broker_value=str(len(broker_snapshot.positions)),
        )
    )
    differences.extend(
        _diff_scalar(
            category="count",
            key="orders",
            paper_value=str(len(tuple(_iter(getattr(paper_result, "orders", ()))))),
            broker_value=str(len(broker_snapshot.orders)),
        )
    )
    differences.extend(
        _diff_scalar(
            category="count",
            key="trades",
            paper_value=str(len(tuple(_iter(getattr(paper_result, "fills", ()))))),
            broker_value=str(len(broker_snapshot.trades)),
        )
    )
    differences.extend(_diff_positions(paper_result, broker_snapshot))
    return tuple(differences)


def _diff_positions(
    paper_result: object,
    broker_snapshot: BrokerSnapshot,
) -> tuple[DifferenceEntry, ...]:
    paper_positions = {
        str(getattr(position, "trade_instrument_id", "")): _decimal_text(
            getattr(position, "quantity", Decimal("0"))
        )
        for position in _iter(getattr(paper_result, "positions", ()))
    }
    broker_positions = {
        position.trade_instrument_id: _decimal_text(position.quantity)
        for position in broker_snapshot.positions
    }
    all_keys = sorted(set(paper_positions) | set(broker_positions))
    differences: list[DifferenceEntry] = []
    for key in all_keys:
        differences.extend(
            _diff_scalar(
                category="position",
                key=key,
                paper_value=paper_positions.get(key, "MISSING"),
                broker_value=broker_positions.get(key, "MISSING"),
                severity="WARN",
            )
        )
    return tuple(differences)


def _diff_scalar(
    *,
    category: str,
    key: str,
    paper_value: str,
    broker_value: str,
    severity: str = "INFO",
) -> tuple[DifferenceEntry, ...]:
    if paper_value == broker_value:
        return ()
    return (
        DifferenceEntry(
            category=category,
            key=key,
            paper_value=paper_value,
            broker_value=broker_value,
            severity=severity,
        ),
    )


def _iter(value: object) -> Iterable[object]:
    if isinstance(value, tuple | list):
        return value
    return ()


def _decimal_text(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)
