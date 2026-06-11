from __future__ import annotations

from futures_mvp.modules.operator_console.view_models import (
    ForbiddenActionViewModel,
    SafetyControlViewModel,
    SafetyPageViewModel,
)


def safety_placeholder() -> SafetyPageViewModel:
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
    return SafetyPageViewModel(
        controls=(
            SafetyControlViewModel("Kill Switch", "DISABLED", "Enable Kill Switch"),
            SafetyControlViewModel("Scheduler Pause", "READY", "Pause Scheduler"),
            SafetyControlViewModel("Replay Pause", "READY", "Pause Replay"),
        ),
        disabled_states=(
            "Live Disabled",
            "Broker Disabled",
            "CTP Disabled",
            "SimNow Disabled",
            "MOCK only",
        ),
        forbidden_actions=forbidden,
    )
