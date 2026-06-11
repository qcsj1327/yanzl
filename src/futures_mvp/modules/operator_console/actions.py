from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PlaceholderActionStatus(StrEnum):
    BLOCKED = "BLOCKED"
    PLACEHOLDER = "DISABLED"


@dataclass(frozen=True)
class ConsoleActionResult:
    status: PlaceholderActionStatus
    reason: str
    executed: bool = False


@dataclass(frozen=True)
class ConsoleActionDescriptor:
    action_key: str
    disabled: bool
    reason: str


PAPER_DRY_RUN_ACTION = ConsoleActionDescriptor(
    action_key="Run Paper Dry-run",
    disabled=False,
    reason="Stage R.2 placeholder only; no PaperLocalSession call is wired.",
)
PAPER_APPLY_ACTION = ConsoleActionDescriptor(
    action_key="Run Paper Apply",
    disabled=True,
    reason="Stage R.2 disables Paper apply; no local ledger write is possible.",
)
SIM_DRY_RUN_ACTION = ConsoleActionDescriptor(
    action_key="Run SIM Dry-run",
    disabled=False,
    reason="Stage R.2 placeholder only; no SimLocalSession call is wired.",
)
SIM_APPLY_ACTION = ConsoleActionDescriptor(
    action_key="Run SIM Apply",
    disabled=True,
    reason="Stage R.2 disables SIM apply; no local ledger write is possible.",
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
