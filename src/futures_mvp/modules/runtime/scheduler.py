from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from futures_mvp.modules.ops_safety.config import SafetyConfig
from futures_mvp.modules.ops_safety.incident import OpsIncidentState
from futures_mvp.modules.ops_safety.kill_switch import (
    evaluate_scheduler_gate,
    evaluate_stage_gate,
)
from futures_mvp.modules.runtime.config import SchedulerConfig


class RuntimeScheduler(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def run_once(self, job_name: str) -> object | None: ...

    @property
    def is_running(self) -> bool: ...


class RuntimeSchedulerRunStatus(StrEnum):
    SUCCESS = "SUCCESS"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"
    PAUSED = "PAUSED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class RuntimeJob:
    name: str
    callable: Callable[[], object]


@dataclass(frozen=True)
class RuntimeSchedulerRunResult:
    job_name: str
    status: RuntimeSchedulerRunStatus
    reason: str | None = None


class DisabledRuntimeScheduler:
    @property
    def is_running(self) -> bool:
        return False

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def run_once(self, job_name: str) -> object | None:
        del job_name
        return None


class ApplicationServiceScheduler:
    def __init__(
        self,
        config: SchedulerConfig,
        jobs: tuple[RuntimeJob, ...],
        safety_config: SafetyConfig | None = None,
    ) -> None:
        self._config = config
        self._safety_config = safety_config or SafetyConfig()
        self._jobs = {job.name: job.callable for job in jobs}
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if not self._config.enabled:
            return None
        scheduler_gate = evaluate_scheduler_gate(self._safety_config)
        if not scheduler_gate.allowed:
            self._running = False
            return None
        missing = set(self._config.enabled_jobs).difference(self._jobs)
        if missing:
            raise RuntimeError(f"scheduler jobs are not wired: {sorted(missing)}")
        self._running = True
        return None

    def stop(self) -> None:
        self._running = False

    def run_once(self, job_name: str) -> object | None:
        scheduler_gate = evaluate_scheduler_gate(self._safety_config)
        if not scheduler_gate.allowed:
            return RuntimeSchedulerRunResult(
                job_name=job_name,
                status=(
                    RuntimeSchedulerRunStatus.BLOCKED
                    if scheduler_gate.incident_state is OpsIncidentState.KILLED
                    else RuntimeSchedulerRunStatus.PAUSED
                ),
                reason=scheduler_gate.reason,
            )
        if not self._running:
            return None
        if job_name not in self._config.enabled_jobs:
            return None
        stage_gate = evaluate_stage_gate(self._safety_config, job_name)
        if not stage_gate.allowed:
            return RuntimeSchedulerRunResult(
                job_name=job_name,
                status=RuntimeSchedulerRunStatus.BLOCKED,
                reason=stage_gate.reason,
            )
        return self._jobs[job_name]()


def build_scheduler(
    config: SchedulerConfig,
    jobs: tuple[RuntimeJob, ...] = (),
    safety_config: SafetyConfig | None = None,
) -> RuntimeScheduler:
    if not config.enabled:
        return DisabledRuntimeScheduler()
    return ApplicationServiceScheduler(config, jobs, safety_config)
