from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import cast

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
    PAPER_SESSION = "Paper Session"
    SIM_SESSION = "SIM Session"
    SAFETY_CONTROLS = "Safety Controls"
    CONFIGURATION = "Configuration"
    RESULTS_HISTORY = "Results / History"
    DIAGNOSTICS = "Diagnostics"
    LIVE_LOCKED_PAGE = "Live Locked Page"


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
    runtime_status: str = "READY"
    rollout_mode: str = "PAPER"
    execution_target_status: str = "MOCK only"
    migration_status: str = "READY"
    kill_switch_status: str = "DISABLED"
    scheduler_pause_status: str = "READY"
    replay_pause_status: str = "READY"
    latest_paper_result: str = "DISABLED"
    latest_sim_result: str = "DISABLED"
    notices: tuple[str, ...] = (
        "mock only target",
        "no real capital",
        "no real exchange",
        "no ctp simnow",
        "targets disabled",
    )


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
        ("Static Fixture", "enabled"),
        ("Read-only Adapter Placeholder", "blocked/not configured"),
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
    paper: SessionPageViewModel
    sim: SessionPageViewModel
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
        paper=SessionPageViewModel(
            page=OperatorPage.PAPER_SESSION,
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
        sim=SessionPageViewModel(
            page=OperatorPage.SIM_SESSION,
            mode_name="SIM",
            dry_run_button=ButtonViewModel(
                action_key="Run SIM Dry-run",
                disabled=False,
                status=ConsoleActionStatus.ENABLED_PLACEHOLDER,
                reason="SIM dry-run placeholder only",
            ),
            apply_button=ButtonViewModel(
                action_key="Run SIM Apply",
                disabled=True,
                status=ConsoleActionStatus.DISABLED_PLACEHOLDER,
                reason="SIM apply is disabled in Stage R.2",
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
                ("pytest status", "unknown/not run"),
                ("ruff status", "unknown/not run"),
                ("mypy status", "unknown/not run"),
                ("alembic current", "unknown/not checked"),
                ("git commit/tag", "unknown/not checked"),
                ("worktree", "unknown/not checked"),
                ("DB health", "unknown/not checked"),
                ("Redis health", "unknown/not checked"),
                ("last error", "none"),
            )
        ),
        live_locked=LiveLockedViewModel(
            disabled_states=disabled_states,
            forbidden_actions=forbidden,
        ),
    )


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
