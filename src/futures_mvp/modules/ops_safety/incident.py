from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OpsIncidentState(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"
    KILLED = "KILLED"


@dataclass(frozen=True)
class OpsGateDecision:
    allowed: bool
    incident_state: OpsIncidentState
    reason: str | None = None
    blocked_stage: str | None = None

