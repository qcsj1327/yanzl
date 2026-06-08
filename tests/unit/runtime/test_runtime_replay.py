from dataclasses import dataclass

from futures_mvp.modules.runtime import (
    ReplayConfig,
    ReplayStage,
    ReplayStageContext,
    ReplayStatus,
    RuntimeReplayCoordinator,
    default_replay_stage_names,
)


@dataclass(frozen=True)
class _StageOutput:
    has_conflict: bool = False


def _record_stage(calls: list[str]):
    return lambda context: calls.append(context.stage_name)


def test_default_replay_stage_order_is_frozen() -> None:
    assert default_replay_stage_names() == (
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


def test_replay_coordinator_defaults_to_dry_run() -> None:
    contexts: list[ReplayStageContext] = []
    coordinator = RuntimeReplayCoordinator(
        ReplayConfig(enabled=True),
        (ReplayStage(name="market", callable=lambda context: contexts.append(context)),),
    )

    result = coordinator.replay()

    assert result.status is ReplayStatus.SUCCESS
    assert contexts[0].dry_run is True
    assert contexts[0].allow_live_apply is False


def test_replay_live_allowlist_is_hard_gate() -> None:
    contexts: list[ReplayStageContext] = []
    coordinator = RuntimeReplayCoordinator(
        ReplayConfig(
            enabled=True,
            default_dry_run=False,
            allowed_live_apply_stages=("market",),
        ),
        (
            ReplayStage(name="feature", callable=lambda context: contexts.append(context)),
            ReplayStage(name="market", callable=lambda context: contexts.append(context)),
        ),
    )

    coordinator.replay()

    by_stage = {context.stage_name: context for context in contexts}
    assert by_stage["market"].dry_run is False
    assert by_stage["market"].allow_live_apply is True
    assert by_stage["feature"].dry_run is True
    assert by_stage["feature"].allow_live_apply is False


def test_replay_allowed_stage_stays_dry_run_when_global_live_disabled() -> None:
    contexts: list[ReplayStageContext] = []
    coordinator = RuntimeReplayCoordinator(
        ReplayConfig(
            enabled=True,
            allowed_live_apply_stages=("oms_event_application",),
        ),
        (
            ReplayStage(
                name="oms_event_application",
                callable=lambda context: contexts.append(context),
            ),
        ),
    )

    coordinator.replay()

    assert contexts[0].dry_run is True
    assert contexts[0].allow_live_apply is True


def test_disabled_replay_is_explicit_noop() -> None:
    calls: list[str] = []
    contexts: list[ReplayStageContext] = []
    coordinator = RuntimeReplayCoordinator(
        ReplayConfig(enabled=False),
        (
            ReplayStage(
                name="market",
                callable=lambda context: contexts.append(context)
                or calls.append(context.stage_name),
            ),
        ),
    )

    result = coordinator.replay()

    assert result.status is ReplayStatus.DISABLED
    assert result.stage_results == ()
    assert calls == []
    assert contexts == []


def test_replay_executes_unordered_input_in_frozen_order() -> None:
    calls: list[str] = []
    coordinator = RuntimeReplayCoordinator(
        ReplayConfig(enabled=True),
        (
            ReplayStage(name="settlement", callable=_record_stage(calls)),
            ReplayStage(name="market", callable=_record_stage(calls)),
            ReplayStage(name="position", callable=_record_stage(calls)),
        ),
    )

    result = coordinator.replay()

    assert calls == ["market", "position", "settlement"]
    assert coordinator.stage_names == ("market", "position", "settlement")
    assert result.status is ReplayStatus.SUCCESS


def test_unknown_replay_stage_fails_closed_without_calls() -> None:
    calls: list[str] = []
    coordinator = RuntimeReplayCoordinator(
        ReplayConfig(enabled=True),
        (
            ReplayStage(name="market", callable=lambda context: calls.append(context.stage_name)),
            ReplayStage(name="unknown", callable=lambda context: calls.append(context.stage_name)),
        ),
    )

    result = coordinator.replay()

    assert result.status is ReplayStatus.ERROR
    assert result.stage_results[0].stage_name == "unknown"
    assert result.stage_results[0].reason == "unknown replay stage"
    assert calls == []


def test_replay_conflict_stops_downstream() -> None:
    calls: list[str] = []
    coordinator = RuntimeReplayCoordinator(
        ReplayConfig(enabled=True, stop_on_conflict=True),
        (
            ReplayStage(
                name="market",
                callable=lambda context: calls.append(context.stage_name) or _StageOutput(True),
            ),
            ReplayStage(
                name="feature",
                callable=lambda context: calls.append(context.stage_name),
            ),
        ),
    )

    result = coordinator.replay()

    assert calls == ["market"]
    assert result.status is ReplayStatus.CONFLICT
    by_stage = {stage.stage_name: stage for stage in result.stage_results}
    assert by_stage["market"].status is ReplayStatus.CONFLICT
    assert by_stage["feature"].status is ReplayStatus.SKIPPED
    assert by_stage["feature"].reason == "upstream conflict"
