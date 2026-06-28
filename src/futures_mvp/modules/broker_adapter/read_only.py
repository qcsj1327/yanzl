from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, TypeVar


class BrokerReadOnlyStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class BrokerReadOnlyError(Exception):
    """只读 Broker 快照错误；调用方必须 fail closed。"""


class BrokerNetworkError(BrokerReadOnlyError):
    pass


class BrokerLoginError(BrokerReadOnlyError):
    pass


class BrokerAccountNotFoundError(BrokerReadOnlyError):
    pass


@dataclass(frozen=True)
class BrokerAccountSnapshot:
    account_id: str
    currency: str
    cash: Decimal
    available: Decimal
    equity: Decimal
    margin: Decimal
    frozen: Decimal
    updated_at: datetime
    source: str = "broker_read_only_account_snapshot"


@dataclass(frozen=True)
class BrokerPositionSnapshot:
    account_id: str
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    side: str
    quantity: Decimal
    avg_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    updated_at: datetime
    source: str = "broker_read_only_position_snapshot"


@dataclass(frozen=True)
class BrokerOrderSnapshot:
    account_id: str
    order_id: str
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    side: str
    order_status: str
    quantity: Decimal
    filled_quantity: Decimal
    price: Decimal
    created_at: datetime
    updated_at: datetime
    source: str = "broker_read_only_order_snapshot"


@dataclass(frozen=True)
class BrokerTradeSnapshot:
    account_id: str
    trade_id: str
    order_id: str
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    side: str
    fill_price: Decimal
    fill_qty: Decimal
    fee: Decimal
    traded_at: datetime
    source: str = "broker_read_only_trade_snapshot"


@dataclass(frozen=True)
class BrokerSnapshot:
    account: BrokerAccountSnapshot
    positions: tuple[BrokerPositionSnapshot, ...] = ()
    orders: tuple[BrokerOrderSnapshot, ...] = ()
    trades: tuple[BrokerTradeSnapshot, ...] = ()
    diagnostics: tuple[str, ...] = ("只读", "无报单接口", "无撤单接口")


T = TypeVar("T")


@dataclass(frozen=True)
class BrokerReadOnlyResult:
    status: BrokerReadOnlyStatus
    reason: str | None = None
    snapshot: BrokerSnapshot | None = None
    account: BrokerAccountSnapshot | None = None
    positions: tuple[BrokerPositionSnapshot, ...] = ()
    orders: tuple[BrokerOrderSnapshot, ...] = ()
    trades: tuple[BrokerTradeSnapshot, ...] = ()
    diagnostics: tuple[str, ...] = ()


class BrokerSnapshotSource(Protocol):
    def read_snapshot(self, account_id: str) -> BrokerSnapshot: ...


class InMemoryBrokerSnapshotSource:
    def __init__(self, snapshots: tuple[BrokerSnapshot, ...]) -> None:
        self._snapshots = {
            snapshot.account.account_id: snapshot
            for snapshot in snapshots
        }

    def read_snapshot(self, account_id: str) -> BrokerSnapshot:
        snapshot = self._snapshots.get(account_id)
        if snapshot is None:
            raise BrokerAccountNotFoundError("Broker 账户不存在")
        return snapshot


class BrokerReadOnlyAdapter:
    adapter_name = "broker_read_only"

    def __init__(
        self,
        *,
        source: BrokerSnapshotSource | None = None,
        configured: bool = False,
    ) -> None:
        self._source = source
        self._configured = configured
        self.read_attempts = 0

    def snapshot(self, account_id: str) -> BrokerReadOnlyResult:
        blocked_reason = self._preflight_blocked_reason(account_id)
        if blocked_reason is not None:
            return _blocked(blocked_reason)

        self.read_attempts += 1
        try:
            snapshot = self._source_or_raise().read_snapshot(account_id)
        except BrokerNetworkError:
            return _blocked("Broker 网络错误")
        except BrokerLoginError:
            return _blocked("Broker 登录失败")
        except BrokerAccountNotFoundError:
            return _blocked("Broker 账户不存在")
        except BrokerReadOnlyError as exc:
            return _blocked(str(exc) or "Broker 只读错误")
        return BrokerReadOnlyResult(
            status=BrokerReadOnlyStatus.READY,
            snapshot=snapshot,
            account=snapshot.account,
            positions=snapshot.positions,
            orders=snapshot.orders,
            trades=snapshot.trades,
            diagnostics=(
                "只读快照已加载",
                "不自动重试",
                "不自动登录",
                "不报单",
                "不撤单",
                *snapshot.diagnostics,
            ),
        )

    def account(self, account_id: str) -> BrokerReadOnlyResult:
        result = self.snapshot(account_id)
        if result.status is BrokerReadOnlyStatus.BLOCKED:
            return result
        return BrokerReadOnlyResult(
            status=BrokerReadOnlyStatus.READY,
            account=result.account,
            diagnostics=result.diagnostics,
        )

    def positions(self, account_id: str) -> BrokerReadOnlyResult:
        result = self.snapshot(account_id)
        if result.status is BrokerReadOnlyStatus.BLOCKED:
            return result
        return BrokerReadOnlyResult(
            status=BrokerReadOnlyStatus.READY,
            positions=result.positions,
            diagnostics=result.diagnostics,
        )

    def orders(self, account_id: str) -> BrokerReadOnlyResult:
        result = self.snapshot(account_id)
        if result.status is BrokerReadOnlyStatus.BLOCKED:
            return result
        return BrokerReadOnlyResult(
            status=BrokerReadOnlyStatus.READY,
            orders=result.orders,
            diagnostics=result.diagnostics,
        )

    def trades(self, account_id: str) -> BrokerReadOnlyResult:
        result = self.snapshot(account_id)
        if result.status is BrokerReadOnlyStatus.BLOCKED:
            return result
        return BrokerReadOnlyResult(
            status=BrokerReadOnlyStatus.READY,
            trades=result.trades,
            diagnostics=result.diagnostics,
        )

    def _preflight_blocked_reason(self, account_id: str) -> str | None:
        if not self._configured:
            return "Broker 只读适配器未配置"
        if self._source is None:
            return "Broker 快照源未配置"
        if not account_id.strip():
            return "Broker 账户 ID 缺失"
        return None

    def _source_or_raise(self) -> BrokerSnapshotSource:
        if self._source is None:
            raise BrokerReadOnlyError("Broker 快照源未配置")
        return self._source


def blocked_broker_snapshot(reason: str) -> BrokerReadOnlyResult:
    return _blocked(reason)


def sample_broker_snapshot(*, account_id: str = "account-1") -> BrokerSnapshot:
    updated_at = datetime(2026, 6, 28, tzinfo=UTC)
    return BrokerSnapshot(
        account=BrokerAccountSnapshot(
            account_id=account_id,
            currency="CNY",
            cash=Decimal("96420"),
            available=Decimal("96000"),
            equity=Decimal("100120"),
            margin=Decimal("3700"),
            frozen=Decimal("0"),
            updated_at=updated_at,
        ),
        positions=(
            BrokerPositionSnapshot(
                account_id=account_id,
                symbol="ao",
                instrument_id="ao2609",
                trade_instrument_id="ao2609",
                exchange="SHFE",
                side="LONG",
                quantity=Decimal("1"),
                avg_price=Decimal("500"),
                market_value=Decimal("500"),
                unrealized_pnl=Decimal("20"),
                updated_at=updated_at,
            ),
            BrokerPositionSnapshot(
                account_id=account_id,
                symbol="rb",
                instrument_id="rb2601",
                trade_instrument_id="rb2601",
                exchange="SHFE",
                side="LONG",
                quantity=Decimal("1"),
                avg_price=Decimal("3200"),
                market_value=Decimal("3200"),
                unrealized_pnl=Decimal("100"),
                updated_at=updated_at,
            ),
        ),
        orders=(
            BrokerOrderSnapshot(
                account_id=account_id,
                order_id="po-ao-1",
                symbol="ao",
                instrument_id="ao2609",
                trade_instrument_id="ao2609",
                exchange="SHFE",
                side="BUY",
                order_status="FILLED",
                quantity=Decimal("1"),
                filled_quantity=Decimal("1"),
                price=Decimal("500"),
                created_at=updated_at,
                updated_at=updated_at,
            ),
        ),
        trades=(
            BrokerTradeSnapshot(
                account_id=account_id,
                trade_id="pf-ao-1",
                order_id="po-ao-1",
                symbol="ao",
                instrument_id="ao2609",
                trade_instrument_id="ao2609",
                exchange="SHFE",
                side="BUY",
                fill_price=Decimal("500"),
                fill_qty=Decimal("1"),
                fee=Decimal("0"),
                traded_at=updated_at,
            ),
        ),
    )


def _blocked(reason: str) -> BrokerReadOnlyResult:
    return BrokerReadOnlyResult(
        status=BrokerReadOnlyStatus.BLOCKED,
        reason=reason,
        diagnostics=(
            "已阻断",
            reason,
            "不自动重试",
            "不自动登录",
            "不报单",
            "不撤单",
            "不写数据库",
        ),
    )
