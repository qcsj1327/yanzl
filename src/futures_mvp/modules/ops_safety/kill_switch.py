from __future__ import annotations

from futures_mvp.modules.ops_safety.config import SafetyConfig
from futures_mvp.modules.ops_safety.incident import OpsGateDecision, OpsIncidentState


def evaluate_scheduler_gate(config: SafetyConfig) -> OpsGateDecision:
    kill_switch = config.kill_switch
    if kill_switch.global_kill_switch:
        return OpsGateDecision(
            allowed=False,
            incident_state=OpsIncidentState.KILLED,
            reason="global kill switch is active",
        )
    if kill_switch.scheduler_paused:
        return OpsGateDecision(
            allowed=False,
            incident_state=OpsIncidentState.PAUSED,
            reason="scheduler is paused",
        )
    return OpsGateDecision(allowed=True, incident_state=OpsIncidentState.READY)


def evaluate_replay_gate(config: SafetyConfig) -> OpsGateDecision:
    kill_switch = config.kill_switch
    if kill_switch.global_kill_switch:
        return OpsGateDecision(
            allowed=False,
            incident_state=OpsIncidentState.KILLED,
            reason="global kill switch is active",
        )
    if kill_switch.replay_paused:
        return OpsGateDecision(
            allowed=False,
            incident_state=OpsIncidentState.PAUSED,
            reason="replay is paused",
        )
    return OpsGateDecision(allowed=True, incident_state=OpsIncidentState.READY)


def evaluate_stage_gate(config: SafetyConfig, stage_name: str) -> OpsGateDecision:
    if config.kill_switch.global_kill_switch:
        return OpsGateDecision(
            allowed=False,
            incident_state=OpsIncidentState.KILLED,
            reason="global kill switch is active",
            blocked_stage=stage_name,
        )
    if stage_name in config.kill_switch.per_stage_kill_switches:
        return OpsGateDecision(
            allowed=False,
            incident_state=OpsIncidentState.PAUSED,
            reason="stage kill switch is active",
            blocked_stage=stage_name,
        )
    return OpsGateDecision(allowed=True, incident_state=OpsIncidentState.READY)


def evaluate_broker_gate(config: SafetyConfig) -> OpsGateDecision:
    if config.kill_switch.global_kill_switch:
        return OpsGateDecision(
            allowed=False,
            incident_state=OpsIncidentState.KILLED,
            reason="global kill switch is active",
        )
    if not config.live_gate.broker_enabled:
        return OpsGateDecision(
            allowed=False,
            incident_state=OpsIncidentState.PAUSED,
            reason="broker is disabled",
        )
    if config.live_gate.broker_credentials_handle is None:
        return OpsGateDecision(
            allowed=False,
            incident_state=OpsIncidentState.PAUSED,
            reason="broker credentials are absent",
        )
    return OpsGateDecision(allowed=True, incident_state=OpsIncidentState.READY)

