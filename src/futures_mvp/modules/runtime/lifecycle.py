from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from futures_mvp.modules.runtime.health import (
    RuntimeHealthCheck,
    RuntimeHealthReport,
    RuntimeHealthStatus,
)
from futures_mvp.modules.runtime.scheduler import RuntimeScheduler
from futures_mvp.modules.runtime.service_graph import RuntimeServiceGraph


@dataclass(frozen=True)
class RuntimeLifecycleEvent:
    name: str


@dataclass(frozen=True)
class RuntimeLifecycleState:
    events: tuple[RuntimeLifecycleEvent, ...]
    health: RuntimeHealthReport | None = None
    graph: RuntimeServiceGraph | None = None


class RuntimeLifecycleManager:
    def __init__(
        self,
        *,
        graph_builder: Callable[[], RuntimeServiceGraph],
        scheduler: RuntimeScheduler,
        health_check: Callable[[], RuntimeHealthReport],
        flush: Callable[[], None] | None = None,
        close_db: Callable[[], None] | None = None,
        release_locks: Callable[[], None] | None = None,
    ) -> None:
        self._graph_builder = graph_builder
        self._scheduler = scheduler
        self._health_check = health_check
        self._flush = flush or (lambda: None)
        self._close_db = close_db or (lambda: None)
        self._release_locks = release_locks or (lambda: None)
        self._events: list[RuntimeLifecycleEvent] = []
        self._graph: RuntimeServiceGraph | None = None
        self._ready = False

    @property
    def events(self) -> tuple[RuntimeLifecycleEvent, ...]:
        return tuple(self._events)

    def startup(self) -> RuntimeLifecycleState:
        self._record("config")
        self._record("db")
        self._record("repositories_uow")
        try:
            self._graph = self._graph_builder()
        except Exception as exc:
            health = _failed_report("service_graph", str(exc))
            self._ready = False
            self._record("service_graph_failed")
            self._record("health_not_ready")
            return RuntimeLifecycleState(events=self.events, health=health, graph=self._graph)
        graph_health = self._validate_graph(self._graph)
        if graph_health is not None:
            self._ready = False
            self._record("service_graph_failed")
            self._record("health_not_ready")
            return RuntimeLifecycleState(
                events=self.events,
                health=graph_health,
                graph=self._graph,
            )
        self._record("application_services")
        self._record("replay_coordinator")
        health = self._health_check()
        if health.status is not RuntimeHealthStatus.READY:
            self._ready = False
            self._record("health_not_ready")
            return RuntimeLifecycleState(events=self.events, health=health, graph=self._graph)
        try:
            self._scheduler.start()
        except Exception as exc:
            self._ready = False
            self._record("scheduler_failed")
            health = _failed_report("scheduler", str(exc))
            self._record("health_not_ready")
            return RuntimeLifecycleState(events=self.events, health=health, graph=self._graph)
        self._record("scheduler")
        self._ready = True
        self._record("health_ready")
        return RuntimeLifecycleState(events=self.events, health=health, graph=self._graph)

    def shutdown(self) -> RuntimeLifecycleState:
        self._ready = False
        self._record("health_not_ready")
        self._scheduler.stop()
        self._record("stop_scheduler")
        self._record("drain_in_flight")
        self._record("commit_or_rollback")
        self._flush()
        self._record("flush")
        self._close_db()
        self._record("close_db")
        self._release_locks()
        self._record("release_locks")
        self._record("terminated")
        return RuntimeLifecycleState(events=self.events, graph=self._graph)

    def _record(self, name: str) -> None:
        self._events.append(RuntimeLifecycleEvent(name=name))

    def _validate_graph(self, graph: RuntimeServiceGraph | None) -> RuntimeHealthReport | None:
        if graph is None:
            return _failed_report("service_graph", "service graph is missing")
        validator = getattr(graph, "validate_required_services", None)
        if validator is None:
            return None
        try:
            is_valid = bool(validator())
        except Exception as exc:
            return _failed_report("service_graph", str(exc))
        if not is_valid:
            return _failed_report("service_graph", "required service missing")
        return None


def _failed_report(name: str, reason: str) -> RuntimeHealthReport:
    return RuntimeHealthReport(
        status=RuntimeHealthStatus.FAILED,
        checks=(
            RuntimeHealthCheck(
                name=name,
                status=RuntimeHealthStatus.FAILED,
                reason=reason,
            ),
        ),
    )
