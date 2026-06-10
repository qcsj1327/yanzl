from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from futures_mvp.modules.ops_safety import (
    CapitalControlConfig,
    CapitalControlContext,
    CapitalControlDecision,
    CapitalControlStatus,
    KillSwitchConfig,
    LiveGateConfig,
    MigrationReadinessReport,
    OperatorApproval,
    PromotionStatus,
    ReplayPolicyStatus,
    RollbackReason,
    RollbackStatus,
    RolloutConfig,
    RolloutGateContext,
    RolloutMode,
    SafetyConfig,
    SafetyConfigError,
    evaluate_capital_controls,
    evaluate_promotion,
    evaluate_replay_policy,
    evaluate_rollback,
    evaluate_stage_p_live_gate,
)


def _approval() -> OperatorApproval:
    return OperatorApproval(
        environment="test",
        account_id="account-1",
        adapter_target="mock",
        allowed_stage="execution_gateway",
        command_surface="SUBMIT_ORDER",
        approved_at=datetime.now(UTC),
        decision_id="decision-1",
    )


def _migration(compatible: bool = True) -> MigrationReadinessReport:
    return MigrationReadinessReport(
        compatible=compatible,
        current_revision="head" if compatible else "old",
        expected_revision="head",
        reason=None if compatible else "db migration revision is incompatible",
    )


def _capital_context(**overrides: object) -> CapitalControlContext:
    values = {
        "order_size": Decimal("1"),
        "projected_position_size": Decimal("2"),
        "daily_loss": Decimal("3"),
        "account_id": "account-1",
        "instrument_id": "rb2610",
    }
    values.update(overrides)
    return CapitalControlContext(**values)


def _capital_config() -> CapitalControlConfig:
    return CapitalControlConfig(
        max_order_size=Decimal("10"),
        max_position_size=Decimal("20"),
        max_daily_loss=Decimal("30"),
        account_whitelist=("account-1",),
        allowed_instruments=("rb2610",),
    )


def _live_safety_config(
    *,
    kill_switch: KillSwitchConfig | None = None,
    capital_controls: CapitalControlConfig | None = None,
) -> SafetyConfig:
    return SafetyConfig(
        kill_switch=kill_switch or KillSwitchConfig(),
        live_gate=LiveGateConfig(
            broker_enabled=True,
            live_submit_enabled=True,
            explicit_live_flag=True,
            broker_credentials_handle="secret-ref",
        ),
        rollout=RolloutConfig(
            mode=RolloutMode.LIVE,
            capital_controls=capital_controls or _capital_config(),
        ),
    )


def _gate_context(**overrides: object) -> RolloutGateContext:
    safety_config = overrides.pop("safety_config", _live_safety_config())
    context_values = {
        "safety_config": safety_config,
        "environment": "test",
        "account_id": "account-1",
        "adapter_target": "mock",
        "stage_name": "execution_gateway",
        "command_surface": "SUBMIT_ORDER",
        "approval": _approval(),
        "migration": _migration(),
        "runtime_ready": True,
        "replay_healthy": True,
        "replay_running": False,
        "scheduler_healthy": True,
        "capital_controls": evaluate_capital_controls(safety_config, _capital_context()),
        "unresolved_critical_incidents": (),
    }
    context_values.update(overrides)
    return RolloutGateContext(**context_values)


def test_default_rollout_mode_is_paper() -> None:
    config = SafetyConfig()

    assert config.rollout.mode is RolloutMode.PAPER


def test_environment_and_execution_target_do_not_set_rollout_mode() -> None:
    config = SafetyConfig()

    assert config.known_environments == ("local", "test", "paper", "sim", "production")
    assert config.rollout.mode is RolloutMode.PAPER


def test_live_mode_requires_broker_enabled_at_config_boundary() -> None:
    with pytest.raises(SafetyConfigError):
        SafetyConfig(rollout=RolloutConfig(mode=RolloutMode.LIVE))


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"order_size": Decimal("11")}, "order size exceeds max_order_size"),
        ({"projected_position_size": Decimal("21")}, "position size exceeds max_position_size"),
        ({"daily_loss": Decimal("31")}, "daily loss exceeds max_daily_loss"),
        ({"account_id": "other"}, "account is not whitelisted"),
        ({"instrument_id": "ag2606"}, "instrument is not allowed"),
    ],
)
def test_capital_controls_reject_blocking_inputs(
    overrides: dict[str, object],
    reason: str,
) -> None:
    config = SafetyConfig(rollout=RolloutConfig(capital_controls=_capital_config()))

    decision = evaluate_capital_controls(config, _capital_context(**overrides))

    assert decision.status is CapitalControlStatus.REJECTED
    assert decision.reason == reason


def test_capital_controls_accept_all_valid_inputs() -> None:
    config = SafetyConfig(rollout=RolloutConfig(capital_controls=_capital_config()))

    decision = evaluate_capital_controls(config, _capital_context())

    assert decision.status is CapitalControlStatus.PASSED


def test_live_capital_controls_fail_closed_for_empty_whitelists() -> None:
    config = _live_safety_config(capital_controls=CapitalControlConfig())

    decision = evaluate_capital_controls(config, _capital_context())

    assert decision.status is CapitalControlStatus.REJECTED
    assert decision.reason == "account whitelist is required"


def test_paper_to_sim_promotion_accepts_when_gates_pass() -> None:
    context = _gate_context(
        safety_config=SafetyConfig(rollout=RolloutConfig(capital_controls=_capital_config()))
    )

    decision = evaluate_promotion(RolloutMode.PAPER, RolloutMode.SIM, context)

    assert decision.status is PromotionStatus.ACCEPTED


def test_paper_to_live_direct_promotion_rejected() -> None:
    decision = evaluate_promotion(RolloutMode.PAPER, RolloutMode.LIVE, _gate_context())

    assert decision.status is PromotionStatus.REJECTED
    assert decision.reason == "unsupported promotion path"


def test_same_mode_promotion_is_no_op() -> None:
    decision = evaluate_promotion(RolloutMode.PAPER, RolloutMode.PAPER, _gate_context())

    assert decision.status is PromotionStatus.NO_OP


def test_sim_to_live_promotion_accepts_when_all_gates_pass() -> None:
    decision = evaluate_promotion(RolloutMode.SIM, RolloutMode.LIVE, _gate_context())

    assert decision.status is PromotionStatus.ACCEPTED


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"approval": None}, "operator approval is required"),
        (
            {"safety_config": SafetyConfig(rollout=RolloutConfig(mode=RolloutMode.SIM))},
            "explicit live flag is required",
        ),
        (
            {"capital_controls": CapitalControlStatus.REJECTED},
            "order size exceeds max_order_size",
        ),
        (
            {"unresolved_critical_incidents": ("incident-1",)},
            "unresolved critical incidents are present",
        ),
    ],
)
def test_sim_to_live_promotion_rejects_missing_gates(
    overrides: dict[str, object],
    reason: str,
) -> None:
    if overrides.get("capital_controls") is CapitalControlStatus.REJECTED:
        overrides["capital_controls"] = CapitalControlStatus.REJECTED
        context = _gate_context(
            capital_controls=evaluate_capital_controls(
                _live_safety_config(),
                _capital_context(order_size=Decimal("100")),
            )
        )
    else:
        context = _gate_context(**overrides)

    decision = evaluate_promotion(RolloutMode.SIM, RolloutMode.LIVE, context)

    assert decision.status is PromotionStatus.REJECTED
    assert decision.reason == reason


@pytest.mark.parametrize(
    ("current_mode", "requested_mode"),
    [
        (RolloutMode.LIVE, RolloutMode.SIM),
        (RolloutMode.LIVE, RolloutMode.PAPER),
        (RolloutMode.SIM, RolloutMode.PAPER),
    ],
)
def test_allowed_rollbacks_accept(
    current_mode: RolloutMode,
    requested_mode: RolloutMode,
) -> None:
    decision = evaluate_rollback(
        current_mode,
        requested_mode,
        RollbackReason.INCIDENT,
    )

    assert decision.status is RollbackStatus.ACCEPTED


def test_invalid_rollback_rejected() -> None:
    decision = evaluate_rollback(
        RolloutMode.PAPER,
        RolloutMode.SIM,
        RollbackReason.OPERATOR,
    )

    assert decision.status is RollbackStatus.REJECTED


def test_rollback_allowed_under_kill_switch_reason() -> None:
    decision = evaluate_rollback(
        RolloutMode.LIVE,
        RolloutMode.PAPER,
        RollbackReason.KILL_SWITCH,
    )

    assert decision.status is RollbackStatus.ACCEPTED
    assert decision.reason is RollbackReason.KILL_SWITCH


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"approval": None}, "operator approval is required"),
        (
            {"safety_config": SafetyConfig(live_gate=LiveGateConfig(explicit_live_flag=True))},
            "broker is disabled",
        ),
        (
            {
                "safety_config": SafetyConfig(
                    live_gate=LiveGateConfig(
                        broker_enabled=True,
                        live_submit_enabled=True,
                        explicit_live_flag=True,
                    )
                )
            },
            "broker credentials are absent",
        ),
        ({"migration": _migration(False)}, "migration readiness is incompatible"),
        ({"runtime_ready": False}, "runtime is not READY"),
        (
            {
                "safety_config": _live_safety_config(
                    kill_switch=KillSwitchConfig(global_kill_switch=True)
                )
            },
            "global kill switch is active",
        ),
        ({"replay_running": True}, "replay is running"),
        ({"scheduler_healthy": False}, "scheduler is not healthy"),
        (
            {
                "capital_controls": CapitalControlDecision(
                    status=CapitalControlStatus.REJECTED,
                    reason="capital controls failed",
                )
            },
            "capital controls failed",
        ),
    ],
)
def test_stage_p_live_gate_rejects_missing_or_unsafe_conditions(
    overrides: dict[str, object],
    reason: str,
) -> None:
    decision = evaluate_stage_p_live_gate(_gate_context(**overrides))

    assert decision.allowed is False
    assert decision.reason == reason


def test_stage_p_live_gate_accepts_complete_valid_context() -> None:
    decision = evaluate_stage_p_live_gate(_gate_context())

    assert decision.allowed is True


@pytest.mark.parametrize("mode", [RolloutMode.PAPER, RolloutMode.SIM])
def test_paper_and_sim_replay_allowed(mode: RolloutMode) -> None:
    decision = evaluate_replay_policy(
        mode=mode,
        requested_live_apply=False,
        allow_live_apply=False,
        approval=None,
        safety_config=SafetyConfig(),
    )

    assert decision.status is ReplayPolicyStatus.ALLOWED


def test_live_replay_apply_disabled_by_default() -> None:
    decision = evaluate_replay_policy(
        mode=RolloutMode.LIVE,
        requested_live_apply=True,
        allow_live_apply=False,
        approval=_approval(),
        safety_config=SafetyConfig(),
    )

    assert decision.status is ReplayPolicyStatus.REJECTED
    assert decision.reason == "LIVE replay apply requires allow_live_apply"


def test_live_replay_apply_requires_approval() -> None:
    decision = evaluate_replay_policy(
        mode=RolloutMode.LIVE,
        requested_live_apply=True,
        allow_live_apply=True,
        approval=None,
        safety_config=SafetyConfig(),
    )

    assert decision.status is ReplayPolicyStatus.REJECTED
    assert decision.reason == "LIVE replay apply requires operator approval"


def test_live_replay_apply_accepts_explicit_allow_and_approval() -> None:
    decision = evaluate_replay_policy(
        mode=RolloutMode.LIVE,
        requested_live_apply=True,
        allow_live_apply=True,
        approval=_approval(),
        safety_config=SafetyConfig(),
    )

    assert decision.status is ReplayPolicyStatus.ALLOWED
    assert decision.dry_run is False


@pytest.mark.parametrize(
    "kill_switch",
    [
        KillSwitchConfig(global_kill_switch=True),
        KillSwitchConfig(replay_paused=True),
    ],
)
def test_kill_or_pause_blocks_replay(kill_switch: KillSwitchConfig) -> None:
    decision = evaluate_replay_policy(
        mode=RolloutMode.PAPER,
        requested_live_apply=False,
        allow_live_apply=False,
        approval=None,
        safety_config=SafetyConfig(kill_switch=kill_switch),
    )

    assert decision.status in {ReplayPolicyStatus.BLOCKED, ReplayPolicyStatus.PAUSED}
