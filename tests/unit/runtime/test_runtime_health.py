from futures_mvp.modules.runtime import (
    ReplayConfig,
    RuntimeConfig,
    RuntimeHealthChecker,
    RuntimeHealthStatus,
)


def _config() -> RuntimeConfig:
    return RuntimeConfig(runtime_id="runtime-1", environment="test")


def test_health_ready_when_required_checks_pass() -> None:
    report = RuntimeHealthChecker(
        config=_config(),
        db_check=lambda: True,
        graph_check=lambda: True,
        scheduler_check=lambda: True,
        replay_check=lambda: True,
    ).check()

    assert report.status is RuntimeHealthStatus.READY
    assert report.is_ready


def test_health_failed_when_db_fails() -> None:
    report = RuntimeHealthChecker(
        config=_config(),
        db_check=lambda: False,
        graph_check=lambda: True,
        scheduler_check=lambda: True,
        replay_check=lambda: True,
    ).check()

    assert report.status is RuntimeHealthStatus.FAILED


def test_replay_conflict_degrades_health() -> None:
    report = RuntimeHealthChecker(
        config=RuntimeConfig(
            runtime_id="runtime-1",
            environment="test",
            enable_replay=True,
            replay=ReplayConfig(enabled=True),
        ),
        db_check=lambda: True,
        graph_check=lambda: True,
        scheduler_check=lambda: True,
        replay_check=lambda: True,
        replay_conflict_check=lambda: True,
    ).check()

    assert report.status is RuntimeHealthStatus.DEGRADED


def test_scheduler_construction_failure_is_failed() -> None:
    report = RuntimeHealthChecker(
        config=_config(),
        db_check=lambda: True,
        graph_check=lambda: True,
        scheduler_check=lambda: False,
        replay_check=lambda: True,
    ).check()

    assert report.status is RuntimeHealthStatus.FAILED
