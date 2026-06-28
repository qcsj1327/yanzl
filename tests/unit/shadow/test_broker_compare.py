from dataclasses import dataclass
from decimal import Decimal

from futures_mvp.modules.broker_adapter import (
    BrokerReadOnlyResult,
    BrokerReadOnlyStatus,
    blocked_broker_snapshot,
    sample_broker_snapshot,
)
from futures_mvp.modules.shadow import (
    BrokerShadowCompareStatus,
    compare_paper_to_broker_snapshot,
)


@dataclass(frozen=True)
class PaperPortfolio:
    cash: Decimal
    equity: Decimal


@dataclass(frozen=True)
class PaperPosition:
    trade_instrument_id: str
    quantity: Decimal


@dataclass(frozen=True)
class PaperResult:
    status: str
    portfolio: PaperPortfolio
    positions: tuple[PaperPosition, ...]
    orders: tuple[object, ...]
    fills: tuple[object, ...]
    reason: str | None = None


def test_compare_reports_match_for_equal_paper_and_broker_snapshot() -> None:
    broker_snapshot = sample_broker_snapshot()
    paper = PaperResult(
        status="COMPLETED",
        portfolio=PaperPortfolio(cash=Decimal("96420"), equity=Decimal("100120")),
        positions=(
            PaperPosition("ao2609", Decimal("1")),
            PaperPosition("rb2601", Decimal("1")),
        ),
        orders=(object(),),
        fills=(object(),),
    )
    broker_result = BrokerReadOnlyResult(
        status=BrokerReadOnlyStatus.READY,
        snapshot=broker_snapshot,
        account=broker_snapshot.account,
        positions=broker_snapshot.positions,
        orders=broker_snapshot.orders,
        trades=broker_snapshot.trades,
    )

    report = compare_paper_to_broker_snapshot(paper, broker_result)

    assert report.status is BrokerShadowCompareStatus.MATCH
    assert report.differences == ()


def test_compare_reports_difference_for_account_and_position_mismatch() -> None:
    broker_snapshot = sample_broker_snapshot()
    paper = PaperResult(
        status="COMPLETED",
        portfolio=PaperPortfolio(cash=Decimal("1"), equity=Decimal("2")),
        positions=(PaperPosition("ao2609", Decimal("99")),),
        orders=(),
        fills=(),
    )
    broker_result = BrokerReadOnlyResult(
        status=BrokerReadOnlyStatus.READY,
        snapshot=broker_snapshot,
        account=broker_snapshot.account,
        positions=broker_snapshot.positions,
        orders=broker_snapshot.orders,
        trades=broker_snapshot.trades,
    )

    report = compare_paper_to_broker_snapshot(paper, broker_result)

    assert report.status is BrokerShadowCompareStatus.DIFFERENCE
    difference_keys = {(item.category, item.key) for item in report.differences}
    assert ("account", "cash") in difference_keys
    assert ("account", "equity") in difference_keys
    assert ("position", "ao2609") in difference_keys
    assert ("position", "rb2601") in difference_keys


def test_compare_blocks_when_broker_snapshot_is_blocked() -> None:
    paper = PaperResult(
        status="COMPLETED",
        portfolio=PaperPortfolio(cash=Decimal("0"), equity=Decimal("0")),
        positions=(),
        orders=(),
        fills=(),
    )

    report = compare_paper_to_broker_snapshot(
        paper,
        blocked_broker_snapshot("Broker 网络错误"),
    )

    assert report.status is BrokerShadowCompareStatus.BLOCKED
    assert report.reason == "Broker 网络错误"
