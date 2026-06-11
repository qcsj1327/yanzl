from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol

from futures_mvp.modules.operator_console import labels
from futures_mvp.modules.operator_console.view_models import (
    ButtonViewModel,
    ForbiddenActionViewModel,
    OperatorConsoleViewModel,
    OperatorPage,
    SessionPageViewModel,
    default_console_view_model,
)


class OperatorConsoleUI(Protocol):
    def title(self, body: str) -> None: ...

    def header(self, body: str) -> None: ...

    def subheader(self, body: str) -> None: ...

    def markdown(self, body: str) -> None: ...

    def write(self, body: object) -> None: ...

    def button(self, label: str, *, disabled: bool = False, key: str | None = None) -> bool: ...


@dataclass(frozen=True)
class StreamlitUI:
    streamlit: Any

    def title(self, body: str) -> None:
        self.streamlit.title(body)

    def header(self, body: str) -> None:
        self.streamlit.header(body)

    def subheader(self, body: str) -> None:
        self.streamlit.subheader(body)

    def markdown(self, body: str) -> None:
        self.streamlit.markdown(body)

    def write(self, body: object) -> None:
        self.streamlit.write(body)

    def button(self, label: str, *, disabled: bool = False, key: str | None = None) -> bool:
        return bool(self.streamlit.button(label, disabled=disabled, key=key))


def render_console(
    ui: OperatorConsoleUI,
    view_model: OperatorConsoleViewModel | None = None,
) -> None:
    model = view_model or default_console_view_model()
    ui.title(labels.section_label("Operator Console"))
    for page in model.pages:
        ui.header(labels.page_title(page.value))
        if page is OperatorPage.DASHBOARD:
            _render_dashboard(ui, model)
        elif page is OperatorPage.PAPER_SESSION:
            _render_session(ui, model.paper)
        elif page is OperatorPage.SIM_SESSION:
            _render_session(ui, model.sim)
        elif page is OperatorPage.SAFETY_CONTROLS:
            _render_safety(ui, model)
        elif page is OperatorPage.CONFIGURATION:
            _render_configuration(ui, model)
        elif page is OperatorPage.RESULTS_HISTORY:
            _render_results(ui, model)
        elif page is OperatorPage.DIAGNOSTICS:
            _render_diagnostics(ui, model)
        elif page is OperatorPage.LIVE_LOCKED_PAGE:
            _render_live_locked(ui, model)


def main() -> None:
    streamlit = import_module("streamlit")
    render_console(StreamlitUI(streamlit))


def _render_dashboard(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    dashboard = model.dashboard
    ui.subheader(labels.section_label("status_overview"))
    for name, value in (
        ("Runtime", labels.status_label(dashboard.runtime_status)),
        ("rollout mode", dashboard.rollout_mode),
        ("ExecutionTarget", labels.safety_label(dashboard.execution_target_status)),
        ("migration", labels.status_label(dashboard.migration_status)),
        ("Kill Switch", labels.status_label(dashboard.kill_switch_status)),
        ("Scheduler Pause", labels.status_label(dashboard.scheduler_pause_status)),
        ("Replay Pause", labels.status_label(dashboard.replay_pause_status)),
        ("Paper", labels.status_label(dashboard.latest_paper_result)),
        ("SIM", labels.status_label(dashboard.latest_sim_result)),
    ):
        ui.write(f"{labels.field_label(name)}: {value}")
    _render_notices(ui, dashboard.notices)


def _render_session(ui: OperatorConsoleUI, session: SessionPageViewModel) -> None:
    ui.write(f"{labels.field_label('mode')}: {session.mode_name}")
    ui.write(f"{labels.field_label('target')}: {labels.safety_label(session.target)}")
    _render_notices(ui, session.notices)
    _render_button(ui, session.dry_run_button)
    _render_button(ui, session.apply_button)
    _render_button(ui, session.view_result_button)
    ui.markdown(labels.section_label("placeholder"))


def _render_safety(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    for control in model.safety.controls:
        ui.write(f"{labels.safety_label(control.label_key)}: {labels.status_label(control.status)}")
        ui.button(
            labels.action_label(control.button_key),
            disabled=control.disabled,
            key=f"safety:{control.button_key}",
        )
    for state in model.safety.disabled_states:
        ui.markdown(labels.safety_label(state))
    _render_forbidden_actions(ui, model.safety.forbidden_actions)


def _render_configuration(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    ui.subheader(labels.section_label("normal_config"))
    for key, value in model.configuration.normal:
        ui.write(f"{labels.field_label(key)}: {value}")
    ui.subheader(labels.section_label("advanced_config"))
    for key, value in model.configuration.advanced:
        ui.write(f"{labels.field_label(key)}: {value}")
    for source in model.configuration.sources:
        ui.markdown(source)


def _render_results(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    for key, value in model.results.items:
        display_key = labels.result_label(key)
        display_value = (
            labels.safety_label(value) if value == "MOCK only" else labels.status_label(value)
        )
        ui.write(f"{display_key}: {display_value}")


def _render_diagnostics(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    ui.subheader(labels.section_label("diagnostic_items"))
    for key, value in model.diagnostics.items:
        ui.write(
            f"{labels.diagnostic_label(key)}: {labels.diagnostic_value_label(value)}"
        )


def _render_live_locked(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    for state in model.live_locked.disabled_states:
        ui.markdown(labels.safety_label(state))
    _render_forbidden_actions(ui, model.live_locked.forbidden_actions)


def _render_notices(ui: OperatorConsoleUI, notices: tuple[str, ...]) -> None:
    ui.subheader(labels.section_label("risk_notices"))
    for notice in notices:
        ui.markdown(labels.risk_notice(notice))


def _render_button(ui: OperatorConsoleUI, button: ButtonViewModel) -> None:
    ui.button(
        labels.action_label(button.action_key),
        disabled=button.disabled,
        key=f"action:{button.action_key}",
    )
    if button.disabled:
        ui.markdown(labels.section_label("disabled_placeholder"))


def _render_forbidden_actions(
    ui: OperatorConsoleUI,
    forbidden_actions: tuple[ForbiddenActionViewModel, ...],
) -> None:
    ui.subheader(labels.section_label("forbidden_actions"))
    for action in forbidden_actions:
        ui.markdown(labels.forbidden_action_label(action.label_key))
