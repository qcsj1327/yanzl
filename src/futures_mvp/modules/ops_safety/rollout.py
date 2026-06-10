from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from futures_mvp.modules.ops_safety.config import (
    RolloutMode,
    SafetyConfig,
)
from futures_mvp.modules.ops_safety.incident import OpsGateDecision, OpsIncidentState
from futures_mvp.modules.ops_safety.kill_switch import (
    evaluate_replay_gate,
    evaluate_scheduler_gate,
)
from futures_mvp.modules.ops_safety.migration import MigrationReadinessReport
from futures_mvp.modules.ops_safety.submit_gate import (
    OperatorApproval,
    validate_live_submit_gate,
)


class CapitalControlStatus(StrEnum):
    PASSED = "PASSED"
    REJECTED = "REJECTED"


class PromotionStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NO_OP = "NO_OP"


class RollbackStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class ReplayPolicyStatus(StrEnum):
    ALLOWED = "ALLOWED"
    REJECTED = "REJECTED"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"


class RollbackReason(StrEnum):
    OPERATOR = "OPERATOR"
    KILL_SWITCH = "KILL_SWITCH"
    MIGRATION_INCOMPATIBLE = "MIGRATION_INCOMPATIBLE"
    INCIDENT = "INCIDENT"


@dataclass(frozen=True)
class CapitalControlContext:
    order_size: Decimal
    projected_position_size: Decimal
    daily_loss: Decimal
    account_id: str
    instrument_id: str


@dataclass(frozen=True)
class CapitalControlDecision:
    status: CapitalControlStatus
    reason: str | None = None

    @property
    def passed(self) -> bool:
        return self.status is CapitalControlStatus.PASSED


@dataclass(frozen=True)
class RolloutGateContext:
    safety_config: SafetyConfig
    environment: str
    account_id: str
    adapter_target: str
    stage_name: str
    command_surface: str
    approval: OperatorApproval | None
    migration: MigrationReadinessReport
    runtime_ready: bool
    replay_healthy: bool = True
    replay_running: bool = False
    scheduler_healthy: bool = True
    capital_controls: CapitalControlDecision | None = None
    unresolved_critical_incidents: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromotionDecision:
    status: PromotionStatus
    from_mode: RolloutMode
    to_mode: RolloutMode
    reason: str | None = None

    @property
    def accepted(self) -> bool:
        return self.status in {PromotionStatus.ACCEPTED, PromotionStatus.NO_OP}


@dataclass(frozen=True)
class RollbackDecision:
    status: RollbackStatus
    from_mode: RolloutMode
    to_mode: RolloutMode
    reason: RollbackReason | None = None
    detail: str | None = None

    @property
    def accepted(self) -> bool:
        return self.status is RollbackStatus.ACCEPTED


@dataclass(frozen=True)
class ReplayPolicyDecision:
    status: ReplayPolicyStatus
    dry_run: bool
    reason: str | None = None

    @property
    def allowed(self) -> bool:
        return self.status is ReplayPolicyStatus.ALLOWED


def evaluate_capital_controls(
    config: SafetyConfig,
    context: CapitalControlContext,
) -> CapitalControlDecision:
    controls = config.rollout.capital_controls
    if controls.max_order_size is not None and context.order_size > controls.max_order_size:
        return _capital_rejected("order size exceeds max_order_size")
    if (
        controls.max_position_size is not None
        and context.projected_position_size > controls.max_position_size
    ):
        return _capital_rejected("position size exceeds max_position_size")
    if controls.max_daily_loss is not None and context.daily_loss > controls.max_daily_loss:
        return _capital_rejected("daily loss exceeds max_daily_loss")
    if not controls.account_whitelist:
        if (
            config.rollout.mode is RolloutMode.LIVE
            or not controls.allow_empty_account_whitelist_in_non_live
        ):
            return _capital_rejected("account whitelist is required")
    elif context.account_id not in controls.account_whitelist:
        return _capital_rejected("account is not whitelisted")
    if not controls.allowed_instruments:
        if (
            config.rollout.mode is RolloutMode.LIVE
            or not controls.allow_empty_instrument_whitelist_in_non_live
        ):
            return _capital_rejected("instrument whitelist is required")
    elif context.instrument_id not in controls.allowed_instruments:
        return _capital_rejected("instrument is not allowed")
    return CapitalControlDecision(status=CapitalControlStatus.PASSED)


def evaluate_promotion(
    current_mode: RolloutMode,
    requested_mode: RolloutMode,
    context: RolloutGateContext,
) -> PromotionDecision:
    if current_mode is requested_mode:
        return PromotionDecision(
            status=PromotionStatus.NO_OP,
            from_mode=current_mode,
            to_mode=requested_mode,
        )
    if current_mode is RolloutMode.PAPER and requested_mode is RolloutMode.SIM:
        reason = _paper_to_sim_reject_reason(context)
        return _promotion_result(current_mode, requested_mode, reason)
    if current_mode is RolloutMode.SIM and requested_mode is RolloutMode.LIVE:
        live_gate = evaluate_stage_p_live_gate(context)
        reason = _sim_to_live_reject_reason(context, live_gate)
        return _promotion_result(current_mode, requested_mode, reason)
    return PromotionDecision(
        status=PromotionStatus.REJECTED,
        from_mode=current_mode,
        to_mode=requested_mode,
        reason="unsupported promotion path",
    )


def evaluate_rollback(
    current_mode: RolloutMode,
    requested_mode: RolloutMode,
    reason: RollbackReason,
) -> RollbackDecision:
    if (current_mode, requested_mode) in {
        (RolloutMode.LIVE, RolloutMode.SIM),
        (RolloutMode.LIVE, RolloutMode.PAPER),
        (RolloutMode.SIM, RolloutMode.PAPER),
    }:
        return RollbackDecision(
            status=RollbackStatus.ACCEPTED,
            from_mode=current_mode,
            to_mode=requested_mode,
            reason=reason,
        )
    return RollbackDecision(
        status=RollbackStatus.REJECTED,
        from_mode=current_mode,
        to_mode=requested_mode,
        reason=reason,
        detail="unsupported rollback path",
    )


def evaluate_stage_p_live_gate(context: RolloutGateContext) -> OpsGateDecision:
    live_gate = validate_live_submit_gate(
        config=context.safety_config,
        environment=context.environment,
        account_id=context.account_id,
        adapter_target=context.adapter_target,
        stage_name=context.stage_name,
        command_surface=context.command_surface,
        approval=context.approval,
        migration=context.migration,
    )
    if not live_gate.allowed:
        return live_gate
    if not context.runtime_ready:
        return _failed("runtime is not READY")
    if context.safety_config.kill_switch.global_kill_switch:
        return OpsGateDecision(
            allowed=False,
            incident_state=OpsIncidentState.KILLED,
            reason="global kill switch is active",
        )
    if context.replay_running:
        return _failed("replay is running")
    scheduler_gate = evaluate_scheduler_gate(context.safety_config)
    if not scheduler_gate.allowed:
        return scheduler_gate
    if not context.scheduler_healthy:
        return _failed("scheduler is not healthy")
    if context.capital_controls is None:
        return _failed("capital controls are required")
    if not context.capital_controls.passed:
        return _failed(context.capital_controls.reason or "capital controls failed")
    if context.unresolved_critical_incidents:
        return _failed("unresolved critical incidents are present")
    return OpsGateDecision(allowed=True, incident_state=OpsIncidentState.READY)


def evaluate_replay_policy(
    *,
    mode: RolloutMode,
    requested_live_apply: bool,
    allow_live_apply: bool,
    approval: OperatorApproval | None,
    safety_config: SafetyConfig,
) -> ReplayPolicyDecision:
    replay_gate = evaluate_replay_gate(safety_config)
    if not replay_gate.allowed:
        status = (
            ReplayPolicyStatus.BLOCKED
            if replay_gate.incident_state is OpsIncidentState.KILLED
            else ReplayPolicyStatus.PAUSED
        )
        return ReplayPolicyDecision(
            status=status,
            dry_run=True,
            reason=replay_gate.reason,
        )
    if mode in {RolloutMode.PAPER, RolloutMode.SIM}:
        return ReplayPolicyDecision(
            status=ReplayPolicyStatus.ALLOWED,
            dry_run=not requested_live_apply,
        )
    if not requested_live_apply:
        return ReplayPolicyDecision(status=ReplayPolicyStatus.ALLOWED, dry_run=True)
    if not allow_live_apply:
        return ReplayPolicyDecision(
            status=ReplayPolicyStatus.REJECTED,
            dry_run=True,
            reason="LIVE replay apply requires allow_live_apply",
        )
    if approval is None:
        return ReplayPolicyDecision(
            status=ReplayPolicyStatus.REJECTED,
            dry_run=True,
            reason="LIVE replay apply requires operator approval",
        )
    return ReplayPolicyDecision(status=ReplayPolicyStatus.ALLOWED, dry_run=False)


def _paper_to_sim_reject_reason(context: RolloutGateContext) -> str | None:
    if not context.runtime_ready:
        return "runtime is not READY"
    if not context.migration.compatible:
        return "migration readiness is incompatible"
    if not context.replay_healthy:
        return "replay is not clean"
    if context.approval is None:
        return "operator approval is required"
    return None


def _sim_to_live_reject_reason(
    context: RolloutGateContext,
    live_gate: OpsGateDecision,
) -> str | None:
    if not live_gate.allowed:
        return live_gate.reason or "live gate rejected"
    return None


def _promotion_result(
    current_mode: RolloutMode,
    requested_mode: RolloutMode,
    reason: str | None,
) -> PromotionDecision:
    if reason is None:
        return PromotionDecision(
            status=PromotionStatus.ACCEPTED,
            from_mode=current_mode,
            to_mode=requested_mode,
        )
    return PromotionDecision(
        status=PromotionStatus.REJECTED,
        from_mode=current_mode,
        to_mode=requested_mode,
        reason=reason,
    )


def _capital_rejected(reason: str) -> CapitalControlDecision:
    return CapitalControlDecision(status=CapitalControlStatus.REJECTED, reason=reason)


def _failed(reason: str) -> OpsGateDecision:
    return OpsGateDecision(
        allowed=False,
        incident_state=OpsIncidentState.FAILED,
        reason=reason,
    )
