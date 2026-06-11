from futures_mvp.modules.operator_console.actions import (
    PAPER_APPLY_ACTION,
    PAPER_DRY_RUN_ACTION,
    SIM_APPLY_ACTION,
    SIM_DRY_RUN_ACTION,
    PlaceholderActionStatus,
    run_placeholder_action,
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
