import pytest

from futures_mvp.modules.runtime import (
    ReplayConfig,
    RuntimeConfig,
    RuntimeConfigError,
    SchedulerConfig,
)


def test_runtime_config_defaults_fail_closed() -> None:
    config = RuntimeConfig(runtime_id="runtime-1", environment="test")

    assert config.enable_scheduler is False
    assert config.scheduler.enabled is False
    assert config.enable_replay is False
    assert config.replay.default_dry_run is True
    assert config.replay.allowed_live_apply_stages == ()


def test_invalid_timeout_is_rejected() -> None:
    with pytest.raises(RuntimeConfigError):
        RuntimeConfig(
            runtime_id="runtime-1",
            environment="test",
            startup_check_timeout_seconds=0,
        )


def test_enabled_scheduler_requires_jobs() -> None:
    with pytest.raises(RuntimeConfigError):
        SchedulerConfig(enabled=True)


def test_live_replay_requires_explicit_live_stages() -> None:
    with pytest.raises(RuntimeConfigError):
        ReplayConfig(enabled=True, default_dry_run=False)


def test_runtime_flags_must_match_nested_configs() -> None:
    with pytest.raises(RuntimeConfigError):
        RuntimeConfig(
            runtime_id="runtime-1",
            environment="test",
            enable_replay=True,
            replay=ReplayConfig(enabled=False),
        )
