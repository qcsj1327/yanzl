from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import cast

from futures_mvp.modules.market_data.runtime import (
    MarketDataRuntimeSnapshot,
    MarketDataRuntimeStatus,
    RuntimeBarsSummary,
    RuntimeQuoteSnapshot,
    SymbolRuntimeSnapshot,
)
from futures_mvp.modules.operator_console.config_assembly import (
    READ_ONLY_ADAPTER_DATA_SOURCE,
    STATIC_FIXTURE_DATA_SOURCE,
    CommandPreview,
    ConfigValidationResult,
    ConsoleDryRunConfig,
    DryRunHistoryEntry,
)


class OperatorPage(StrEnum):
    DASHBOARD = "Dashboard"
    RESEARCH = "Research"
    PORTFOLIO = "Portfolio"
    PAPER = "Paper"
    MARKET_DATA = "Market Data"
    DIAGNOSTICS = "Diagnostics"


class ConsoleActionStatus(StrEnum):
    ENABLED_PLACEHOLDER = "ENABLED_PLACEHOLDER"
    DISABLED_PLACEHOLDER = "DISABLED_PLACEHOLDER"


@dataclass(frozen=True)
class ButtonViewModel:
    action_key: str
    disabled: bool
    status: ConsoleActionStatus
    reason: str


@dataclass(frozen=True)
class DashboardViewModel:
    research_status: str = "READY"
    paper_runtime_status: str = "READY"
    portfolio_status: str = "READY"
    market_data_status: str = "READY"
    diagnostics_status: str = "READY"
    current_source: str = STATIC_FIXTURE_DATA_SOURCE
    execution_target_status: str = "MOCK only"
    latest_dry_run_summary: str = "尚未运行"
    notices: tuple[str, ...] = (
        "mock only target",
        "research only",
        "no real capital",
        "no real exchange",
        "no ctp simnow",
        "targets disabled",
    )


@dataclass(frozen=True)
class ResearchViewModel:
    backtest_status: str
    strategy: str
    symbols: tuple[str, ...]
    orders: tuple[tuple[str, str], ...]
    trades: tuple[tuple[str, str], ...]
    positions: tuple[tuple[str, str], ...]
    realized_pnl: str
    unrealized_pnl: str
    equity_curve_summary: tuple[tuple[str, str], ...]
    metrics: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PortfolioViewModel:
    cash: str
    equity: str
    market_value: str
    positions: tuple[tuple[str, str], ...]
    symbol_contributions: tuple[tuple[str, str], ...]
    position_weights: tuple[tuple[str, str], ...]
    cash_weight: str
    allocation: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PaperConsolePageViewModel:
    runtime_status: str
    lifecycle: tuple[tuple[str, str], ...]
    orders: tuple[tuple[str, str], ...]
    fills: tuple[tuple[str, str], ...]
    positions: tuple[tuple[str, str], ...]
    portfolio: tuple[tuple[str, str], ...]
    consistency: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class MarketDataViewModel:
    selected_source: str
    static_fixture_status: str
    read_only_adapter_status: str
    connection_status: str
    configuration_status: str
    runtime_status: str
    runtime_started: str
    runtime_configured: str
    resolver_source: str
    blocked_reason: str | None
    supported_symbols: tuple[str, ...]
    symbol_statuses: tuple[tuple[str, str], ...]
    diagnostics: tuple[tuple[str, str], ...]
    latest_quote: tuple[tuple[str, str], ...] = ()
    latest_bars: tuple[tuple[str, str], ...] = ()
    updated_at: str = "未更新"


@dataclass(frozen=True)
class SessionPageViewModel:
    page: OperatorPage
    mode_name: str
    target: str = "MOCK only"
    dry_run_button: ButtonViewModel = field(
        default_factory=lambda: ButtonViewModel(
            action_key="Run Paper Dry-run",
            disabled=False,
            status=ConsoleActionStatus.ENABLED_PLACEHOLDER,
            reason="placeholder only",
        )
    )
    apply_button: ButtonViewModel = field(
        default_factory=lambda: ButtonViewModel(
            action_key="Run Paper Apply",
            disabled=True,
            status=ConsoleActionStatus.DISABLED_PLACEHOLDER,
            reason="apply placeholder is disabled in Stage R.2",
        )
    )
    view_result_button: ButtonViewModel = field(
        default_factory=lambda: ButtonViewModel(
            action_key="View Result",
            disabled=False,
            status=ConsoleActionStatus.ENABLED_PLACEHOLDER,
            reason="placeholder only",
        )
    )
    notices: tuple[str, ...] = (
        "dry-run no db write",
        "apply writes local ledger",
        "mock only target",
        "danger requires confirmation",
    )


@dataclass(frozen=True)
class SafetyControlViewModel:
    label_key: str
    status: str
    button_key: str
    disabled: bool = False


@dataclass(frozen=True)
class ForbiddenActionViewModel:
    label_key: str
    clickable: bool = False


@dataclass(frozen=True)
class SafetyPageViewModel:
    controls: tuple[SafetyControlViewModel, ...]
    disabled_states: tuple[str, ...]
    forbidden_actions: tuple[ForbiddenActionViewModel, ...]


@dataclass(frozen=True)
class ConfigurationViewModel:
    normal: tuple[tuple[str, str], ...]
    advanced: tuple[tuple[str, str], ...]
    sources: tuple[str, ...]
    dry_run_config: ConsoleDryRunConfig = field(default_factory=ConsoleDryRunConfig)
    preview: CommandPreview | None = None
    validation: ConfigValidationResult = field(
        default_factory=lambda: ConfigValidationResult(
            blocked=True,
            reason="缺少必填配置",
            missing_fields=(
                "account_id",
                "trading_day",
                "symbol",
            ),
        )
    )
    market_data_sources: tuple[tuple[str, str], ...] = (
        ("静态样例", "可用"),
        ("只读适配器", "已阻断/未配置"),
    )
    dry_run_required: tuple[tuple[str, str], ...] = (
        ("account_id", "未配置"),
        ("trading_day", "未配置"),
        ("symbol", "未配置"),
        ("resolver_status", "未解析"),
        ("quantity", "未配置"),
        ("price", "未配置"),
        ("instrument whitelist", "未配置"),
        ("max order size", "未配置"),
        ("max position size", "未配置"),
        ("max daily loss", "未配置"),
        ("command source / typed command provider", "未配置"),
        ("market_data_source", STATIC_FIXTURE_DATA_SOURCE),
        ("job_factory", "未配置"),
    )


@dataclass(frozen=True)
class ResultHistoryViewModel:
    items: tuple[tuple[str, str], ...]
    session_status: str = "NOT_RUN"
    job_status: str = "NOT_RUN"
    run_status: str = "NOT_RUN"
    db_delta: int = 0
    target: str = "MOCK only"
    latest_run: str = "无"
    reason: str | None = None
    history: tuple[DryRunHistoryEntry, ...] = ()


@dataclass(frozen=True)
class DiagnosticViewModel:
    items: tuple[tuple[str, str], ...]
    resolver: tuple[tuple[str, str], ...] = ()
    market_data: tuple[tuple[str, str], ...] = ()
    research: tuple[tuple[str, str], ...] = ()
    paper: tuple[tuple[str, str], ...] = ()
    safety: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class LiveLockedViewModel:
    disabled_states: tuple[str, ...]
    forbidden_actions: tuple[ForbiddenActionViewModel, ...]


@dataclass(frozen=True)
class PaperRuntimeConsoleViewModel:
    status: str
    reason: str | None
    equity: str
    portfolio: tuple[tuple[str, str], ...]
    orders: tuple[tuple[str, str], ...]
    fills: tuple[tuple[str, str], ...]
    positions: tuple[tuple[str, str], ...]
    allocation: tuple[tuple[str, str], ...]
    consistency: tuple[tuple[str, str], ...]
    source: str = "operator_console_paper_runtime_view"


@dataclass(frozen=True)
class OperatorConsoleViewModel:
    pages: tuple[OperatorPage, ...]
    dashboard: DashboardViewModel
    research: ResearchViewModel
    portfolio: PortfolioViewModel
    paper_page: PaperConsolePageViewModel
    market_data: MarketDataViewModel
    paper: SessionPageViewModel
    safety: SafetyPageViewModel
    configuration: ConfigurationViewModel
    results: ResultHistoryViewModel
    diagnostics: DiagnosticViewModel
    live_locked: LiveLockedViewModel


def paper_runtime_console_view(result: object) -> PaperRuntimeConsoleViewModel:
    status = str(getattr(result, "status", "UNKNOWN"))
    reason = getattr(result, "reason", None)
    portfolio = getattr(result, "portfolio", None)
    consistency = getattr(result, "consistency", None)
    return PaperRuntimeConsoleViewModel(
        status=status,
        reason=reason if isinstance(reason, str) else None,
        equity=_decimal_text(getattr(portfolio, "equity", Decimal("0"))),
        portfolio=_paper_portfolio_rows(portfolio),
        orders=_paper_order_rows(cast(Iterable[object], getattr(result, "orders", ()))),
        fills=_paper_fill_rows(cast(Iterable[object], getattr(result, "fills", ()))),
        positions=_paper_position_rows(
            cast(Iterable[object], getattr(result, "positions", ()))
        ),
        allocation=_paper_allocation_rows(
            cast(Iterable[object], getattr(portfolio, "allocation", ()))
        ),
        consistency=_paper_consistency_rows(consistency),
    )


def default_console_view_model() -> OperatorConsoleViewModel:
    forbidden = tuple(
        ForbiddenActionViewModel(key)
        for key in (
            "LIVE Enable",
            "Broker Enable",
            "CTP Connect",
            "SimNow Connect",
            "Real Capital Trading",
            "Manual Order Edit",
            "Manual Trade Edit",
            "Manual Position Edit",
            "Manual Ledger Edit",
        )
    )
    disabled_states = (
        "Live Disabled",
        "Broker Disabled",
        "CTP Disabled",
        "SimNow Disabled",
        "MOCK only",
    )
    return OperatorConsoleViewModel(
        pages=tuple(OperatorPage),
        dashboard=DashboardViewModel(),
        research=ResearchViewModel(
            backtest_status="COMPLETED",
            strategy="sample_breakout_research",
            symbols=("ao", "rb", "ag", "cu"),
            orders=(
                ("o-ao-1", "ao / ao2609 / BUY / FILLED / 1"),
                ("o-rb-1", "rb / rb2601 / BUY / FILLED / 1"),
            ),
            trades=(
                ("t-ao-1", "ao / ao2609 / 500 / 1"),
                ("t-rb-1", "rb / rb2601 / 3200 / 1"),
            ),
            positions=(
                ("ao", "ao2609 / LONG / 1 / 市值 500"),
                ("rb", "rb2601 / LONG / 1 / 市值 3200"),
            ),
            realized_pnl="0",
            unrealized_pnl="120",
            equity_curve_summary=(
                ("points", "3"),
                ("first_equity", "100000"),
                ("last_equity", "100120"),
            ),
            metrics=(
                ("total_return", "0.0012"),
                ("max_equity", "100120"),
                ("min_equity", "100000"),
            ),
        ),
        portfolio=PortfolioViewModel(
            cash="96420",
            equity="100120",
            market_value="3700",
            positions=(
                ("ao", "ao2609 / 数量 1 / 市值 500"),
                ("rb", "rb2601 / 数量 1 / 市值 3200"),
            ),
            symbol_contributions=(
                ("ao", "市值 500 / PnL 20"),
                ("rb", "市值 3200 / PnL 100"),
            ),
            position_weights=(
                ("ao", "0.0050"),
                ("rb", "0.0320"),
            ),
            cash_weight="0.9630",
            allocation=(
                ("cash", "96.30%"),
                ("ao", "0.50%"),
                ("rb", "3.20%"),
            ),
        ),
        paper_page=PaperConsolePageViewModel(
            runtime_status="READY",
            lifecycle=(
                ("run", "dry-run only"),
                ("pause", "展示占位"),
                ("stop", "展示占位"),
            ),
            orders=(
                ("po-ao-1", "ao / ao2609 / CREATED"),
                ("po-rb-1", "rb / rb2601 / CREATED"),
            ),
            fills=(
                ("pf-ao-1", "ao / 500 / 1"),
                ("pf-rb-1", "rb / 3200 / 1"),
            ),
            positions=(
                ("ao", "ao2609 / 1 / 市值 500"),
                ("rb", "rb2601 / 1 / 市值 3200"),
            ),
            portfolio=(
                ("cash", "96420"),
                ("equity", "100120"),
                ("market_value", "3700"),
            ),
            consistency=(
                ("all_match", "True"),
                ("cash_matches", "True"),
                ("equity_matches", "True"),
                ("positions_match", "True"),
                ("orders_match", "True"),
                ("fills_match", "True"),
            ),
        ),
        market_data=MarketDataViewModel(
            selected_source=STATIC_FIXTURE_DATA_SOURCE,
            static_fixture_status="可用",
            read_only_adapter_status="已阻断",
            connection_status="未连接",
            configuration_status="未配置",
            runtime_status=MarketDataRuntimeStatus.NOT_CONFIGURED.value,
            runtime_started="否",
            runtime_configured="否",
            resolver_source="static_fixture",
            blocked_reason="只读行情适配器未配置，不会访问网络",
            supported_symbols=("ao", "rb", "ag", "cu"),
            symbol_statuses=(
                ("ao", "未刷新"),
                ("rb", "未刷新"),
                ("ag", "未刷新"),
                ("cu", "未刷新"),
            ),
            latest_quote=(("状态", "无真实行情"),),
            latest_bars=(("状态", "无真实 K 线"),),
            updated_at="未更新",
            diagnostics=(
                ("数据源", "static_fixture"),
                ("网络", "不会访问网络"),
                ("Broker", "禁用"),
                ("解析器", "静态夹具"),
            ),
        ),
        paper=SessionPageViewModel(
            page=OperatorPage.PAPER,
            mode_name="PAPER",
            dry_run_button=ButtonViewModel(
                action_key="Run Paper Dry-run",
                disabled=False,
                status=ConsoleActionStatus.ENABLED_PLACEHOLDER,
                reason="Paper dry-run placeholder only",
            ),
            apply_button=ButtonViewModel(
                action_key="Run Paper Apply",
                disabled=True,
                status=ConsoleActionStatus.DISABLED_PLACEHOLDER,
                reason="Paper apply is disabled in Stage R.2",
            ),
        ),
        safety=SafetyPageViewModel(
            controls=(
                SafetyControlViewModel("Kill Switch", "DISABLED", "Enable Kill Switch"),
                SafetyControlViewModel("Scheduler Pause", "READY", "Pause Scheduler"),
                SafetyControlViewModel("Replay Pause", "READY", "Pause Replay"),
            ),
            disabled_states=disabled_states,
            forbidden_actions=forbidden,
        ),
        configuration=ConfigurationViewModel(
            normal=(
                ("account_id", "未配置"),
                ("trading_day", "未配置"),
                ("instrument whitelist", "未配置"),
                ("max order size", "未配置"),
                ("max position size", "未配置"),
                ("max daily loss", "未配置"),
                ("Paper/SIM mode", "PAPER"),
                ("dry-run/apply", "dry-run"),
                ("market data source", "Static Fixture"),
            ),
            advanced=(
                ("runtime_id", "未配置"),
                ("config_hash", "未配置"),
                ("migration revision", "未配置"),
                ("capital control details", "未配置"),
            ),
            sources=(
                "typed config object",
                "local TOML/YAML",
                "environment variables",
                "UI session state",
                f"{STATIC_FIXTURE_DATA_SOURCE} enabled",
                f"{READ_ONLY_ADAPTER_DATA_SOURCE} blocked/not configured",
            ),
        ),
        results=ResultHistoryViewModel(
            items=(
                ("execution reports", "DISABLED"),
                ("order status", "DISABLED"),
                ("trades", "DISABLED"),
                ("position updates", "DISABLED"),
                ("margin calculation", "DISABLED"),
                ("pnl calculation", "DISABLED"),
                ("settlement snapshot", "DISABLED"),
                ("duplicate detection", "DISABLED"),
                ("db delta", "0"),
                ("target type", "MOCK only"),
            )
        ),
        diagnostics=DiagnosticViewModel(
            items=(
                ("git commit/tag", "unknown/not checked"),
                ("worktree", "unknown/not checked"),
                ("last error", "none"),
            ),
            resolver=(
                ("resolver_status", "READY"),
                ("resolver_source", "static_fixture"),
                ("supported_symbols", "ao, rb, ag, cu"),
            ),
            market_data=(
                ("selected_source", STATIC_FIXTURE_DATA_SOURCE),
                ("read_only_adapter", "已阻断"),
                ("network", "不会访问网络"),
            ),
            research=(
                ("backtest_status", "COMPLETED"),
                ("source_of_truth", "research only"),
            ),
            paper=(
                ("PaperResearchRuntime", "READY"),
                ("PaperConsistencyReport", "all_match=True"),
            ),
            safety=(
                ("ExecutionTarget", "MOCK only"),
                ("DB write", "disabled"),
                ("live trading", "disabled"),
                ("broker/CTP/SimNow", "disabled"),
            ),
        ),
        live_locked=LiveLockedViewModel(
            disabled_states=disabled_states,
            forbidden_actions=forbidden,
        ),
    )


def market_data_view_model_from_snapshot(
    snapshot: MarketDataRuntimeSnapshot,
) -> MarketDataViewModel:
    blocked_reason = snapshot.latest_error
    if blocked_reason is None and not snapshot.configured:
        blocked_reason = "真实行情运行时未配置，不会访问网络"
    return MarketDataViewModel(
        selected_source=snapshot.source,
        static_fixture_status="可用",
        read_only_adapter_status=_adapter_status(snapshot),
        connection_status="已启动" if snapshot.started else "未连接",
        configuration_status="已配置" if snapshot.configured else "未配置",
        runtime_status=snapshot.status.value,
        runtime_started="是" if snapshot.started else "否",
        runtime_configured="是" if snapshot.configured else "否",
        resolver_source="InstrumentResolver",
        blocked_reason=blocked_reason,
        supported_symbols=("ao", "rb", "ag", "cu"),
        symbol_statuses=_symbol_status_rows(snapshot.symbols),
        latest_quote=_latest_quote_rows(snapshot.symbols),
        latest_bars=_latest_bars_rows(snapshot.symbols),
        updated_at=_datetime_text(snapshot.updated_at),
        diagnostics=(
            ("数据源", snapshot.source),
            ("akshare_available", str(snapshot.akshare_available)),
            ("network_call_occurred", "是" if snapshot.network_call_occurred else "否"),
            ("latest_error", snapshot.latest_error or "无"),
            *tuple(("diagnostics", item) for item in snapshot.diagnostics),
        ),
    )


def _adapter_status(snapshot: MarketDataRuntimeSnapshot) -> str:
    if snapshot.status is MarketDataRuntimeStatus.RUNNING:
        return "运行中"
    if snapshot.status is MarketDataRuntimeStatus.DEGRADED:
        return "降级"
    if snapshot.status is MarketDataRuntimeStatus.BLOCKED:
        return "已阻断"
    if snapshot.configured:
        return "已配置"
    return "已阻断"


def _symbol_status_rows(
    symbols: tuple[SymbolRuntimeSnapshot, ...],
) -> tuple[tuple[str, str], ...]:
    if not symbols:
        return (
            ("ao", "未刷新"),
            ("rb", "未刷新"),
            ("ag", "未刷新"),
            ("cu", "未刷新"),
        )
    return tuple((item.symbol, item.status.value) for item in symbols)


def _latest_quote_rows(
    symbols: tuple[SymbolRuntimeSnapshot, ...],
) -> tuple[tuple[str, str], ...]:
    rows = []
    for item in symbols:
        if item.latest_quote is None:
            rows.append((item.symbol, "无最近报价"))
            continue
        rows.append((item.symbol, _quote_text(item.latest_quote)))
    return tuple(rows) or (("状态", "无真实行情"),)


def _latest_bars_rows(
    symbols: tuple[SymbolRuntimeSnapshot, ...],
) -> tuple[tuple[str, str], ...]:
    rows = []
    for item in symbols:
        if item.latest_bars_summary is None:
            rows.append((item.symbol, "无 K 线摘要"))
            continue
        rows.append((item.symbol, _bars_text(item.latest_bars_summary)))
    return tuple(rows) or (("状态", "无真实 K 线"),)


def _quote_text(quote: RuntimeQuoteSnapshot) -> str:
    return (
        f"{quote.trade_instrument_id} / 最近价 {quote.last_price} / "
        f"成交量 {quote.volume} / {quote.ts.isoformat()}"
    )


def _bars_text(summary: RuntimeBarsSummary) -> str:
    return (
        f"{summary.trade_instrument_id} / {summary.timeframe.value} / "
        f"数量 {summary.count} / 最新收盘 {summary.last_close}"
    )


def _datetime_text(value: object | None) -> str:
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return "未更新"


def _paper_portfolio_rows(portfolio: object | None) -> tuple[tuple[str, str], ...]:
    if portfolio is None:
        return ()
    return (
        ("cash", _decimal_text(getattr(portfolio, "cash", Decimal("0")))),
        ("equity", _decimal_text(getattr(portfolio, "equity", Decimal("0")))),
        ("position_count", str(len(getattr(portfolio, "positions", ())))),
    )


def _paper_order_rows(orders: Iterable[object]) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            str(getattr(order, "order_id", "")),
            "|".join(
                (
                    str(getattr(order, "symbol", "")),
                    str(getattr(order, "trade_instrument_id", "")),
                    _decimal_text(getattr(order, "quantity", Decimal("0"))),
                    str(getattr(order, "status", "")),
                )
            ),
        )
        for order in orders
    )


def _paper_fill_rows(fills: Iterable[object]) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            str(getattr(fill, "fill_id", "")),
            "|".join(
                (
                    str(getattr(fill, "symbol", "")),
                    str(getattr(fill, "trade_instrument_id", "")),
                    _decimal_text(getattr(fill, "fill_price", Decimal("0"))),
                    _decimal_text(getattr(fill, "fill_qty", Decimal("0"))),
                )
            ),
        )
        for fill in fills
    )


def _paper_position_rows(positions: Iterable[object]) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            str(getattr(position, "symbol", "")),
            "|".join(
                (
                    str(getattr(position, "trade_instrument_id", "")),
                    _decimal_text(getattr(position, "quantity", Decimal("0"))),
                    _decimal_text(getattr(position, "market_value", Decimal("0"))),
                )
            ),
        )
        for position in positions
    )


def _paper_allocation_rows(allocation: Iterable[object]) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            str(getattr(item, "symbol", "")),
            _decimal_text(getattr(item, "allocation", Decimal("0"))),
        )
        for item in allocation
    )


def _paper_consistency_rows(consistency: object | None) -> tuple[tuple[str, str], ...]:
    if consistency is None:
        return ()
    return (
        ("all_match", str(getattr(consistency, "all_match", False))),
        ("cash_matches", str(getattr(consistency, "cash_matches", False))),
        ("equity_matches", str(getattr(consistency, "equity_matches", False))),
        ("positions_match", str(getattr(consistency, "positions_match", False))),
        ("orders_match", str(getattr(consistency, "orders_match", False))),
        ("fills_match", str(getattr(consistency, "fills_match", False))),
    )


def _decimal_text(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)
