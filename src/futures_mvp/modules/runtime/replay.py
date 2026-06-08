from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from futures_mvp.modules.ops_safety.config import SafetyConfig
from futures_mvp.modules.ops_safety.incident import OpsIncidentState
from futures_mvp.modules.ops_safety.kill_switch import evaluate_replay_gate, evaluate_stage_gate
from futures_mvp.modules.runtime.config import ReplayConfig


class ReplayStatus(StrEnum):
    SUCCESS = "SUCCESS"
    CONFLICT = "CONFLICT"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    DISABLED = "DISABLED"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ReplayStageContext:
    stage_name: str
    dry_run: bool
    allow_live_apply: bool
    batch_size: int


@dataclass(frozen=True)
class ReplayStage:
    name: str
    callable: Callable[[ReplayStageContext], object]


@dataclass(frozen=True)
class ReplayStageResult:
    stage_name: str
    status: ReplayStatus
    result: object | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ReplayResult:
    status: ReplayStatus
    stage_results: tuple[ReplayStageResult, ...]

    @property
    def has_conflict(self) -> bool:
        return any(
            stage.status in {ReplayStatus.CONFLICT, ReplayStatus.ERROR}
            for stage in self.stage_results
        )


class RuntimeReplayCoordinator:
    def __init__(
        self,
        config: ReplayConfig,
        stages: tuple[ReplayStage, ...],
        safety_config: SafetyConfig | None = None,
    ) -> None:
        self._config = config
        self._safety_config = safety_config or SafetyConfig()
        self._stage_map: dict[str, ReplayStage] = {}
        self._configuration_error: ReplayStageResult | None = None
        known_stages = set(default_replay_stage_names())
        for stage in stages:
            if stage.name not in known_stages:
                self._configuration_error = ReplayStageResult(
                    stage_name=stage.name,
                    status=ReplayStatus.ERROR,
                    reason="unknown replay stage",
                )
                continue
            if stage.name in self._stage_map:
                self._configuration_error = ReplayStageResult(
                    stage_name=stage.name,
                    status=ReplayStatus.ERROR,
                    reason="duplicate replay stage",
                )
                continue
            self._stage_map[stage.name] = stage

    @property
    def stage_names(self) -> tuple[str, ...]:
        return tuple(
            stage_name
            for stage_name in default_replay_stage_names()
            if stage_name in self._stage_map
        )

    def replay(self) -> ReplayResult:
        if not self._config.enabled:
            return ReplayResult(status=ReplayStatus.DISABLED, stage_results=())
        replay_gate = evaluate_replay_gate(self._safety_config)
        if not replay_gate.allowed:
            status = (
                ReplayStatus.BLOCKED
                if replay_gate.incident_state is OpsIncidentState.KILLED
                else ReplayStatus.PAUSED
            )
            return ReplayResult(
                status=status,
                stage_results=(
                    ReplayStageResult(
                        stage_name="replay",
                        status=status,
                        reason=replay_gate.reason,
                    ),
                ),
            )
        if self._configuration_error is not None:
            return ReplayResult(
                status=ReplayStatus.ERROR,
                stage_results=(self._configuration_error,),
            )

        results: list[ReplayStageResult] = []
        stopped = False
        for stage_name in default_replay_stage_names():
            stage = self._stage_map.get(stage_name)
            if stage is None:
                results.append(
                    ReplayStageResult(
                        stage_name=stage_name,
                        status=ReplayStatus.SKIPPED,
                        reason="stage not wired",
                    )
                )
                continue
            if stopped:
                results.append(
                    ReplayStageResult(
                        stage_name=stage_name,
                        status=ReplayStatus.SKIPPED,
                        reason="upstream conflict",
                    )
                )
                continue
            stage_gate = evaluate_stage_gate(self._safety_config, stage_name)
            if not stage_gate.allowed:
                status = (
                    ReplayStatus.BLOCKED
                    if stage_gate.incident_state is OpsIncidentState.KILLED
                    else ReplayStatus.PAUSED
                )
                results.append(
                    ReplayStageResult(
                        stage_name=stage_name,
                        status=status,
                        reason=stage_gate.reason,
                    )
                )
                stopped = True
                continue
            context = ReplayStageContext(
                stage_name=stage.name,
                dry_run=self._dry_run_for(stage.name),
                allow_live_apply=stage.name in self._config.allowed_live_apply_stages,
                batch_size=self._config.batch_size,
            )
            try:
                value = stage.callable(context)
            except Exception as exc:  # pragma: no cover - defensive runtime envelope
                stage_result = ReplayStageResult(
                    stage_name=stage.name,
                    status=ReplayStatus.ERROR,
                    reason=str(exc),
                )
            else:
                stage_result = ReplayStageResult(
                    stage_name=stage.name,
                    status=ReplayStatus.CONFLICT if _has_conflict(value) else ReplayStatus.SUCCESS,
                    result=value,
                )
            results.append(stage_result)
            if (
                self._config.stop_on_conflict
                and stage_result.status in {ReplayStatus.CONFLICT, ReplayStatus.ERROR}
            ):
                stopped = True
        return ReplayResult(status=_aggregate(results), stage_results=tuple(results))

    def _dry_run_for(self, stage_name: str) -> bool:
        if (
            not self._config.default_dry_run
            and stage_name in self._config.allowed_live_apply_stages
        ):
            return False
        return True


def default_replay_stage_names() -> tuple[str, ...]:
    return (
        "market",
        "feature",
        "strategy",
        "workflow",
        "oms_bridge",
        "execution_gateway",
        "execution_reports",
        "oms_event_application",
        "oms_to_trade",
        "position",
        "margin",
        "pnl",
        "settlement",
    )


def _aggregate(results: list[ReplayStageResult]) -> ReplayStatus:
    if any(result.status is ReplayStatus.BLOCKED for result in results):
        return ReplayStatus.BLOCKED
    if any(result.status is ReplayStatus.PAUSED for result in results):
        return ReplayStatus.PAUSED
    if any(result.status is ReplayStatus.ERROR for result in results):
        return ReplayStatus.ERROR
    if any(result.status is ReplayStatus.CONFLICT for result in results):
        return ReplayStatus.CONFLICT
    return ReplayStatus.SUCCESS


def _has_conflict(value: object) -> bool:
    if value is None:
        return False
    for attr in ("has_conflict", "has_divergence", "has_error"):
        flag = getattr(value, attr, None)
        if isinstance(flag, bool) and flag:
            return True
    status = getattr(value, "status", None)
    if _status_is_conflict(status):
        return True
    if isinstance(value, list | tuple):
        return any(_has_conflict(item) for item in value)
    results = getattr(value, "results", None)
    if isinstance(results, list | tuple):
        return any(_has_conflict(item) for item in results)
    return False


def _status_is_conflict(status: object) -> bool:
    if status is None:
        return False
    status_value = getattr(status, "value", status)
    return str(status_value).upper() in {"CONFLICT", "ERROR", "FAILED"}
