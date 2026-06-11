from futures_mvp.modules.operator_console.actions import (
    PAPER_APPLY_ACTION,
    PAPER_DRY_RUN_ACTION,
    SIM_APPLY_ACTION,
    SIM_DRY_RUN_ACTION,
    DryRunActionResult,
    PlaceholderActionStatus,
    run_apply_placeholder,
    run_paper_dry_run,
    run_placeholder_action,
    run_sim_dry_run,
)


def test_apply_actions_are_disabled_and_never_execute() -> None:
    for descriptor in (PAPER_APPLY_ACTION, SIM_APPLY_ACTION):
        result = run_placeholder_action(descriptor)

        assert descriptor.disabled is True
        assert result.status is PlaceholderActionStatus.BLOCKED
        assert result.executed is False


def test_dry_run_actions_are_placeholders_and_never_execute() -> None:
    for descriptor in (PAPER_DRY_RUN_ACTION, SIM_DRY_RUN_ACTION):
        result = run_placeholder_action(descriptor)

        assert descriptor.disabled is False
        assert result.status is PlaceholderActionStatus.PLACEHOLDER
        assert result.executed is False


def test_dry_run_without_provider_is_blocked() -> None:
    for action in (run_paper_dry_run, run_sim_dry_run):
        result = action()

        assert result.status is PlaceholderActionStatus.BLOCKED
        assert result.executed is False


def test_paper_dry_run_provider_is_called_once() -> None:
    calls = 0

    def provider() -> DryRunActionResult:
        nonlocal calls
        calls += 1
        return DryRunActionResult("DRY_RUN_COMPLETED", "DRY_RUN", "DRY_RUN_COMPLETED")

    result = run_paper_dry_run(provider)

    assert calls == 1
    assert result.status is PlaceholderActionStatus.DRY_RUN_COMPLETED
    assert result.executed is True
    assert result.dry_run_result == DryRunActionResult(
        "DRY_RUN_COMPLETED",
        "DRY_RUN",
        "DRY_RUN_COMPLETED",
    )


def test_sim_dry_run_provider_is_called_once() -> None:
    calls = 0

    def provider() -> DryRunActionResult:
        nonlocal calls
        calls += 1
        return DryRunActionResult("DRY_RUN_COMPLETED", "DRY_RUN", "DRY_RUN_COMPLETED")

    result = run_sim_dry_run(provider)

    assert calls == 1
    assert result.status is PlaceholderActionStatus.DRY_RUN_COMPLETED
    assert result.executed is True


def test_apply_placeholder_is_blocked() -> None:
    for descriptor in (PAPER_APPLY_ACTION, SIM_APPLY_ACTION):
        result = run_apply_placeholder(descriptor)

        assert result.status is PlaceholderActionStatus.BLOCKED
        assert result.executed is False


def test_dry_run_db_delta_nonzero_is_not_marked_safe() -> None:
    def provider() -> DryRunActionResult:
        return DryRunActionResult(
            "DRY_RUN_COMPLETED",
            "DRY_RUN",
            "DRY_RUN_COMPLETED",
            db_delta=1,
        )

    result = run_paper_dry_run(provider)

    assert result.status is PlaceholderActionStatus.BLOCKED
    assert result.executed is True
    assert result.dry_run_result is not None
    assert result.dry_run_result.session_status == "BLOCKED"
    assert result.dry_run_result.db_delta == 1


def test_dry_run_non_mock_result_is_not_marked_safe() -> None:
    def provider() -> DryRunActionResult:
        return DryRunActionResult(
            "DRY_RUN_COMPLETED",
            "DRY_RUN",
            "DRY_RUN_COMPLETED",
            target="SIM",
        )

    result = run_sim_dry_run(provider)

    assert result.status is PlaceholderActionStatus.BLOCKED
    assert result.executed is True
    assert result.dry_run_result is not None
    assert result.dry_run_result.session_status == "BLOCKED"
    assert result.dry_run_result.target == "SIM"
