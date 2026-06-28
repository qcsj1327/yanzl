from datetime import UTC, datetime
from decimal import Decimal

from futures_mvp.modules.broker_adapter import (
    BrokerAccountSnapshot,
    BrokerLoginError,
    BrokerNetworkError,
    BrokerReadOnlyAdapter,
    BrokerReadOnlyStatus,
    BrokerSnapshot,
    InMemoryBrokerSnapshotSource,
    sample_broker_snapshot,
)


class FailingSource:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def read_snapshot(self, account_id: str) -> BrokerSnapshot:
        self.calls += 1
        raise self.error


def test_read_only_adapter_returns_account_position_order_and_trade_snapshots() -> None:
    snapshot = sample_broker_snapshot()
    adapter = BrokerReadOnlyAdapter(
        source=InMemoryBrokerSnapshotSource((snapshot,)),
        configured=True,
    )

    result = adapter.snapshot("account-1")

    assert result.status is BrokerReadOnlyStatus.READY
    assert result.account == snapshot.account
    assert result.positions == snapshot.positions
    assert result.orders == snapshot.orders
    assert result.trades == snapshot.trades
    assert result.positions
    assert result.orders
    assert result.trades
    assert "不报单" in result.diagnostics
    assert "不撤单" in result.diagnostics
    assert adapter.read_attempts == 1


def test_read_only_adapter_blocks_when_not_configured_without_read_attempt() -> None:
    adapter = BrokerReadOnlyAdapter()

    result = adapter.snapshot("account-1")

    assert result.status is BrokerReadOnlyStatus.BLOCKED
    assert result.reason == "Broker 只读适配器未配置"
    assert adapter.read_attempts == 0
    assert "不写数据库" in result.diagnostics


def test_read_only_adapter_blocks_missing_account() -> None:
    adapter = BrokerReadOnlyAdapter(
        source=InMemoryBrokerSnapshotSource((_snapshot(),)),
        configured=True,
    )

    result = adapter.snapshot("missing-account")

    assert result.status is BrokerReadOnlyStatus.BLOCKED
    assert result.reason == "Broker 账户不存在"
    assert adapter.read_attempts == 1


def test_read_only_adapter_blocks_network_or_login_errors_without_retry() -> None:
    for error, reason in (
        (BrokerNetworkError("网络错误"), "Broker 网络错误"),
        (BrokerLoginError("登录失败"), "Broker 登录失败"),
    ):
        source = FailingSource(error)
        adapter = BrokerReadOnlyAdapter(source=source, configured=True)

        result = adapter.snapshot("account-1")

        assert result.status is BrokerReadOnlyStatus.BLOCKED
        assert result.reason == reason
        assert source.calls == 1
        assert adapter.read_attempts == 1


def test_individual_read_methods_remain_read_only() -> None:
    snapshot = _snapshot()
    adapter = BrokerReadOnlyAdapter(
        source=InMemoryBrokerSnapshotSource((snapshot,)),
        configured=True,
    )

    assert adapter.account("account-1").account == snapshot.account
    assert adapter.positions("account-1").positions == snapshot.positions
    assert adapter.orders("account-1").orders == snapshot.orders
    assert adapter.trades("account-1").trades == snapshot.trades


def _snapshot() -> BrokerSnapshot:
    updated_at = datetime(2026, 6, 28, tzinfo=UTC)
    return BrokerSnapshot(
        account=BrokerAccountSnapshot(
            account_id="account-1",
            currency="CNY",
            cash=Decimal("100"),
            available=Decimal("90"),
            equity=Decimal("120"),
            margin=Decimal("20"),
            frozen=Decimal("0"),
            updated_at=updated_at,
        )
    )
