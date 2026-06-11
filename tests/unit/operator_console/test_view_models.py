from futures_mvp.modules.operator_console.labels import safety_label
from futures_mvp.modules.operator_console.view_models import (
    ConsoleActionStatus,
    OperatorPage,
    default_console_view_model,
)


def test_default_view_model_has_all_pages() -> None:
    model = default_console_view_model()

    assert model.pages == tuple(OperatorPage)
    assert len(model.pages) == 8


def test_default_view_model_is_mock_only_and_live_locked() -> None:
    model = default_console_view_model()

    assert model.dashboard.execution_target_status == "MOCK only"
    assert safety_label(model.dashboard.execution_target_status) == "仅 MOCK，本地模拟"
    assert set(model.live_locked.disabled_states) == {
        "Live Disabled",
        "Broker Disabled",
        "CTP Disabled",
        "SimNow Disabled",
        "MOCK only",
    }
    assert all(not action.clickable for action in model.live_locked.forbidden_actions)


def test_apply_buttons_are_disabled_placeholders() -> None:
    model = default_console_view_model()

    assert model.paper.apply_button.disabled is True
    assert model.paper.apply_button.status is ConsoleActionStatus.DISABLED_PLACEHOLDER
    assert model.sim.apply_button.disabled is True
    assert model.sim.apply_button.status is ConsoleActionStatus.DISABLED_PLACEHOLDER
