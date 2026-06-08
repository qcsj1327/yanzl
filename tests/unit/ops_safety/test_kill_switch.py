from futures_mvp.modules.ops_safety import (
    KillSwitchConfig,
    OpsIncidentState,
    SafetyConfig,
    evaluate_broker_gate,
    evaluate_replay_gate,
    evaluate_scheduler_gate,
    evaluate_stage_gate,
)


def test_global_kill_switch_returns_killed() -> None:
    config = SafetyConfig(kill_switch=KillSwitchConfig(global_kill_switch=True))

    decision = evaluate_scheduler_gate(config)

    assert decision.allowed is False
    assert decision.incident_state is OpsIncidentState.KILLED


def test_scheduler_pause_blocks_scheduler() -> None:
    config = SafetyConfig(kill_switch=KillSwitchConfig(scheduler_paused=True))

    decision = evaluate_scheduler_gate(config)

    assert decision.allowed is False
    assert decision.incident_state is OpsIncidentState.PAUSED
    assert decision.reason == "scheduler is paused"


def test_replay_pause_blocks_replay() -> None:
    config = SafetyConfig(kill_switch=KillSwitchConfig(replay_paused=True))

    decision = evaluate_replay_gate(config)

    assert decision.allowed is False
    assert decision.incident_state is OpsIncidentState.PAUSED
    assert decision.reason == "replay is paused"


def test_per_stage_kill_switch_blocks_stage() -> None:
    config = SafetyConfig(kill_switch=KillSwitchConfig(per_stage_kill_switches=("market",)))

    decision = evaluate_stage_gate(config, "market")

    assert decision.allowed is False
    assert decision.blocked_stage == "market"
    assert decision.reason == "stage kill switch is active"


def test_broker_disabled_blocks_broker_gate() -> None:
    decision = evaluate_broker_gate(SafetyConfig())

    assert decision.allowed is False
    assert decision.reason == "broker is disabled"

