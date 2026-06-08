from __future__ import annotations

import pytest

from futures_mvp.modules.ops_safety import (
    KillSwitchConfig,
    LiveGateConfig,
    MigrationReadinessConfig,
    SafetyConfig,
    SafetyConfigError,
)
from futures_mvp.modules.runtime import RuntimeConfig, RuntimeConfigError


def test_default_safety_config_disables_broker_and_live() -> None:
    config = SafetyConfig()

    assert config.kill_switch.global_kill_switch is False
    assert config.kill_switch.per_stage_kill_switches == ()
    assert config.kill_switch.scheduler_paused is False
    assert config.kill_switch.replay_paused is False
    assert config.live_gate.broker_enabled is False
    assert config.live_gate.live_submit_enabled is False


def test_unknown_environment_is_rejected_by_runtime_config() -> None:
    with pytest.raises(RuntimeConfigError):
        RuntimeConfig(runtime_id="runtime-1", environment="typo")


def test_production_requires_explicit_flags() -> None:
    with pytest.raises(RuntimeConfigError):
        RuntimeConfig(runtime_id="runtime-1", environment="production")

    config = RuntimeConfig(
        runtime_id="runtime-1",
        environment="production",
        safety=SafetyConfig(production_explicit=True),
    )

    assert config.environment == "production"


def test_safety_config_rejects_empty_stage_or_revision_names() -> None:
    with pytest.raises(SafetyConfigError):
        KillSwitchConfig(per_stage_kill_switches=("",))
    with pytest.raises(SafetyConfigError):
        MigrationReadinessConfig(enabled=True)
    with pytest.raises(SafetyConfigError):
        LiveGateConfig(broker_credentials_handle="")

