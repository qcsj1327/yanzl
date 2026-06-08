from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from futures_mvp.modules.runtime.config import SchedulerConfig


class RuntimeScheduler(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def run_once(self, job_name: str) -> object | None: ...

    @property
    def is_running(self) -> bool: ...


@dataclass(frozen=True)
class RuntimeJob:
    name: str
    callable: Callable[[], object]


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
    def __init__(self, config: SchedulerConfig, jobs: tuple[RuntimeJob, ...]) -> None:
        self._config = config
        self._jobs = {job.name: job.callable for job in jobs}
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if not self._config.enabled:
            return None
        missing = set(self._config.enabled_jobs).difference(self._jobs)
        if missing:
            raise RuntimeError(f"scheduler jobs are not wired: {sorted(missing)}")
        self._running = True
        return None

    def stop(self) -> None:
        self._running = False

    def run_once(self, job_name: str) -> object | None:
        if not self._running:
            return None
        if job_name not in self._config.enabled_jobs:
            return None
        return self._jobs[job_name]()


def build_scheduler(config: SchedulerConfig, jobs: tuple[RuntimeJob, ...] = ()) -> RuntimeScheduler:
    if not config.enabled:
        return DisabledRuntimeScheduler()
    return ApplicationServiceScheduler(config, jobs)
