from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class PlaceholderActionStatus(StrEnum):
    BLOCKED = "BLOCKED"
    PLACEHOLDER = "DISABLED"
    DRY_RUN_COMPLETED = "DRY_RUN_COMPLETED"


@dataclass(frozen=True)
class ConsoleActionDescriptor:
    action_key: str
    disabled: bool
    reason: str


@dataclass(frozen=True)
class DryRunActionResult:
    session_status: str
    job_status: str
    run_status: str
    db_delta: int = 0
    target: str = "MOCK only"
    reason: str | None = None


DryRunProvider = Callable[[], DryRunActionResult]


@dataclass(frozen=True)
class ConsoleActionResult:
    status: PlaceholderActionStatus
    reason: str
    executed: bool = False
    dry_run_result: DryRunActionResult | None = None


PAPER_DRY_RUN_ACTION = ConsoleActionDescriptor(
    action_key="Run Paper Dry-run",
    disabled=False,
    reason="Paper dry-run uses injected provider only.",
)
PAPER_APPLY_ACTION = ConsoleActionDescriptor(
    action_key="Run Paper Apply",
    disabled=True,
    reason="Stage R.4 disables Paper apply; no local ledger write is possible.",
)
SIM_DRY_RUN_ACTION = ConsoleActionDescriptor(
    action_key="Run SIM Dry-run",
    disabled=False,
    reason="SIM dry-run uses injected provider only.",
)
SIM_APPLY_ACTION = ConsoleActionDescriptor(
    action_key="Run SIM Apply",
    disabled=True,
    reason="Stage R.4 disables SIM apply; no local ledger write is possible.",
)


def run_placeholder_action(descriptor: ConsoleActionDescriptor) -> ConsoleActionResult:
    if descriptor.disabled:
        return ConsoleActionResult(
            status=PlaceholderActionStatus.BLOCKED,
            reason=descriptor.reason,
            executed=False,
        )
    return ConsoleActionResult(
        status=PlaceholderActionStatus.PLACEHOLDER,
        reason=descriptor.reason,
        executed=False,
    )


def run_paper_dry_run(provider: DryRunProvider | None = None) -> ConsoleActionResult:
    return _run_dry_run(PAPER_DRY_RUN_ACTION, provider)


def run_sim_dry_run(provider: DryRunProvider | None = None) -> ConsoleActionResult:
    return _run_dry_run(SIM_DRY_RUN_ACTION, provider)


def run_apply_placeholder(descriptor: ConsoleActionDescriptor) -> ConsoleActionResult:
    return ConsoleActionResult(
        status=PlaceholderActionStatus.BLOCKED,
        reason=descriptor.reason,
        executed=False,
    )


def _run_dry_run(
    descriptor: ConsoleActionDescriptor,
    provider: DryRunProvider | None,
) -> ConsoleActionResult:
    if provider is None:
        return ConsoleActionResult(
            status=PlaceholderActionStatus.BLOCKED,
            reason="dry-run provider is not configured",
            executed=False,
        )
    dry_run_result = provider()
    blocked_reason = _unsafe_dry_run_reason(dry_run_result)
    if blocked_reason is not None:
        return ConsoleActionResult(
            status=PlaceholderActionStatus.BLOCKED,
            reason=blocked_reason,
            executed=True,
            dry_run_result=DryRunActionResult(
                session_status=PlaceholderActionStatus.BLOCKED.value,
                job_status=PlaceholderActionStatus.BLOCKED.value,
                run_status=PlaceholderActionStatus.BLOCKED.value,
                db_delta=dry_run_result.db_delta,
                target=dry_run_result.target,
                reason=blocked_reason,
            ),
        )
    return ConsoleActionResult(
        status=PlaceholderActionStatus.DRY_RUN_COMPLETED,
        reason=descriptor.reason,
        executed=True,
        dry_run_result=dry_run_result,
    )


def _unsafe_dry_run_reason(result: DryRunActionResult) -> str | None:
    if result.target not in {"MOCK only", "MOCK"}:
        return "dry-run returned non-MOCK target"
    if result.db_delta != 0:
        return "dry-run returned non-zero DB delta"
    return None
