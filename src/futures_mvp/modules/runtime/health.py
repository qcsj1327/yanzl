from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from futures_mvp.modules.runtime.config import RuntimeConfig


class RuntimeHealthStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class RuntimeHealthCheck:
    name: str
    status: RuntimeHealthStatus
    reason: str | None = None


@dataclass(frozen=True)
class RuntimeHealthReport:
    status: RuntimeHealthStatus
    checks: tuple[RuntimeHealthCheck, ...]

    @property
    def is_ready(self) -> bool:
        return self.status is RuntimeHealthStatus.READY


class RuntimeHealthChecker:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        db_check: Callable[[], bool],
        graph_check: Callable[[], bool],
        scheduler_check: Callable[[], bool],
        replay_check: Callable[[], bool],
        replay_conflict_check: Callable[[], bool] | None = None,
        redis_check: Callable[[], bool] | None = None,
    ) -> None:
        self._config = config
        self._db_check = db_check
        self._graph_check = graph_check
        self._scheduler_check = scheduler_check
        self._replay_check = replay_check
        self._replay_conflict_check = replay_conflict_check or (lambda: False)
        self._redis_check = redis_check

    def check(self) -> RuntimeHealthReport:
        checks = [
            _bool_check("config", True),
            _bool_check("db", self._db_check()),
            _bool_check("service_graph", self._graph_check()),
            _bool_check("scheduler", self._scheduler_check()),
            _bool_check("replay", self._replay_check()),
        ]
        if self._redis_check is not None:
            checks.append(
                _bool_check(
                    "redis",
                    self._redis_check(),
                    degraded_when_false=not self._config.enable_scheduler,
                )
            )
        if self._replay_conflict_check():
            checks.append(
                RuntimeHealthCheck(
                    name="replay_conflict",
                    status=RuntimeHealthStatus.DEGRADED,
                    reason="replay conflict or divergence requires review",
                )
            )
        return RuntimeHealthReport(status=_aggregate(checks), checks=tuple(checks))


def _bool_check(
    name: str,
    passed: bool,
    *,
    degraded_when_false: bool = False,
) -> RuntimeHealthCheck:
    if passed:
        return RuntimeHealthCheck(name=name, status=RuntimeHealthStatus.READY)
    status = RuntimeHealthStatus.DEGRADED if degraded_when_false else RuntimeHealthStatus.FAILED
    return RuntimeHealthCheck(name=name, status=status, reason=f"{name} check failed")


def _aggregate(checks: list[RuntimeHealthCheck]) -> RuntimeHealthStatus:
    if any(check.status is RuntimeHealthStatus.FAILED for check in checks):
        return RuntimeHealthStatus.FAILED
    if any(check.status is RuntimeHealthStatus.DEGRADED for check in checks):
        return RuntimeHealthStatus.DEGRADED
    return RuntimeHealthStatus.READY
