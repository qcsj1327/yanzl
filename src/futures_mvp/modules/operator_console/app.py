from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol

from futures_mvp.modules.operator_console import labels
from futures_mvp.modules.operator_console.actions import (
    DryRunActionResult,
    DryRunProvider,
    run_paper_dry_run,
    run_sim_dry_run,
)
from futures_mvp.modules.operator_console.dry_run_wiring import (
    create_paper_dry_run_provider,
    create_sim_dry_run_provider,
)
from futures_mvp.modules.operator_console.view_models import (
    ButtonViewModel,
    ForbiddenActionViewModel,
    OperatorConsoleViewModel,
    OperatorPage,
    ResultHistoryViewModel,
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

    def selectbox(
        self,
        label: str,
        options: tuple[str, ...],
        *,
        index: int = 0,
        key: str | None = None,
    ) -> str: ...

    def columns(self, count: int) -> tuple[OperatorConsoleUI, ...]: ...

    def container(self) -> OperatorConsoleUI: ...

    def divider(self) -> None: ...


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

    def selectbox(
        self,
        label: str,
        options: tuple[str, ...],
        *,
        index: int = 0,
        key: str | None = None,
    ) -> str:
        return str(
            self.streamlit.sidebar.selectbox(
                label,
                options,
                index=index,
                key=key,
            )
        )

    def columns(self, count: int) -> tuple[StreamlitUI, ...]:
        return tuple(StreamlitUI(column) for column in self.streamlit.columns(count))

    def container(self) -> StreamlitUI:
        return StreamlitUI(self.streamlit.container())

    def divider(self) -> None:
        self.streamlit.divider()


def render_console(
    ui: OperatorConsoleUI,
    view_model: OperatorConsoleViewModel | None = None,
    *,
    paper_dry_run: DryRunProvider | None = None,
    sim_dry_run: DryRunProvider | None = None,
) -> None:
    model = view_model or default_console_view_model()
    ui.title(labels.section_label("Operator Console"))
    selected_page = _select_page(ui, model)
    ui.header(labels.page_title(selected_page.value))
    rendered_model = _render_page(
        ui,
        model,
        selected_page,
        paper_dry_run=paper_dry_run,
        sim_dry_run=sim_dry_run,
    )
    if selected_page is not OperatorPage.RESULTS_HISTORY and _has_result(rendered_model.results):
        ui.divider()
        _render_dry_run_result_summary(ui, rendered_model.results)


def main() -> None:
    streamlit = import_module("streamlit")
    render_console(
        StreamlitUI(streamlit),
        paper_dry_run=create_paper_dry_run_provider(),
        sim_dry_run=create_sim_dry_run_provider(),
    )


def _select_page(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> OperatorPage:
    page_titles = tuple(labels.page_title(page.value) for page in model.pages)
    selected_title = ui.selectbox(
        labels.field_label("page"),
        page_titles,
        index=0,
        key="operator_console_page",
    )
    page_by_title = {
        labels.page_title(page.value): page
        for page in model.pages
    }
    return page_by_title.get(selected_title, OperatorPage.DASHBOARD)


def _render_page(
    ui: OperatorConsoleUI,
    model: OperatorConsoleViewModel,
    page: OperatorPage,
    *,
    paper_dry_run: DryRunProvider | None,
    sim_dry_run: DryRunProvider | None,
) -> OperatorConsoleViewModel:
    if page is OperatorPage.DASHBOARD:
        _render_dashboard(ui, model)
    elif page is OperatorPage.PAPER_SESSION:
        result = _render_session(ui, model.paper, dry_run_provider=paper_dry_run)
        if result is not None:
            return _with_result(model, result)
    elif page is OperatorPage.SIM_SESSION:
        result = _render_session(ui, model.sim, dry_run_provider=sim_dry_run)
        if result is not None:
            return _with_result(model, result)
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
    return model


def _render_dashboard(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    first_row = ui.columns(2)
    _render_card(
        first_row[0],
        labels.section_label("system_status_card"),
        (
            labels.dashboard_text("system_ready"),
            labels.dashboard_text("current_mode"),
            labels.dashboard_text("current_target"),
            labels.dashboard_text("migration_ready"),
        ),
    )
    _render_card(
        first_row[1],
        labels.section_label("safety_lock_card"),
        (
            "🔒 LIVE 禁用",
            "🔒 Broker 禁用",
            "🔒 CTP 禁用",
            "🔒 SimNow 禁用",
            "🔒 真实资金禁用",
        ),
    )
    second_row = ui.columns(2)
    _render_card(
        second_row[0],
        labels.section_label("next_step_card"),
        (
            labels.dashboard_text("recommended_actions"),
            labels.dashboard_text("paper_dry_run_first"),
            labels.dashboard_text("view_result_second"),
            labels.dashboard_text("sim_after_safety"),
        ),
    )
    _render_card(
        second_row[1],
        labels.section_label("latest_result_card"),
        (
            labels.dashboard_text("not_run_yet"),
            labels.dashboard_text("db_delta_zero"),
            labels.dashboard_text("latest_status_none"),
        ),
    )


def _render_session(
    ui: OperatorConsoleUI,
    session: SessionPageViewModel,
    *,
    dry_run_provider: DryRunProvider | None,
) -> DryRunActionResult | None:
    if session.page is OperatorPage.PAPER_SESSION:
        _render_paper_session(ui, session)
    elif session.page is OperatorPage.SIM_SESSION:
        _render_sim_session(ui, session)
    else:
        ui.write(f"{labels.field_label('mode')}: {session.mode_name}")
        ui.write(f"{labels.field_label('target')}: {labels.safety_label(session.target)}")
    result = _render_dry_run_button(ui, session, dry_run_provider)
    _render_button(ui, session.apply_button)
    _render_button(ui, session.view_result_button)
    ui.markdown(labels.section_label("placeholder"))
    return result


def _render_paper_session(ui: OperatorConsoleUI, session: SessionPageViewModel) -> None:
    ui.subheader(f"🧪 {labels.section_label('what_is_this')}")
    for key in ("purpose_ledger", "not_exchange", "no_capital", "mock_only"):
        ui.markdown(f"- {labels.paper_text(key)}")
    ui.divider()
    ui.subheader(f"🧭 {labels.section_label('operation_flow')}")
    for key in ("step_dry_run", "step_view_result", "step_future_apply"):
        ui.markdown(labels.paper_text(key))
    ui.divider()
    ui.subheader(f"📄 {labels.section_label('current_buttons')}")
    ui.markdown(f"⚠️ {labels.paper_text('dry_run_hint')}")
    ui.markdown(f"⚠️ {labels.paper_text('apply_disabled_hint')}")
    ui.write(f"{labels.field_label('target')}: {labels.safety_label(session.target)}")


def _render_sim_session(ui: OperatorConsoleUI, session: SessionPageViewModel) -> None:
    ui.subheader(f"🧪 {labels.section_label('what_is_this')}")
    for key in ("local_sim", "not_simnow", "not_ctp", "not_live", "mock_only"):
        ui.markdown(f"- {labels.sim_text(key)}")
    ui.divider()
    ui.subheader(f"🧭 {labels.section_label('paper_vs_sim')}")
    for key in ("paper_difference", "sim_difference", "future_behaviors"):
        ui.markdown(f"- {labels.sim_text(key)}")
    ui.divider()
    ui.subheader(f"📄 {labels.section_label('current_buttons')}")
    ui.markdown(f"⚠️ {labels.paper_text('dry_run_hint')}")
    ui.markdown(f"⚠️ {labels.paper_text('apply_disabled_hint')}")
    ui.write(f"{labels.field_label('target')}: {labels.safety_label(session.target)}")


def _render_safety(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    for control in model.safety.controls:
        ui.subheader(labels.safety_label(control.label_key))
        ui.markdown(labels.safety_explanation(control.label_key))
        ui.write(f"{labels.field_label('health')}: {labels.status_label(control.status)}")
        ui.button(
            labels.action_label(control.button_key),
            disabled=control.disabled,
            key=f"safety:{control.button_key}",
        )
    ui.divider()
    _render_card(
        ui,
        labels.section_label("locked_actions"),
        tuple(
            labels.forbidden_action_label(action.label_key)
            for action in model.safety.forbidden_actions
        ),
    )
    _render_forbidden_actions(ui, model.safety.forbidden_actions)


def _render_configuration(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    ui.subheader(labels.section_label("normal_config"))
    for key, value in model.configuration.normal:
        ui.write(f"{labels.field_label(key)}: {value}")
    ui.subheader(labels.section_label("dry_run_required_config"))
    for key, value in model.configuration.dry_run_required:
        ui.write(f"{labels.field_label(key)}: {value}")
    ui.subheader(labels.section_label("advanced_config"))
    for key, value in model.configuration.advanced:
        ui.write(f"{labels.field_label(key)}: {value}")
    for source in model.configuration.sources:
        ui.markdown(source)


def _render_results(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    if _has_result(model.results):
        _render_dry_run_result_summary(ui, model.results)
        return
    for key in (
        "current_status",
        "latest_run",
        "db_delta",
        "execution_reports",
        "order_status",
        "trades",
        "position_updates",
        "margin_pnl",
        "settlement_snapshot",
    ):
        ui.markdown(labels.result_status_text(key))


def _render_diagnostics(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    ui.subheader(labels.section_label("diagnostic_items"))
    for key, value in model.diagnostics.items:
        ui.write(
            f"{labels.diagnostic_label(key)}: {labels.diagnostic_value_label(value)}"
        )


def _render_live_locked(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    ui.subheader(labels.section_label("live_locked_notice"))
    for key in ("no_exchange", "no_ctp", "no_simnow", "no_capital", "no_live_button"):
        ui.markdown(f"- {labels.live_locked_text(key)}")
    ui.divider()
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


def _render_dry_run_button(
    ui: OperatorConsoleUI,
    session: SessionPageViewModel,
    provider: DryRunProvider | None,
) -> DryRunActionResult | None:
    clicked = ui.button(
        labels.action_label(session.dry_run_button.action_key),
        disabled=session.dry_run_button.disabled,
        key=f"action:{session.dry_run_button.action_key}",
    )
    if not clicked:
        return None
    if session.page is OperatorPage.PAPER_SESSION:
        action_result = run_paper_dry_run(provider)
    elif session.page is OperatorPage.SIM_SESSION:
        action_result = run_sim_dry_run(provider)
    else:
        action_result = run_paper_dry_run(None)
    if action_result.dry_run_result is not None:
        return action_result.dry_run_result
    return DryRunActionResult(
        session_status=action_result.status.value,
        job_status=action_result.status.value,
        run_status=action_result.status.value,
        db_delta=0,
        target="MOCK only",
        reason=action_result.reason,
    )


def _with_result(
    model: OperatorConsoleViewModel,
    result: DryRunActionResult,
) -> OperatorConsoleViewModel:
    return OperatorConsoleViewModel(
        pages=model.pages,
        dashboard=model.dashboard,
        paper=model.paper,
        sim=model.sim,
        safety=model.safety,
        configuration=model.configuration,
        results=ResultHistoryViewModel(
            items=model.results.items,
            session_status=result.session_status,
            job_status=result.job_status,
            run_status=result.run_status,
            db_delta=result.db_delta,
            target=result.target,
            latest_run="dry-run",
            reason=result.reason,
        ),
        diagnostics=model.diagnostics,
        live_locked=model.live_locked,
    )


def _has_result(result: ResultHistoryViewModel) -> bool:
    return result.latest_run != "无"


def _render_dry_run_result_summary(
    ui: OperatorConsoleUI,
    result: ResultHistoryViewModel,
) -> None:
    if result.session_status == "BLOCKED":
        _render_blocked_dry_run_result(ui, result)
        return
    ui.subheader(labels.section_label("latest_result_card"))
    ui.markdown(
        f"{labels.result_label('session status')}: "
        f"{labels.status_label(result.session_status)}"
    )
    ui.markdown(
        f"{labels.result_label('job status')}: {labels.status_label(result.job_status)}"
    )
    ui.markdown(
        f"{labels.result_label('run status')}: {labels.status_label(result.run_status)}"
    )
    ui.markdown(f"{labels.result_label('db delta')}: {result.db_delta}")
    ui.markdown(f"{labels.result_label('target type')}: {labels.safety_label(result.target)}")
    if result.reason:
        ui.markdown(f"{labels.result_label('reason')}: {labels.reason_label(result.reason)}")


def _render_blocked_dry_run_result(
    ui: OperatorConsoleUI,
    result: ResultHistoryViewModel,
) -> None:
    ui.subheader(labels.section_label("blocked_dry_run_title"))
    ui.markdown(labels.blocked_result_text("description"))
    if result.reason:
        ui.markdown(f"{labels.result_label('reason')}: {labels.reason_label(result.reason)}")
    ui.markdown(labels.section_label("blocked_next_steps"))
    for key in ("next_step_config", "next_step_check", "next_step_retry"):
        ui.markdown(labels.blocked_result_text(key))
    ui.markdown(labels.section_label("blocked_safe_result"))
    ui.markdown(labels.blocked_result_text("safe_db_delta_zero"))
    ui.markdown(labels.blocked_result_text("safe_target_mock"))
    ui.markdown(labels.blocked_result_text("safe_no_capital"))


def _render_forbidden_actions(
    ui: OperatorConsoleUI,
    forbidden_actions: tuple[ForbiddenActionViewModel, ...],
) -> None:
    ui.subheader(labels.section_label("forbidden_actions"))
    for action in forbidden_actions:
        ui.markdown(labels.forbidden_action_label(action.label_key))


def _render_card(ui: OperatorConsoleUI, title: str, lines: tuple[str, ...]) -> None:
    container = ui.container()
    container.markdown(f"### {title}")
    for line in lines:
        container.markdown(line)


if __name__ == "__main__":
    main()
