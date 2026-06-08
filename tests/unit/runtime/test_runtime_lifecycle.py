from futures_mvp.modules.runtime import (
    RuntimeHealthCheck,
    RuntimeHealthReport,
    RuntimeHealthStatus,
    RuntimeLifecycleManager,
)


class FakeScheduler:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        self._running = True
        self._events.append("scheduler_start")

    def stop(self) -> None:
        self._running = False
        self._events.append("scheduler_stop")

    def run_once(self, job_name: str) -> object | None:
        del job_name
        return None


class FakeGraph:
    def __init__(self, valid: bool = True) -> None:
        self._valid = valid

    def validate_required_services(self) -> bool:
        return self._valid


def _ready_report() -> RuntimeHealthReport:
    return RuntimeHealthReport(
        status=RuntimeHealthStatus.READY,
        checks=(RuntimeHealthCheck(name="test", status=RuntimeHealthStatus.READY),),
    )


def _failed_report(name: str = "db") -> RuntimeHealthReport:
    return RuntimeHealthReport(
        status=RuntimeHealthStatus.FAILED,
        checks=(
            RuntimeHealthCheck(
                name=name,
                status=RuntimeHealthStatus.FAILED,
                reason=f"{name} failed",
            ),
        ),
    )


def test_lifecycle_startup_starts_scheduler_only_after_health_precheck() -> None:
    side_effects: list[str] = []

    def health_check() -> RuntimeHealthReport:
        side_effects.append("health_check")
        return _ready_report()

    manager = RuntimeLifecycleManager(
        graph_builder=lambda: FakeGraph(),  # type: ignore[arg-type,return-value]
        scheduler=FakeScheduler(side_effects),
        health_check=health_check,
    )

    state = manager.startup()

    assert [event.name for event in state.events] == [
        "config",
        "db",
        "repositories_uow",
        "application_services",
        "replay_coordinator",
        "scheduler",
        "health_ready",
    ]
    assert side_effects == ["health_check", "scheduler_start"]
    assert state.health is not None
    assert state.health.status is RuntimeHealthStatus.READY


def test_lifecycle_db_failure_does_not_start_scheduler() -> None:
    side_effects: list[str] = []
    manager = RuntimeLifecycleManager(
        graph_builder=lambda: FakeGraph(),  # type: ignore[arg-type,return-value]
        scheduler=FakeScheduler(side_effects),
        health_check=_failed_report,
    )

    state = manager.startup()

    assert state.health is not None
    assert state.health.status is RuntimeHealthStatus.FAILED
    assert [event.name for event in state.events][-1] == "health_not_ready"
    assert side_effects == []


def test_lifecycle_graph_none_fails_before_scheduler_start() -> None:
    side_effects: list[str] = []
    manager = RuntimeLifecycleManager(
        graph_builder=lambda: None,  # type: ignore[arg-type,return-value]
        scheduler=FakeScheduler(side_effects),
        health_check=_ready_report,
    )

    state = manager.startup()

    assert state.health is not None
    assert state.health.status is RuntimeHealthStatus.FAILED
    assert state.graph is None
    assert side_effects == []


def test_lifecycle_graph_validation_failure_does_not_start_scheduler() -> None:
    side_effects: list[str] = []
    manager = RuntimeLifecycleManager(
        graph_builder=lambda: FakeGraph(valid=False),  # type: ignore[arg-type,return-value]
        scheduler=FakeScheduler(side_effects),
        health_check=_ready_report,
    )

    state = manager.startup()

    assert state.health is not None
    assert state.health.status is RuntimeHealthStatus.FAILED
    assert side_effects == []


def test_lifecycle_shutdown_stops_scheduler_before_db_close() -> None:
    side_effects: list[str] = []
    manager = RuntimeLifecycleManager(
        graph_builder=lambda: FakeGraph(),  # type: ignore[arg-type,return-value]
        scheduler=FakeScheduler(side_effects),
        health_check=_ready_report,
        close_db=lambda: side_effects.append("close_db"),
    )

    manager.startup()
    state = manager.shutdown()

    names = [event.name for event in state.events]
    assert names.index("stop_scheduler") < names.index("close_db")
    assert side_effects == ["scheduler_start", "scheduler_stop", "close_db"]
