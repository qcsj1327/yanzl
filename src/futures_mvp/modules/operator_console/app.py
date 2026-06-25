from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol, cast

from futures_mvp.modules.market_data.models import InstrumentResolveStatus
from futures_mvp.modules.market_data.resolver import InstrumentResolver
from futures_mvp.modules.operator_console import labels
from futures_mvp.modules.operator_console.actions import (
    DryRunActionResult,
    DryRunProvider,
    run_paper_dry_run,
)
from futures_mvp.modules.operator_console.config_assembly import (
    READ_ONLY_ADAPTER_DATA_SOURCE,
    STATIC_FIXTURE_DATA_SOURCE,
    CommandPreview,
    ConsoleDryRunConfig,
    append_history,
    assemble_config,
    format_allowed_instruments,
    parse_allowed_instruments,
)
from futures_mvp.modules.operator_console.dry_run_wiring import (
    create_paper_config_dry_run_provider,
)
from futures_mvp.modules.operator_console.view_models import (
    ButtonViewModel,
    ConfigurationViewModel,
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

    def text_input(self, label: str, *, value: str = "", key: str | None = None) -> str: ...

    def number_input(
        self,
        label: str,
        *,
        value: str = "",
        key: str | None = None,
    ) -> str: ...

    def text_area(self, label: str, *, value: str = "", key: str | None = None) -> str: ...

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

    def session_value(self, key: str, default: object | None = None) -> object | None: ...

    def set_session_value(self, key: str, value: object) -> None: ...


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

    def text_input(self, label: str, *, value: str = "", key: str | None = None) -> str:
        return str(self.streamlit.text_input(label, value=value, key=key))

    def number_input(
        self,
        label: str,
        *,
        value: str = "",
        key: str | None = None,
    ) -> str:
        return str(self.streamlit.text_input(label, value=value, key=key))

    def text_area(self, label: str, *, value: str = "", key: str | None = None) -> str:
        return str(self.streamlit.text_area(label, value=value, key=key))

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

    def session_value(self, key: str, default: object | None = None) -> object | None:
        return cast(object | None, self.streamlit.session_state.get(key, default))

    def set_session_value(self, key: str, value: object) -> None:
        self.streamlit.session_state[key] = value


def render_console(
    ui: OperatorConsoleUI,
    view_model: OperatorConsoleViewModel | None = None,
    *,
    paper_dry_run: DryRunProvider | None = None,
) -> None:
    model = _model_with_session_state(ui, view_model or default_console_view_model())
    ui.title(labels.section_label("Operator Console"))
    selected_page = _select_page(ui, model)
    ui.header(labels.page_title(selected_page.value))
    rendered_model = _render_page(
        ui,
        model,
        selected_page,
        paper_dry_run=paper_dry_run,
    )
    if _has_result(rendered_model.results):
        ui.divider()
        _render_dry_run_result_summary(ui, rendered_model.results)


def main() -> None:
    streamlit = import_module("streamlit")
    if hasattr(streamlit, "set_page_config"):
        streamlit.set_page_config(
            page_title=labels.section_label("Operator Console"),
            layout="wide",
            initial_sidebar_state="expanded",
        )
    streamlit.markdown(
        """
        <style>
        [data-testid="stHeader"] {height: 0rem !important;}
        .block-container {
            padding-top: 0.25rem !important;
            padding-bottom: 0.25rem !important;
            max-width: 100% !important;
        }
        h1 {
            font-size: 1.55rem !important;
            line-height: 1.05 !important;
            margin: 0.1rem 0 0.2rem 0 !important;
        }
        h2 {
            font-size: 1.35rem !important;
            line-height: 1.05 !important;
            margin: 0.1rem 0 0.2rem 0 !important;
        }
        h3 {
            font-size: 0.95rem !important;
            line-height: 1.05 !important;
            margin: 0.03rem 0 0.08rem 0 !important;
        }
        p, li {
            font-size: 0.74rem !important;
            line-height: 1.02 !important;
            margin-bottom: 0 !important;
        }
        ul {margin: 0.02rem 0 0.08rem 0 !important;}
        label, input, textarea {
            font-size: 0.72rem !important;
            line-height: 1.05 !important;
        }
        section[data-testid="stSidebar"] {
            width: 12rem !important;
            min-width: 12rem !important;
        }
        section[data-testid="stSidebar"] > div {
            width: 12rem !important;
            min-width: 12rem !important;
        }
        div[data-testid="stTextInput"] {margin-bottom: -0.05rem !important;}
        div[data-testid="stTextInput"] input {
            min-height: 1.35rem !important;
            padding-top: 0.1rem !important;
            padding-bottom: 0.1rem !important;
        }
        div[data-testid="stVerticalBlock"] {gap: 0.02rem !important;}
        div[data-testid="stHorizontalBlock"] {gap: 0.4rem !important;}
        div[data-testid="stMarkdownContainer"] {margin-bottom: 0 !important;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    render_console(StreamlitUI(streamlit))


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
) -> OperatorConsoleViewModel:
    if page is OperatorPage.DASHBOARD:
        _render_dashboard(ui, model)
    elif page is OperatorPage.RESEARCH:
        _render_research(ui, model)
    elif page is OperatorPage.PORTFOLIO:
        _render_portfolio(ui, model)
    elif page is OperatorPage.PAPER:
        _render_paper(ui, model)
        provider = paper_dry_run or create_paper_config_dry_run_provider(
            model.configuration.dry_run_config
        )
        result = _render_session_actions(ui, model.paper, provider)
        if result is not None:
            return _with_result(ui, model, "PAPER", result)
    elif page is OperatorPage.MARKET_DATA:
        configuration = _render_market_data(ui, model)
        return _with_configuration(model, configuration)
    elif page is OperatorPage.DIAGNOSTICS:
        _render_diagnostics(ui, model)
    return model


def _render_dashboard(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    _render_card(
        ui,
        labels.section_label("safety_banner"),
        (
            "MOCK only",
            "research only",
            "no live trading",
            "不写数据库",
        ),
    )
    first_row = ui.columns(3)
    _render_card(
        first_row[0],
        labels.section_label("system_status_card"),
        (
            f"{labels.field_label('Research Platform')}: "
            f"{labels.status_label(model.dashboard.research_status)}",
            f"{labels.field_label('Paper Runtime')}: "
            f"{labels.status_label(model.dashboard.paper_runtime_status)}",
            f"{labels.field_label('Portfolio')}: "
            f"{labels.status_label(model.dashboard.portfolio_status)}",
        ),
    )
    _render_card(
        first_row[1],
        labels.section_label("market_data_status"),
        (
            f"{labels.field_label('Market Data')}: "
            f"{labels.status_label(model.dashboard.market_data_status)}",
            f"{labels.field_label('current_source')}: "
            f"{model.dashboard.current_source}",
            f"{labels.field_label('Diagnostics')}: "
            f"{labels.status_label(model.dashboard.diagnostics_status)}",
        ),
    )
    _render_card(
        first_row[2],
        labels.section_label("safety_lock_card"),
        (
            "LIVE 禁用",
            "Broker 禁用",
            "CTP / SimNow 禁用",
            "真实资金禁用",
            labels.safety_label(model.dashboard.execution_target_status),
        ),
    )
    second_row = ui.columns(1)
    _render_card(
        second_row[0],
        labels.section_label("latest_result_card"),
        (
            f"{labels.field_label('latest dry-run')}: "
            f"{model.dashboard.latest_dry_run_summary}",
            labels.dashboard_text("db_delta_zero"),
            "命令来源：static_fixture 时可预演，read_only_adapter_placeholder 时阻断",
        ),
    )


def _render_research(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    research = model.research
    top = ui.columns(3)
    _render_card(
        top[0],
        labels.section_label("research_status"),
        (
            f"{labels.field_label('backtest_status')}: "
            f"{labels.status_label(research.backtest_status)}",
            f"{labels.field_label('strategy')}: {research.strategy}",
            f"{labels.field_label('symbols')}: {', '.join(research.symbols)}",
        ),
    )
    _render_card(
        top[1],
        labels.section_label("pnl_summary"),
        (
            f"{labels.field_label('realized_pnl')}: {research.realized_pnl}",
            f"{labels.field_label('unrealized_pnl')}: {research.unrealized_pnl}",
        ),
    )
    _render_card(top[2], labels.section_label("metrics"), research.metrics)
    bottom = ui.columns(4)
    _render_card(bottom[0], labels.section_label("orders"), research.orders)
    _render_card(bottom[1], labels.section_label("trades"), research.trades)
    _render_card(bottom[2], labels.section_label("positions"), research.positions)
    _render_card(
        bottom[3],
        labels.section_label("equity_curve"),
        research.equity_curve_summary,
    )


def _render_portfolio(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    portfolio = model.portfolio
    top = ui.columns(4)
    _render_card(top[0], labels.section_label("cash"), (portfolio.cash,))
    _render_card(top[1], labels.section_label("equity"), (portfolio.equity,))
    _render_card(top[2], labels.section_label("market_value"), (portfolio.market_value,))
    _render_card(top[3], labels.section_label("cash_weight"), (portfolio.cash_weight,))
    bottom = ui.columns(4)
    _render_card(bottom[0], labels.section_label("positions"), portfolio.positions)
    _render_card(
        bottom[1],
        labels.section_label("symbol_contributions"),
        portfolio.symbol_contributions,
    )
    _render_card(
        bottom[2],
        labels.section_label("position_weights"),
        portfolio.position_weights,
    )
    _render_card(bottom[3], labels.section_label("allocation"), portfolio.allocation)


def _render_paper(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    paper = model.paper_page
    top = ui.columns(3)
    _render_card(
        top[0],
        labels.section_label("paper_runtime"),
        (f"PaperResearchRuntime: {labels.status_label(paper.runtime_status)}",),
    )
    _render_card(top[1], labels.section_label("paper_lifecycle"), paper.lifecycle)
    _render_card(top[2], labels.section_label("paper_consistency"), paper.consistency)
    bottom = ui.columns(4)
    _render_card(bottom[0], labels.section_label("paper_orders"), paper.orders)
    _render_card(bottom[1], labels.section_label("paper_fills"), paper.fills)
    _render_card(bottom[2], labels.section_label("paper_positions"), paper.positions)
    _render_card(bottom[3], labels.section_label("paper_portfolio"), paper.portfolio)
    ui.markdown(labels.section_label("placeholder"))


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


def _render_configuration(
    ui: OperatorConsoleUI,
    model: OperatorConsoleViewModel,
) -> ConfigurationViewModel:
    config = _read_config_form(ui, model.configuration.dry_run_config)
    assembly = assemble_config(config)
    ui.set_session_value("operator_console_dry_run_config", assembly.config)
    summary_col, required_col, preview_col, source_col = ui.columns(4)
    summary_col.subheader(labels.section_label("normal_config"))
    _render_key_values(summary_col, _normal_config_items(config))
    required_col.subheader(labels.section_label("dry_run_required_config"))
    _render_key_values(
        required_col,
        _dry_run_required_items(config, assembly.validation.missing_fields),
    )
    preview_col.subheader(labels.section_label("typed_command_preview"))
    preview_col.markdown(labels.section_label("resolver_preview"))
    if assembly.resolver_resolution is not None:
        _render_resolver_preview(
            preview_col,
            assembly.resolver_resolution,
            assembly.config.allowed_instruments,
        )
    if assembly.preview is None:
        preview_col.markdown(labels.config_text("preview_blocked"))
        if assembly.validation.reason:
            preview_col.markdown(
                f"{labels.result_label('reason')}: "
                f"{labels.reason_label(assembly.validation.reason)}"
            )
        if assembly.validation.missing_fields:
            missing_fields = ", ".join(
                labels.field_label(field)
                for field in assembly.validation.missing_fields
            )
            preview_col.markdown(
                f"{labels.config_label('missing_fields')}: "
                f"{missing_fields}"
            )
    else:
        preview_col.markdown(labels.config_text("preview_ready"))
        _render_command_preview(preview_col, assembly.preview)
    source_col.subheader(labels.section_label("advanced_config"))
    _render_key_values(source_col, model.configuration.advanced)
    source_col.markdown(labels.section_label("command_sources"))
    for source in model.configuration.sources:
        source_col.markdown(source)
    return ConfigurationViewModel(
        normal=_normal_config_items(config),
        advanced=model.configuration.advanced,
        sources=model.configuration.sources,
        dry_run_config=assembly.config,
        preview=assembly.preview,
        validation=assembly.validation,
        dry_run_required=_dry_run_required_items(
            assembly.config,
            assembly.validation.missing_fields,
        ),
    )


def _render_market_data(
    ui: OperatorConsoleUI,
    model: OperatorConsoleViewModel,
) -> ConfigurationViewModel:
    current = model.configuration.dry_run_config
    source_options = (STATIC_FIXTURE_DATA_SOURCE, READ_ONLY_ADAPTER_DATA_SOURCE)
    source = ui.selectbox(
        labels.field_label("market_data_source"),
        source_options,
        index=source_options.index(current.market_data_source)
        if current.market_data_source in source_options
        else 0,
        key="operator_console_market_data_source",
    )
    config = ConsoleDryRunConfig(
        account_id=current.account_id,
        trading_day=current.trading_day,
        instrument_id=current.instrument_id,
        trade_instrument_id=current.trade_instrument_id,
        symbol=current.symbol,
        exchange=current.exchange,
        resolver_resolution=current.resolver_resolution,
        market_data_source=source,
        read_only_adapter_configured=current.read_only_adapter_configured,
        quantity=current.quantity,
        price=current.price,
        max_order_size=current.max_order_size,
        max_position_size=current.max_position_size,
        max_daily_loss=current.max_daily_loss,
        allowed_instruments=current.allowed_instruments,
        is_example=current.is_example,
        target="MOCK only",
        apply_requested=False,
    )
    assembly = assemble_config(config)
    ui.set_session_value("operator_console_dry_run_config", assembly.config)
    market_data = model.market_data
    top = ui.columns(4)
    _render_card(
        top[0],
        labels.section_label("selected_data_source"),
        (source,),
    )
    _render_card(
        top[1],
        labels.section_label("static_fixture_status"),
        (labels.status_label(market_data.static_fixture_status),),
    )
    _render_card(
        top[2],
        labels.section_label("read_only_adapter_status"),
        (labels.status_label(market_data.read_only_adapter_status),),
    )
    _render_card(top[3], labels.section_label("resolver_source"), (market_data.resolver_source,))
    middle = ui.columns(4)
    _render_card(
        middle[0],
        labels.section_label("connection_status"),
        (labels.status_label(market_data.connection_status),),
    )
    _render_card(
        middle[1],
        labels.section_label("configuration_status"),
        (labels.status_label(market_data.configuration_status),),
    )
    _render_card(
        middle[2],
        labels.section_label("latest_quote"),
        market_data.latest_quote,
    )
    _render_card(
        middle[3],
        labels.section_label("updated_at"),
        (market_data.updated_at,),
    )
    bottom = ui.columns(4)
    blocked_reason = assembly.validation.reason if assembly.validation.blocked else "无"
    _render_card(
        bottom[0],
        labels.section_label("blocked_reason"),
        (labels.reason_label(blocked_reason),),
    )
    _render_card(
        bottom[1],
        labels.section_label("supported_symbols"),
        (", ".join(market_data.supported_symbols),),
    )
    _render_card(bottom[2], labels.section_label("latest_bars"), market_data.latest_bars)
    _render_card(bottom[3], labels.section_label("source_diagnostics"), market_data.diagnostics)
    preview_col = ui.columns(1)[0]
    preview_col.subheader(labels.section_label("typed_command_preview"))
    if assembly.preview is None:
        preview_col.markdown(labels.config_text("preview_blocked"))
        if assembly.validation.reason:
            preview_col.markdown(
                f"{labels.result_label('reason')}: "
                f"{labels.reason_label(assembly.validation.reason)}"
            )
    else:
        preview_col.markdown(labels.config_text("preview_ready"))
        _render_command_preview(preview_col, assembly.preview)
    return ConfigurationViewModel(
        normal=model.configuration.normal,
        advanced=model.configuration.advanced,
        sources=model.configuration.sources,
        dry_run_config=assembly.config,
        preview=assembly.preview,
        validation=assembly.validation,
        market_data_sources=model.configuration.market_data_sources,
        dry_run_required=model.configuration.dry_run_required,
    )


def _render_results(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    if _has_result(model.results):
        _render_dry_run_result_summary(ui, model.results)
        _render_result_history(ui, model.results)
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
    row = ui.columns(5)
    _render_card(row[0], labels.section_label("resolver_diagnostics"), model.diagnostics.resolver)
    _render_card(
        row[1],
        labels.section_label("market_data_diagnostics"),
        model.diagnostics.market_data,
    )
    _render_card(row[2], labels.section_label("research_diagnostics"), model.diagnostics.research)
    _render_card(row[3], labels.section_label("paper_diagnostics"), model.diagnostics.paper)
    _render_card(row[4], labels.section_label("safety_checks"), model.diagnostics.safety)
    ui.subheader(labels.section_label("diagnostic_items"))
    _render_card(ui, labels.section_label("local_checks"), model.diagnostics.items)


def _render_live_locked(ui: OperatorConsoleUI, model: OperatorConsoleViewModel) -> None:
    notice_col, forbidden_col = ui.columns(2)
    notice_col.subheader(labels.section_label("live_locked_notice"))
    for key in ("no_exchange", "no_ctp", "no_simnow", "no_capital", "no_live_button"):
        notice_col.markdown(f"- {labels.live_locked_text(key)}")
    _render_forbidden_actions(forbidden_col, model.live_locked.forbidden_actions)


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
    action_result = run_paper_dry_run(provider)
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


def _render_session_actions(
    ui: OperatorConsoleUI,
    session: SessionPageViewModel,
    provider: DryRunProvider | None,
) -> DryRunActionResult | None:
    dry_run_col, apply_col, result_col = ui.columns(3)
    result = _render_dry_run_button(dry_run_col, session, provider)
    _render_button(apply_col, session.apply_button)
    _render_button(result_col, session.view_result_button)
    return result


def _with_result(
    ui: OperatorConsoleUI,
    model: OperatorConsoleViewModel,
    mode: str,
    result: DryRunActionResult,
) -> OperatorConsoleViewModel:
    history = append_history(model.results.history, mode=mode, result=result)
    ui.set_session_value("operator_console_result_history", history)
    return OperatorConsoleViewModel(
        pages=model.pages,
        dashboard=model.dashboard,
        research=model.research,
        portfolio=model.portfolio,
        paper_page=model.paper_page,
        market_data=model.market_data,
        paper=model.paper,
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
            history=history,
        ),
        diagnostics=model.diagnostics,
        live_locked=model.live_locked,
    )


def _with_configuration(
    model: OperatorConsoleViewModel,
    configuration: ConfigurationViewModel,
) -> OperatorConsoleViewModel:
    return OperatorConsoleViewModel(
        pages=model.pages,
        dashboard=model.dashboard,
        research=model.research,
        portfolio=model.portfolio,
        paper_page=model.paper_page,
        market_data=model.market_data,
        paper=model.paper,
        safety=model.safety,
        configuration=configuration,
        results=model.results,
        diagnostics=model.diagnostics,
        live_locked=model.live_locked,
    )


def _has_result(result: ResultHistoryViewModel) -> bool:
    return result.latest_run != "无" or bool(result.history)


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


def _render_result_history(ui: OperatorConsoleUI, result: ResultHistoryViewModel) -> None:
    if not result.history:
        return
    ui.subheader(labels.section_label("result_history"))
    for index, item in enumerate(result.history, start=1):
        reason = ""
        if item.reason:
            reason = f", {labels.result_label('reason')}: {labels.reason_label(item.reason)}"
        ui.markdown(
            f"{index}. {item.mode} - "
            f"{labels.result_label('session status')}: {labels.status_label(item.session_status)}, "
            f"{labels.result_label('db delta')}: {item.db_delta}, "
            f"{labels.result_label('target type')}: {labels.safety_label(item.target)}"
            f"{reason}"
        )


def _render_command_preview(ui: OperatorConsoleUI, preview: CommandPreview) -> None:
    _render_key_values(
        ui,
        (
            ("account_id", preview.account_id),
            ("trading_day", preview.trading_day),
            ("instrument_id", preview.instrument_id),
            ("trade_instrument_id", preview.trade_instrument_id),
            ("symbol", preview.symbol),
            ("exchange", preview.exchange),
            ("direction_offset", f"{preview.direction} / {preview.offset}"),
            ("quantity", preview.quantity),
            ("price", preview.price),
            ("target", labels.safety_label(preview.target)),
            ("dry_run", preview.dry_run),
            ("db_write", preview.db_write),
        ),
    )


def _render_resolver_preview(
    ui: OperatorConsoleUI,
    resolution: object,
    allowed_instruments: tuple[str, ...] = (),
) -> None:
    _render_key_values(
        ui,
        (
            ("resolver_notice", "当前为本地静态合约映射，不是真实行情源，不会连接交易所"),
            ("resolver_status", str(getattr(resolution, "status", ""))),
            (
                "instrument_id",
                _resolver_generated_value(
                    str(getattr(resolution, "instrument_id", "") or "未解析")
                ),
            ),
            (
                "trade_instrument_id",
                _resolver_generated_value(
                    str(getattr(resolution, "trade_instrument_id", "") or "未解析")
                ),
            ),
            (
                "exchange",
                _resolver_generated_value(
                    str(getattr(resolution, "exchange", "") or "未解析")
                ),
            ),
            (
                "resolver_source",
                _resolver_source_label(str(getattr(resolution, "source", "") or "")),
            ),
            ("resolver_confidence", str(getattr(resolution, "confidence", "") or "none")),
            (
                "current_whitelist",
                _resolver_whitelist_value(allowed_instruments),
            ),
            (
                "effective_window",
                _effective_window(
                    getattr(resolution, "effective_from", None),
                    getattr(resolution, "effective_to", None),
                ),
            ),
        ),
    )


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


def _render_card(ui: OperatorConsoleUI, title: str, lines: tuple[object, ...]) -> None:
    container = ui.container()
    container.markdown(f"### {title}")
    for line in lines:
        container.markdown(_card_line(line))


def _card_line(line: object) -> str:
    if isinstance(line, tuple) and len(line) == 2:
        key, value = line
        return f"- **{labels.field_label(str(key))}:** {value}"
    return str(line)


def _render_key_values(
    ui: OperatorConsoleUI,
    items: tuple[tuple[str, str], ...],
) -> None:
    lines = tuple(f"- **{labels.field_label(key)}:** {value}" for key, value in items)
    ui.markdown("\n".join(lines))


def _read_config_form(
    ui: OperatorConsoleUI,
    current: ConsoleDryRunConfig,
) -> ConsoleDryRunConfig:
    first_row = ui.columns(4)
    second_row = ui.columns(4)
    third_row = ui.columns(4)
    account_id = first_row[0].text_input(
        labels.field_label("account_id"),
        value=current.account_id,
        key="operator_console_config_account_id",
    )
    symbol = first_row[1].text_input(
        labels.field_label("symbol"),
        value=current.symbol,
        key="operator_console_config_symbol",
    )
    trading_day = first_row[2].text_input(
        labels.field_label("trading_day"),
        value=current.trading_day,
        key="operator_console_config_trading_day",
    )
    default_allowed_instruments = _default_allowed_instruments(
        symbol=symbol,
        trading_day=trading_day,
        current=current.allowed_instruments,
    )
    allowed_instruments = first_row[3].text_input(
        labels.field_label("allowed instruments"),
        value=format_allowed_instruments(default_allowed_instruments),
        key="operator_console_config_allowed_instruments",
    )
    quantity = second_row[0].number_input(
        labels.field_label("quantity"),
        value=current.quantity,
        key="operator_console_config_quantity",
    )
    price = second_row[1].number_input(
        labels.field_label("price"),
        value=current.price,
        key="operator_console_config_price",
    )
    max_order_size = third_row[0].number_input(
        labels.field_label("max_order_size"),
        value=current.max_order_size,
        key="operator_console_config_max_order_size",
    )
    max_position_size = third_row[1].number_input(
        labels.field_label("max_position_size"),
        value=current.max_position_size,
        key="operator_console_config_max_position_size",
    )
    max_daily_loss = third_row[2].number_input(
        labels.field_label("max_daily_loss"),
        value=current.max_daily_loss,
        key="operator_console_config_max_daily_loss",
    )
    config = ConsoleDryRunConfig(
        account_id=account_id,
        trading_day=trading_day,
        instrument_id=current.instrument_id,
        trade_instrument_id=current.trade_instrument_id,
        symbol=symbol,
        exchange=current.exchange,
        quantity=quantity,
        price=price,
        max_order_size=max_order_size,
        max_position_size=max_position_size,
        max_daily_loss=max_daily_loss,
        allowed_instruments=parse_allowed_instruments(allowed_instruments),
        is_example=current.is_example,
        target="MOCK only",
        apply_requested=False,
    )
    ui.set_session_value("operator_console_dry_run_config", config)
    return config


def _normal_config_items(config: ConsoleDryRunConfig) -> tuple[tuple[str, str], ...]:
    return (
        ("account_id", _display_config_value(config.account_id, config.is_example)),
        ("symbol", _display_config_value(config.symbol, config.is_example)),
        ("trading_day", _display_config_value(config.trading_day, config.is_example)),
        ("quantity", _display_config_value(config.quantity, config.is_example)),
        ("price", _display_config_value(config.price, config.is_example)),
        (
            "instrument whitelist",
            _display_config_value(
                format_allowed_instruments(config.allowed_instruments),
                config.is_example,
            ),
        ),
        ("max order size", _display_config_value(config.max_order_size, config.is_example)),
        ("max position size", _display_config_value(config.max_position_size, config.is_example)),
        ("max daily loss", _display_config_value(config.max_daily_loss, config.is_example)),
        ("Paper/SIM mode", "PAPER / SIM"),
        ("dry-run/apply", "dry-run only"),
        ("resolver_notice", "当前为本地静态合约映射，不是真实行情源，不会连接交易所"),
    )


def _dry_run_required_items(
    config: ConsoleDryRunConfig,
    missing_fields: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    missing = set(missing_fields)
    resolver_ready = (
        "resolver" not in missing
        and bool(config.symbol.strip())
        and bool(config.trading_day.strip())
        and bool(config.instrument_id.strip())
        and bool(config.trade_instrument_id.strip())
    )
    return (
        ("account_id", _required_display(config.account_id, "account_id", missing)),
        ("trading_day", _required_display(config.trading_day, "trading_day", missing)),
        ("symbol", _required_display(config.symbol, "symbol", missing)),
        ("resolver_status", "已解析" if resolver_ready else "未解析"),
        ("quantity", _required_display(config.quantity, "quantity", missing)),
        ("price", _required_display(config.price, "price", missing)),
        (
            "instrument whitelist",
            _required_display(
                format_allowed_instruments(config.allowed_instruments),
                "allowed instruments",
                missing,
            ),
        ),
        ("max order size", _display_config_value(config.max_order_size, config.is_example)),
        ("max position size", _display_config_value(config.max_position_size, config.is_example)),
        ("max daily loss", _display_config_value(config.max_daily_loss, config.is_example)),
        ("command source / typed command provider", "UI config preview command"),
        ("job_factory", "未配置"),
    )


def _display_config_value(value: str, is_example: bool) -> str:
    cleaned = value.strip()
    if not cleaned:
        return "未配置"
    if is_example:
        return f"示例：{cleaned}"
    return cleaned


def _required_display(value: str, field_name: str, missing_fields: set[str]) -> str:
    if field_name in missing_fields or not value.strip():
        return "未配置"
    return value.strip()


def _effective_window(effective_from: object, effective_to: object) -> str:
    if effective_from is None or effective_to is None:
        return "未解析"
    return f"{effective_from} / {effective_to}"


def _resolver_generated_value(value: str) -> str:
    if value == "未解析":
        return value
    return f"{value}（由 resolver 生成）"


def _resolver_source_label(source: str) -> str:
    if source == "static_fixture":
        return "static fixture only, not live market source"
    if not source:
        return "static fixture only, not live market source"
    return source


def _default_allowed_instruments(
    *,
    symbol: str,
    trading_day: str,
    current: tuple[str, ...],
) -> tuple[str, ...]:
    if current:
        return current
    resolution = InstrumentResolver().resolve(symbol, trading_day)
    if (
        resolution.status is InstrumentResolveStatus.RESOLVED
        and resolution.trade_instrument_id
    ):
        return (resolution.trade_instrument_id,)
    return ()


def _resolver_whitelist_value(allowed_instruments: tuple[str, ...]) -> str:
    if not allowed_instruments:
        return "未配置"
    return f"{format_allowed_instruments(allowed_instruments)}（由 resolver 推荐）"


def _model_with_session_state(
    ui: OperatorConsoleUI,
    model: OperatorConsoleViewModel,
) -> OperatorConsoleViewModel:
    stored_config = ui.session_value("operator_console_dry_run_config")
    stored_history = ui.session_value("operator_console_result_history", ())
    config = (
        stored_config
        if isinstance(stored_config, ConsoleDryRunConfig)
        else model.configuration.dry_run_config
    )
    history = stored_history if isinstance(stored_history, tuple) else model.results.history
    latest = history[0] if history else None
    if config is model.configuration.dry_run_config and history == model.results.history:
        return model
    return OperatorConsoleViewModel(
        pages=model.pages,
        dashboard=model.dashboard,
        research=model.research,
        portfolio=model.portfolio,
        paper_page=model.paper_page,
        market_data=model.market_data,
        paper=model.paper,
        safety=model.safety,
        configuration=ConfigurationViewModel(
            normal=model.configuration.normal,
            advanced=model.configuration.advanced,
            sources=model.configuration.sources,
            dry_run_config=config,
            preview=model.configuration.preview,
            validation=model.configuration.validation,
            dry_run_required=model.configuration.dry_run_required,
        ),
        results=ResultHistoryViewModel(
            items=model.results.items,
            session_status=latest.session_status if latest else model.results.session_status,
            job_status=latest.job_status if latest else model.results.job_status,
            run_status=latest.run_status if latest else model.results.run_status,
            db_delta=latest.db_delta if latest else model.results.db_delta,
            target=latest.target if latest else model.results.target,
            latest_run="dry-run" if latest else model.results.latest_run,
            reason=latest.reason if latest else model.results.reason,
            history=history,
        ),
        diagnostics=model.diagnostics,
        live_locked=model.live_locked,
    )


if __name__ == "__main__":
    main()
