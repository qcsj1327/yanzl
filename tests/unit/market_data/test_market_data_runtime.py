from __future__ import annotations

from datetime import date, datetime

from futures_mvp.modules.market_data.runtime import (
    MarketDataRuntime,
    MarketDataRuntimeConfig,
    MarketDataRuntimeStatus,
    SymbolPollStatus,
)


def test_runtime_default_does_not_start_or_call_akshare() -> None:
    client = _CountingAkShareClient()
    runtime = MarketDataRuntime(client=client)

    snapshot = runtime.health()

    assert snapshot.status is MarketDataRuntimeStatus.NOT_CONFIGURED
    assert snapshot.started is False
    assert snapshot.configured is False
    assert snapshot.network_call_occurred is False
    assert client.calls == []


def test_runtime_unconfigured_start_is_blocked() -> None:
    client = _CountingAkShareClient()
    runtime = MarketDataRuntime(client=client)

    snapshot = runtime.start()

    assert snapshot.status is MarketDataRuntimeStatus.BLOCKED
    assert snapshot.started is False
    assert snapshot.configured is False
    assert snapshot.network_call_occurred is False
    assert snapshot.latest_error == "真实行情运行时未配置：enabled=False"
    assert client.calls == []


def test_runtime_unconfigured_poll_once_is_blocked() -> None:
    client = _CountingAkShareClient()
    resolver = _ExplodingResolver()
    runtime = MarketDataRuntime(client=client, resolver=resolver)

    snapshot = runtime.poll_once(("ao",))
    latest = runtime.latest_snapshot()

    assert snapshot.status is MarketDataRuntimeStatus.BLOCKED
    assert latest.status is MarketDataRuntimeStatus.BLOCKED
    assert snapshot.network_call_occurred is False
    assert snapshot.latest_error == "行情运行时未配置或未启用，不能刷新"
    assert any("行情运行时未配置或未启用，不能刷新" in item for item in snapshot.diagnostics)
    assert resolver.calls == 0
    assert client.calls == []


def test_runtime_fake_akshare_poll_once_success_caches_latest_snapshot() -> None:
    client = _CountingAkShareClient()
    runtime = MarketDataRuntime(
        MarketDataRuntimeConfig(enabled=True, trading_day=date(2026, 6, 12)),
        client=client,
        now=datetime(2026, 6, 12, 9, 1),
    )

    runtime.start()
    snapshot = runtime.poll_once(("ao",))
    latest = runtime.latest_snapshot()

    assert snapshot.status is MarketDataRuntimeStatus.RUNNING
    assert snapshot.network_call_occurred is True
    assert snapshot.symbols[0].symbol == "ao"
    assert snapshot.symbols[0].status is SymbolPollStatus.OK
    assert snapshot.symbols[0].latest_quote is not None
    assert snapshot.symbols[0].latest_quote.instrument_id == "ao9999"
    assert snapshot.symbols[0].latest_quote.trade_instrument_id == "ao2609"
    assert snapshot.symbols[0].latest_bars_summary is not None
    assert snapshot.symbols[0].latest_bars_summary.count == 1
    assert latest.symbols == snapshot.symbols
    assert client.calls == [
        "spot:AO0",
        "bars:AO0:1",
    ]


def test_runtime_configured_but_never_started_poll_once_is_blocked() -> None:
    client = _CountingAkShareClient()
    resolver = _ExplodingResolver()
    runtime = MarketDataRuntime(
        MarketDataRuntimeConfig(enabled=True, trading_day=date(2026, 6, 12)),
        client=client,
        resolver=resolver,
    )

    snapshot = runtime.poll_once(("ao",))
    latest = runtime.latest_snapshot()

    assert snapshot.status is MarketDataRuntimeStatus.BLOCKED
    assert latest.status is MarketDataRuntimeStatus.BLOCKED
    assert snapshot.started is False
    assert snapshot.network_call_occurred is False
    assert snapshot.latest_error == "行情运行时未启动，需先启动后刷新"
    assert resolver.calls == 0
    assert client.calls == []


def test_runtime_single_symbol_failure_does_not_pollute_other_symbols() -> None:
    client = _CountingAkShareClient(fail_symbols={"RB0"})
    runtime = MarketDataRuntime(
        MarketDataRuntimeConfig(enabled=True, trading_day=date(2026, 6, 12)),
        client=client,
    )

    runtime.start()
    snapshot = runtime.poll_once(("ao", "rb"))
    by_symbol = {item.symbol: item for item in snapshot.symbols}

    assert snapshot.status is MarketDataRuntimeStatus.DEGRADED
    assert by_symbol["ao"].status is SymbolPollStatus.OK
    assert by_symbol["ao"].latest_quote is not None
    assert by_symbol["rb"].status is SymbolPollStatus.BLOCKED
    assert by_symbol["rb"].latest_quote is None
    assert snapshot.latest_error is not None
    assert snapshot.latest_error.startswith("rb:")


def test_runtime_stop_after_start_updates_status() -> None:
    runtime = MarketDataRuntime(
        MarketDataRuntimeConfig(enabled=True, trading_day=date(2026, 6, 12)),
        client=_CountingAkShareClient(),
    )

    runtime.start()
    snapshot = runtime.stop()

    assert snapshot.status is MarketDataRuntimeStatus.STOPPED
    assert snapshot.started is False
    assert snapshot.configured is True


def test_runtime_poll_once_after_stop_fails_closed_without_client_calls() -> None:
    client = _CountingAkShareClient()
    resolver = _ExplodingResolver()
    runtime = MarketDataRuntime(
        MarketDataRuntimeConfig(enabled=True, trading_day=date(2026, 6, 12)),
        client=client,
        resolver=resolver,
    )

    runtime.start()
    stopped = runtime.stop()
    snapshot = runtime.poll_once(("ao",))
    latest = runtime.latest_snapshot()

    assert stopped.status is MarketDataRuntimeStatus.STOPPED
    assert snapshot.status is MarketDataRuntimeStatus.STOPPED
    assert latest.status is MarketDataRuntimeStatus.STOPPED
    assert snapshot.started is False
    assert snapshot.network_call_occurred is False
    assert snapshot.latest_error == "行情运行时已停止，需重新启动后刷新"
    assert any("未启动" in item or "已停止" in item for item in snapshot.diagnostics)
    assert resolver.calls == 0
    assert client.calls == []


class _ExplodingResolver:
    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, symbol: str, trading_day: date) -> object:
        self.calls += 1
        raise RuntimeError("不应调用 resolver")


class _CountingAkShareClient:
    def __init__(self, fail_symbols: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self.fail_symbols = fail_symbols or set()

    def futures_display_main_sina(self) -> list[dict[str, object]]:
        self.calls.append("display")
        return [
            {"symbol": "AO0", "exchange": "SHFE"},
            {"symbol": "RB0", "exchange": "SHFE"},
        ]

    def match_main_contract(self, symbol: str) -> str:
        self.calls.append(f"match:{symbol}")
        return f"{symbol.upper()}0"

    def futures_zh_spot(
        self,
        symbol: str,
        market: str = "CF",
        adjust: str = "0",
    ) -> list[dict[str, object]]:
        self.calls.append(f"spot:{symbol}")
        if symbol in self.fail_symbols:
            raise RuntimeError("接口错误")
        contract = "ao2609" if symbol == "AO0" else "rb2610"
        return [
            {
                "symbol": contract,
                "current_price": "3205",
                "volume": "10",
                "hold": "20",
                "bid_price": "3204",
                "ask_price": "3206",
            }
        ]

    def futures_zh_minute_sina(self, symbol: str, period: str) -> list[dict[str, object]]:
        self.calls.append(f"bars:{symbol}:{period}")
        if symbol in self.fail_symbols:
            raise RuntimeError("接口错误")
        return [
            {
                "datetime": "2026-06-12 09:01:00",
                "open": "3200",
                "high": "3210",
                "low": "3190",
                "close": "3205",
                "volume": "10",
                "hold": "20",
            }
        ]

    def futures_zh_daily_sina(self, symbol: str) -> list[dict[str, object]]:
        self.calls.append(f"daily:{symbol}")
        return self.futures_zh_minute_sina(symbol, "1")
