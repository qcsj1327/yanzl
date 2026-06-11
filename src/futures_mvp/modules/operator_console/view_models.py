from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


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


@dataclass(frozen=True)
class DiagnosticViewModel:
    items: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class LiveLockedViewModel:
    disabled_states: tuple[str, ...]
    forbidden_actions: tuple[ForbiddenActionViewModel, ...]


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
