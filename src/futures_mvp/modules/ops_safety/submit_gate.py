from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from futures_mvp.modules.ops_safety.config import SafetyConfig
from futures_mvp.modules.ops_safety.incident import OpsGateDecision, OpsIncidentState
from futures_mvp.modules.ops_safety.kill_switch import evaluate_broker_gate
from futures_mvp.modules.ops_safety.migration import MigrationReadinessReport


@dataclass(frozen=True)
class OperatorApproval:
    environment: str
    account_id: str
    adapter_target: str
    allowed_stage: str
    command_surface: str
    approved_at: datetime
    decision_id: str
    operator_id: str | None = None

    def __post_init__(self) -> None:
        if not self.environment:
            raise ValueError("approval environment is required")
        if not self.account_id:
            raise ValueError("approval account_id is required")
        if not self.adapter_target:
            raise ValueError("approval adapter_target is required")
        if not self.allowed_stage:
            raise ValueError("approval allowed_stage is required")
        if not self.command_surface:
            raise ValueError("approval command_surface is required")
        if not self.decision_id:
            raise ValueError("approval decision_id is required")


def validate_live_submit_gate(
    *,
    config: SafetyConfig,
    environment: str,
    account_id: str,
    adapter_target: str,
    stage_name: str,
    command_surface: str,
    approval: OperatorApproval | None,
    migration: MigrationReadinessReport,
) -> OpsGateDecision:
    try:
        config.validate_environment(environment)
    except ValueError as exc:
        return _failed(str(exc))
    if not config.live_gate.explicit_live_flag:
        return _failed("explicit live flag is required")
    broker_gate = evaluate_broker_gate(config)
    if not broker_gate.allowed:
        return broker_gate
    if not config.live_gate.live_submit_enabled:
        return _failed("live submit is disabled")
    if not migration.compatible:
        return _failed("migration readiness is incompatible")
    if approval is None:
        return _failed("operator approval is required")
    if approval.environment != environment:
        return _failed("operator approval environment mismatch")
    if approval.account_id != account_id:
        return _failed("operator approval account mismatch")
    if approval.adapter_target != adapter_target:
        return _failed("operator approval adapter target mismatch")
    if approval.allowed_stage != stage_name:
        return _failed("operator approval stage mismatch")
    if approval.command_surface != command_surface:
        return _failed("operator approval command surface mismatch")
    return OpsGateDecision(allowed=True, incident_state=OpsIncidentState.READY)


def _failed(reason: str) -> OpsGateDecision:
    return OpsGateDecision(
        allowed=False,
        incident_state=OpsIncidentState.FAILED,
        reason=reason,
    )

