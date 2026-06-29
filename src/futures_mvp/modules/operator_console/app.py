from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from importlib import import_module
from typing import Any, Protocol, cast

from futures_mvp.modules.market_data.data_center import (
    DataCenterService,
    DataCenterSnapshot,
    DataCenterSyncResult,
    DataQualityRow,
    HistoricalCoverageRow,
    InstrumentDataCenterRow,
)
from futures_mvp.modules.market_data.models import InstrumentResolveStatus
from futures_mvp.modules.market_data.resolver import InstrumentResolver
from futures_mvp.modules.market_data.runtime import MarketDataRuntime
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
    BrokerConsoleViewModel,
    ButtonViewModel,
    ConfigurationViewModel,
    ForbiddenActionViewModel,
    OperatorConsoleViewModel,
    OperatorPage,
    ResultHistoryViewModel,
    SessionPageViewModel,
    default_console_view_model,
    market_data_view_model_from_snapshot,
)


@dataclass(frozen=True)
class _PrimaryAction:
    label: str
    action_key: str | None
    disabled: bool
    why_disabled: str
    next_step: str


@dataclass(frozen=True)
class _WorkflowState:
    selected_symbol: str
    can_backtest: bool
    backtest_completed: bool
    paper_completed: bool
    primary_action: _PrimaryAction


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
    market_data_runtime: MarketDataRuntime | None = None,
    historical_ingestion_service: Any | None = None,
    data_center_service: DataCenterService | None = None,
) -> None:
    model = _model_with_session_state(ui, view_model or default_console_view_model())
    data_service = data_center_service or DataCenterService(
        ingestion_service=historical_ingestion_service,
        runtime=market_data_runtime,
    )
    workflow_state = _workflow_state(ui, model, data_service, "AO")
    ui.title(labels.section_label("Operator Console"))
    developer_mode = _select_display_mode(ui)
    selected_page = _select_page(ui, model)
    ui.header(labels.page_title(selected_page.value))
    rendered_model = _render_page(
        ui,
        model,
        selected_page,
        workflow_state=workflow_state,
        developer_mode=developer_mode,
        paper_dry_run=paper_dry_run,
        market_data_runtime=market_data_runtime,
        historical_ingestion_service=historical_ingestion_service,
        data_center_service=data_service,
    )
    if selected_page is OperatorPage.PAPER and _has_result(rendered_model.results):
        ui.divider()
        _render_dry_run_result_summary(ui, rendered_model.results)


def _select_display_mode(ui: OperatorConsoleUI) -> bool:
    selected = ui.selectbox(
        labels.section_label("developer_mode"),
        ("普通用户", "开发者模式"),
        index=0,
        key="operator_console_display_mode",
    )
    return selected == "开发者模式"


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
        "今天要完成什么",
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
    workflow_state: _WorkflowState,
    developer_mode: bool,
    paper_dry_run: DryRunProvider | None,
    market_data_runtime: MarketDataRuntime | None,
    historical_ingestion_service: Any | None,
    data_center_service: DataCenterService,
) -> OperatorConsoleViewModel:
    if page is OperatorPage.DASHBOARD:
        _render_dashboard(ui, model, workflow_state)
    elif page is OperatorPage.CONFIG_CENTER:
        configuration = _render_config_center(
            ui,
            model,
            developer_mode=developer_mode,
            workflow_state=workflow_state,
        )
        return _with_configuration(model, configuration)
    elif page is OperatorPage.DATA_CENTER:
        _render_data_center(
            ui,
            data_center_service,
            developer_mode=developer_mode,
        )
    elif page is OperatorPage.RESEARCH:
        if not workflow_state.can_backtest:
            _render_workflow_gate(ui, workflow_state, "研究页面")
            return model
        if not workflow_state.backtest_completed:
            _render_backtest_entry_gate(ui, workflow_state)
            return model
        _render_research(ui, model)
    elif page is OperatorPage.PORTFOLIO:
        if not workflow_state.can_backtest:
            _render_workflow_gate(ui, workflow_state, "组合页面")
            return model
        if not workflow_state.backtest_completed:
            _render_stage_gate(
                ui,
                page_name="组合页面",
                why="本地库回测还没有完成，组合结果暂时不能查看。",
                next_step="请先完成本地库回测。",
                current_action="完成本地库回测（只读本地历史行情，不连接券商）",
            )
            return model
        _render_portfolio(ui, model)
    elif page is OperatorPage.PAPER:
        if not workflow_state.can_backtest:
            _render_workflow_gate(ui, workflow_state, "纸面模拟页面")
            return model
        if not workflow_state.backtest_completed:
            _render_stage_gate(
                ui,
                page_name="纸面模拟页面",
                why="本地库回测还没有完成，纸面模拟暂时不能查看。",
                next_step="请先完成本地库回测。",
                current_action="完成本地库回测（只读本地历史行情，不连接券商）",
            )
            return model
        provider = paper_dry_run or create_paper_config_dry_run_provider(
            model.configuration.dry_run_config
        )
        if not workflow_state.paper_completed:
            result = _render_paper_not_completed(ui, model.paper, provider)
            if result is not None:
                return _with_result(ui, model, "PAPER", result)
            return model
        _render_paper(ui, model)
        result = _render_session_actions(ui, model.paper, provider)
        if result is not None:
            return _with_result(ui, model, "PAPER", result)
    elif page is OperatorPage.BROKER:
        if not workflow_state.can_backtest:
            _render_workflow_gate(ui, workflow_state, "券商只读页面")
            return model
        if not workflow_state.backtest_completed:
            _render_stage_gate(
                ui,
                page_name="券商只读页面",
                why="本地库回测还没有完成，券商只读对照暂时不能查看。",
                next_step="请先完成本地库回测。",
                current_action="完成本地库回测（只读本地历史行情，不连接券商）",
            )
            return model
        if not workflow_state.paper_completed:
            _render_stage_gate(
                ui,
                page_name="券商只读页面",
                why="纸面模拟还没有完成，券商只读对照暂时不能查看。",
                next_step="请先完成纸面模拟。",
                current_action="查看最近一次纸面模拟结果（只预演，不写账本）",
            )
            return model
        _render_broker(ui, model.broker, developer_mode=developer_mode)
    elif page is OperatorPage.MARKET_DATA:
        if not developer_mode:
            _render_market_data_workflow_only(ui, workflow_state)
            return model
        configuration = _render_market_data(
            ui,
            model,
            developer_mode=developer_mode,
            market_data_runtime=market_data_runtime,
            historical_ingestion_service=historical_ingestion_service,
        )
        return _with_configuration(model, configuration)
    elif page is OperatorPage.DIAGNOSTICS:
        _render_diagnostics(ui, model, developer_mode=developer_mode)
    return model


def _render_dashboard(
    ui: OperatorConsoleUI,
    model: OperatorConsoleViewModel,
    workflow_state: _WorkflowState,
) -> None:
    workflow = model.dashboard.workflow
    _render_card(
        ui,
        labels.section_label("beginner_workflow"),
        (
            ("今天目标", workflow.today_goal),
            ("当前品种", workflow_state.selected_symbol),
            ("下一步", workflow_state.primary_action.next_step),
            (
                "安全说明",
                "首页按钮只引导本地流程，不连接券商，不下单，不启用真实交易。",
            ),
        ),
    )
    first_row = ui.columns(2)
    _render_card(
        first_row[0],
        labels.section_label("workflow_status"),
        (
            ("数据准备", "未完成"),
            ("是否可以回测", "可以" if workflow_state.can_backtest else "不能"),
            ("纸面模拟", "前置条件完成后可查看"),
            ("券商对照", "前置条件完成后可查看"),
        ),
    )
    _render_card(
        first_row[1],
        labels.section_label("safety_lock_card"),
        (
            "实盘禁用",
            "券商只读",
            "CTP / SimNow 禁用",
            "真实资金禁用",
            labels.safety_label(model.dashboard.execution_target_status),
        ),
    )
    _render_workflow_steps(ui, workflow.steps, workflow_state.primary_action)


def _render_workflow_steps(
    ui: OperatorConsoleUI,
    steps: tuple[object, ...],
    primary_action: _PrimaryAction,
) -> None:
    ui.subheader(labels.section_label("workflow_board"))
    for item in steps:
        title = getattr(item, "title", "")
        status = getattr(item, "status", "")
        summary = getattr(item, "summary", "")
        why = getattr(item, "why", "")
        safe_result = getattr(item, "safe_result", "")
        next_step = getattr(item, "next_step", "")
        action_label = getattr(item, "action_label", "")
        action_key = getattr(item, "action_key", None)
        _render_card(
            ui,
            f"{getattr(item, 'step_no', '')}. {title}",
            (
                ("状态", status),
                ("说明", summary),
                ("为什么", why),
                ("安全吗", safe_result),
                ("下一步", next_step),
                ("按钮后果", action_label),
            ),
        )
        if action_key == primary_action.action_key:
            ui.button(primary_action.label, disabled=primary_action.disabled, key=str(action_key))
        elif action_key:
            ui.markdown(f"当前不能点：{primary_action.next_step}")


def _workflow_state(
    ui: OperatorConsoleUI,
    model: OperatorConsoleViewModel,
    service: DataCenterService,
    selected_symbol: str,
) -> _WorkflowState:
    snapshot = service.snapshot()
    instrument = _data_center_instrument(snapshot, selected_symbol)
    coverage = _data_center_coverage(snapshot, selected_symbol)
    quality = _data_center_quality(snapshot, selected_symbol)
    primary_action = _data_center_primary_action(
        selected_symbol=selected_symbol,
        instrument=instrument,
        coverage=coverage,
        quality=quality,
    )
    can_backtest = primary_action.action_key == "data_center:open_backtest"
    backtest_completed = ui.session_value(
        "operator_console_backtest_completed",
        False,
    ) is True
    paper_completed = (
        ui.session_value("operator_console_paper_completed", False) is True
        or _paper_result_completed(model.results)
    )
    return _WorkflowState(
        selected_symbol=selected_symbol,
        can_backtest=can_backtest,
        backtest_completed=backtest_completed,
        paper_completed=paper_completed,
        primary_action=primary_action,
    )


def _paper_result_completed(result: ResultHistoryViewModel) -> bool:
    return (
        result.run_status == "DRY_RUN_COMPLETED"
        and result.db_delta == 0
        and result.target == "MOCK only"
    )


def _workflow_allows_business_page(
    ui: OperatorConsoleUI,
    workflow_state: _WorkflowState,
    page_name: str,
) -> bool:
    if workflow_state.can_backtest:
        return True
    _render_workflow_gate(ui, workflow_state, page_name)
    return False


def _render_workflow_gate(
    ui: OperatorConsoleUI,
    workflow_state: _WorkflowState,
    page_name: str,
) -> None:
    _render_card(
        ui,
        f"{page_name}暂时不能进入",
        (
            ("为什么", workflow_state.primary_action.why_disabled),
            ("下一步", workflow_state.primary_action.next_step),
            (
                "安全吗",
                "系统没有连接券商，没有下单，没有写入交易数据。",
            ),
            ("当前主操作", workflow_state.primary_action.label),
        ),
    )


def _render_stage_gate(
    ui: OperatorConsoleUI,
    *,
    page_name: str,
    why: str,
    next_step: str,
    current_action: str,
) -> None:
    _render_card(
        ui,
        f"{page_name}暂时不能进入",
        (
            ("为什么", why),
            ("下一步", next_step),
            ("安全吗", "系统没有连接券商，没有下单，没有写入交易数据。"),
            ("当前主操作", current_action),
        ),
    )


def _render_backtest_entry_gate(
    ui: OperatorConsoleUI,
    workflow_state: _WorkflowState,
) -> None:
    _render_card(
        ui,
        "本地库回测可以开始",
        (
            ("为什么", "历史行情覆盖和数据质量已通过，但本地库回测还没有完成。"),
            ("下一步", "请先完成本地库回测。"),
            ("安全吗", "这里只读本地历史行情，不连接券商，不下单。"),
            (
                "当前主操作",
                f"完成 {workflow_state.selected_symbol} 本地库回测"
                "（只读历史行情，不连接券商）",
            ),
        ),
    )


def _render_market_data_workflow_only(
    ui: OperatorConsoleUI,
    workflow_state: _WorkflowState,
) -> None:
    _render_card(
        ui,
        "行情数据当前任务",
        (
            ("当前主操作", workflow_state.primary_action.label),
            ("为什么", workflow_state.primary_action.why_disabled),
            ("下一步", workflow_state.primary_action.next_step),
            ("安全吗", "普通模式不启动行情运行时，不自动联网，不连接券商，不下单。"),
        ),
    )


def _render_config_center(
    ui: OperatorConsoleUI,
    model: OperatorConsoleViewModel,
    *,
    developer_mode: bool,
    workflow_state: _WorkflowState,
) -> ConfigurationViewModel:
    config = (
        _read_config_form(ui, model.configuration.dry_run_config)
        if developer_mode
        else model.configuration.dry_run_config
    )
    assembly = assemble_config(config)
    ui.set_session_value("operator_console_dry_run_config", assembly.config)
    center = model.config_center
    _render_card(
        ui,
        "当前任务状态",
        (
            ("我是谁", "本地样例账户"),
            ("我要跑哪个品种", workflow_state.selected_symbol),
            ("我要跑哪一天", "先按数据中心同步区间准备历史行情"),
            ("我要使用什么数据", "本地历史行情"),
            ("当前能不能回测", "可以" if workflow_state.can_backtest else "不能"),
            ("当前是不是只读", "是，只读查看和本地预演"),
            ("当前是否允许实盘", "不允许"),
            ("下一步", workflow_state.primary_action.next_step),
        ),
    )
    if not developer_mode:
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
    first_row = ui.columns(3)
    _render_card(first_row[0], labels.section_label("basic_config"), center.basic)
    _render_card(first_row[1], labels.section_label("research_config"), center.research)
    _render_card(first_row[2], labels.section_label("paper_config"), center.paper)
    second_row = ui.columns(3)
    _render_card(second_row[0], labels.section_label("broker_config"), center.broker)
    _render_card(second_row[1], labels.section_label("market_data_config"), center.market_data)
    _render_card(second_row[2], labels.section_label("safety_lock"), center.safety_locks)
    preview_row = ui.columns(2)
    _render_card(
        preview_row[0],
        "本次任务配置",
        _run_preview_items(assembly.config, center.run_preview),
    )
    _render_check_items(preview_row[1], center.checks)
    if developer_mode:
        _render_card(
            ui,
            labels.section_label("developer_diagnostics"),
            (
                ("命令来源", "typed config object / UI session state"),
                ("配置预览", "仅用于预演，不落库"),
                ("交易目标", "仅本地模拟"),
            ),
        )
    return ConfigurationViewModel(
        normal=_normal_config_items(config),
        advanced=model.configuration.advanced,
        sources=model.configuration.sources,
        dry_run_config=assembly.config,
        preview=assembly.preview,
        validation=assembly.validation,
        market_data_sources=model.configuration.market_data_sources,
        dry_run_required=_dry_run_required_items(
            assembly.config,
            assembly.validation.missing_fields,
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
        (
            ("状态", labels.status_label(paper.runtime_status)),
            ("为什么", "纸面模拟用于确认本地流程是否跑通"),
            ("安全吗", "默认只预演，不写账本，不连接真实交易所"),
        ),
    )
    _render_card(top[1], labels.section_label("paper_lifecycle"), paper.lifecycle)
    _render_card(top[2], labels.section_label("paper_consistency"), paper.consistency)
    bottom = ui.columns(4)
    _render_card(bottom[0], labels.section_label("paper_orders"), paper.orders)
    _render_card(bottom[1], labels.section_label("paper_fills"), paper.fills)
    _render_card(bottom[2], labels.section_label("paper_positions"), paper.positions)
    _render_card(bottom[3], labels.section_label("paper_portfolio"), paper.portfolio)
    ui.markdown("当前页面只用于查看纸面模拟，不会登录券商，不会下单。")


def _render_paper_not_completed(
    ui: OperatorConsoleUI,
    session: SessionPageViewModel,
    provider: DryRunProvider | None,
) -> DryRunActionResult | None:
    _render_card(
        ui,
        "纸面模拟尚未完成",
        (
            ("为什么", "本地库回测已完成，但还没有纸面模拟结果。"),
            ("下一步", "查看最近一次纸面模拟结果，确认只预演、不写账本。"),
            ("安全吗", "纸面模拟只预演，不连接真实交易所，不写交易账本。"),
            ("当前主操作", labels.action_label(session.dry_run_button.action_key)),
        ),
    )
    return _render_dry_run_button(ui, session, provider)


def _render_broker(
    ui: OperatorConsoleUI,
    broker: BrokerConsoleViewModel,
    *,
    developer_mode: bool = False,
) -> None:
    top = ui.columns(4)
    _render_card(
        top[0],
        labels.section_label("broker_status"),
        (
            ("状态", "只读可查看"),
            ("为什么", "这是样例快照和只读对照，不是真实登录状态"),
            ("安全吗", "不登录、不重试、不报单、不撤单、不写数据库"),
        ),
    )
    _render_card(top[1], labels.section_label("broker_accounts"), broker.accounts)
    _render_card(top[2], labels.section_label("broker_shadow_compare"), broker.shadow_compare)
    _render_card(
        top[3],
        labels.section_label("safe_result"),
        (
            "不会登录券商",
            "不会提交委托",
            "不会撤销委托",
            "不会写入交易数据库",
        ),
    )
    middle = ui.columns(4)
    _render_card(middle[0], labels.section_label("broker_positions"), broker.positions)
    _render_card(middle[1], labels.section_label("broker_orders"), broker.orders)
    _render_card(middle[2], labels.section_label("broker_trades"), broker.trades)
    _render_card(middle[3], labels.section_label("broker_differences"), broker.differences)
    ui.markdown(labels.section_label("broker_read_only_notice"))
    if developer_mode:
        _render_card(ui, labels.section_label("developer_diagnostics"), broker.diagnostics)


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
    *,
    developer_mode: bool = False,
    market_data_runtime: MarketDataRuntime | None,
    historical_ingestion_service: Any | None,
) -> ConfigurationViewModel:
    runtime = market_data_runtime or MarketDataRuntime()
    runtime_snapshot = runtime.health()
    ui.set_session_value("operator_console_market_data_runtime_snapshot", runtime_snapshot)
    runtime_market_data = market_data_view_model_from_snapshot(runtime_snapshot)
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
    market_data = runtime_market_data
    top = ui.columns(4)
    _render_card(
        top[0],
        "当前行情选择",
        (_data_source_display(source),),
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
    _render_card(top[3], "合约信息来源", ("本地合约映射",))
    runtime_row = ui.columns(4)
    _render_card(
        runtime_row[0],
        labels.section_label("runtime_status"),
        (labels.status_label(market_data.runtime_status),),
    )
    _render_card(
        runtime_row[1],
        labels.section_label("runtime_started"),
        (market_data.runtime_started,),
    )
    _render_card(
        runtime_row[2],
        labels.section_label("runtime_configured"),
        (market_data.runtime_configured,),
    )
    _render_card(
        runtime_row[3],
        labels.section_label("runtime_source"),
        (_data_source_display(market_data.selected_source),),
    )
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
    if developer_mode:
        _render_card(bottom[3], labels.section_label("source_diagnostics"), market_data.diagnostics)
    else:
        _render_card(
            bottom[3],
            labels.section_label("safe_result"),
            (
                "不会连接券商",
                "不会下单",
                "不会启用真实交易",
                "未配置时不会访问网络",
            ),
        )
    status_row = ui.columns(1)
    _render_card(
        status_row[0],
        labels.section_label("symbol_status"),
        market_data.symbol_statuses,
    )
    sync_symbol = ui.text_input(
        labels.field_label("historical_symbol"),
        value=dict(market_data.historical_sync_controls).get("品种", "ao"),
        key="historical_data_sync:symbol",
    )
    sync_day_text = ui.text_input(
        labels.field_label("historical_trading_day"),
        value=dict(market_data.historical_sync_controls).get("开始日期", "2026-06-12"),
        key="historical_data_sync:trading_day",
    )
    sync_end_day_text = ui.text_input(
        labels.field_label("historical_end_trading_day"),
        value=dict(market_data.historical_sync_controls).get("结束日期", sync_day_text),
        key="historical_data_sync:end_trading_day",
    )
    sync_timeframe = ui.selectbox(
        labels.field_label("historical_timeframe"),
        ("1m", "5m", "15m", "1h", "1d"),
        index=0,
        key="historical_data_sync:timeframe",
    )
    coverage_row = ui.columns(2)
    _render_card(
        coverage_row[0],
        labels.section_label("historical_sync_controls"),
        (
            ("品种", sync_symbol),
            ("开始日期", sync_day_text),
            ("结束日期", sync_end_day_text),
            ("周期", sync_timeframe),
            ("动作", "仅同步历史行情"),
        ),
    )
    _render_card(
        coverage_row[1],
        labels.section_label("historical_coverage"),
        market_data.historical_coverage,
    )
    action_row = ui.columns(3)
    if action_row[0].button(
        labels.action_label("Start Market Data Runtime"),
        disabled=False,
        key="market_data_runtime:start",
    ):
        runtime_snapshot = runtime.start()
        ui.set_session_value("operator_console_market_data_runtime_snapshot", runtime_snapshot)
        _render_card(
            action_row[0],
            labels.section_label("runtime_status"),
            (labels.status_label(runtime_snapshot.status),),
        )
    if action_row[1].button(
        labels.action_label("Stop Market Data Runtime"),
        disabled=False,
        key="market_data_runtime:stop",
    ):
        runtime_snapshot = runtime.stop()
        ui.set_session_value("operator_console_market_data_runtime_snapshot", runtime_snapshot)
        _render_card(
            action_row[1],
            labels.section_label("runtime_status"),
            (labels.status_label(runtime_snapshot.status),),
        )
    if action_row[2].button(
        labels.action_label("Poll Market Data Once"),
        disabled=False,
        key="market_data_runtime:poll_once",
    ):
        runtime_snapshot = runtime.poll_once(market_data.supported_symbols)
        ui.set_session_value("operator_console_market_data_runtime_snapshot", runtime_snapshot)
        _render_card(
            action_row[2],
            labels.section_label("runtime_status"),
            (labels.status_label(runtime_snapshot.status),),
        )
    sync_action_row = ui.columns(1)
    if sync_action_row[0].button(
        f"同步 {sync_symbol.upper()} 历史行情（不连接券商，不下单）",
        disabled=False,
        key="historical_data_sync:run",
    ):
        sync_lines = _sync_historical_bars(
            historical_ingestion_service,
            sync_symbol,
            sync_day_text,
            sync_end_day_text,
            sync_timeframe,
        )
        _render_card(
            sync_action_row[0],
            labels.section_label("historical_sync_result"),
            sync_lines,
        )
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


def _render_data_center(
    ui: OperatorConsoleUI,
    service: DataCenterService,
    *,
    developer_mode: bool = False,
) -> None:
    snapshot = service.snapshot()
    selected_symbol = ui.selectbox(
        labels.field_label("data_center_symbol"),
        ("请选择品种", "AO", "RB", "AG", "CU"),
        index=1,
        key="data_center:selected_symbol",
    )
    if selected_symbol == "请选择品种":
        _render_card(
            ui,
            "当前主操作",
            (
                ("状态", "等待选择品种"),
                ("为什么不能点", "还不知道要准备哪个品种的历史行情。"),
                ("下一步做什么", "先在左侧选择 AO、RB、AG 或 CU。"),
                ("按钮后果", "选择品种只改变页面展示，不联网，不下单。"),
            ),
        )
        return
    symbol = selected_symbol.lower()
    instrument = _data_center_instrument(snapshot, selected_symbol)
    coverage = _data_center_coverage(snapshot, selected_symbol)
    quality = _data_center_quality(snapshot, selected_symbol)
    source = snapshot.data_sources[0]
    can_backtest = coverage.bar_count > 0 and quality.coverage_ratio != "0%"

    top = ui.columns(2)
    _render_card(
        top[0],
        labels.section_label("data_center_instruments"),
        (
            ("品种名称", selected_symbol),
            ("品种映射", instrument.mapping),
            ("合约解析", instrument.status),
            ("主力合约", instrument.main_contract),
            ("交易合约", instrument.trade_contract),
            ("交易所", instrument.exchange),
        ),
    )
    _render_card(
        top[1],
        "当前品种能不能准备",
        (
            ("行情服务", "已配置" if source.enabled else "未配置"),
            ("当前结论", "不能回测" if not can_backtest else "可以回测"),
            ("为什么", "本地历史行情还没有覆盖" if not can_backtest else "覆盖和质量已通过"),
            ("安全吗", "不会自动联网，不连接券商，不下单"),
        ),
    )

    workflow = ui.columns(1)
    _render_card(
        workflow[0],
        labels.section_label("data_center_step_config"),
        (
            ("状态", "已通过" if instrument.status == "可用" else "已阻断"),
            ("行情映射", "可用" if instrument.mapping != "未解析" else "未配置"),
            ("合约信息", "可用" if instrument.trade_contract != "未解析" else "未解析"),
            ("安全吗", "只读取本地配置，不连接券商"),
            ("下一步", "同步该品种历史行情"),
        ),
    )

    ui.subheader(labels.section_label("data_center_step_sync"))
    start_text = ui.text_input(
        labels.field_label("data_center_start"),
        value="2024-01-01",
        key="data_center:sync_start",
    )
    end_text = ui.text_input(
        labels.field_label("data_center_end"),
        value="2026-06-30",
        key="data_center:sync_end",
    )
    timeframe = ui.selectbox(
        labels.field_label("data_center_timeframe"),
        ("1m", "5m", "15m", "1h", "1d"),
        index=0,
        key="data_center:timeframe",
    )
    step_rows = ui.columns(1)
    _render_card(
        step_rows[0],
        "同步设置",
        (
            ("开始日期", start_text),
            ("结束日期", end_text),
            ("时间周期", timeframe),
            ("按钮后果", "只同步当前品种历史行情；不会连接券商，不会下单"),
        ),
    )
    primary_action = _data_center_primary_action(
        selected_symbol=selected_symbol,
        instrument=instrument,
        coverage=coverage,
        quality=quality,
    )
    _render_card(
        ui,
        "当前主操作",
        (
            ("按钮", primary_action.label),
            ("为什么不能点", primary_action.why_disabled),
            ("下一步做什么", primary_action.next_step),
        ),
    )
    if (
        primary_action.action_key == "data_center:sync_selected"
        and ui.button(
            primary_action.label,
            disabled=primary_action.disabled,
            key=primary_action.action_key,
        )
    ):
        result = _run_data_center_sync(service, symbol, start_text, end_text, timeframe)
        _render_card(
            ui,
            labels.section_label("data_center_sync_result"),
            _data_center_sync_result_rows(result),
        )
    if (
        primary_action.action_key == "data_center:check_coverage"
        and ui.button(
            primary_action.label,
            disabled=primary_action.disabled,
            key=primary_action.action_key,
        )
    ):
        checked = service.snapshot(timeframe=timeframe)
        _render_card(
            ui,
            labels.section_label("data_center_coverage"),
            _selected_coverage_rows(checked, selected_symbol),
        )
    if (
        primary_action.action_key == "data_center:check_quality"
        and ui.button(
            primary_action.label,
            disabled=primary_action.disabled,
            key=primary_action.action_key,
        )
    ):
        checked = service.snapshot(timeframe=timeframe)
        _render_card(
            ui,
            labels.section_label("data_quality_result"),
            _selected_quality_rows(checked, selected_symbol),
        )
    if (
        primary_action.action_key == "data_center:open_backtest"
        and ui.button(
            primary_action.label,
            disabled=primary_action.disabled,
            key=primary_action.action_key,
        )
    ):
        _render_card(
            ui,
            "本地库回测入口",
            (
                ("状态", "可以进入"),
                ("为什么", "当前品种已有历史行情覆盖，可以用于本地库回测。"),
                ("安全吗", "这里只读本地历史行情，不连接券商，不下单。"),
                ("下一步", "打开研究页面查看本地库回测结果。"),
            ),
        )

    bottom = ui.columns(1)
    _render_card(
        bottom[0],
        labels.section_label("data_center_step_coverage"),
        (
            ("覆盖开始", coverage.coverage_start),
            ("覆盖结束", coverage.coverage_end),
            ("K 线数量", str(coverage.bar_count)),
            ("覆盖率", quality.coverage_ratio),
            ("缺失情况", "无" if quality.missing_bars == 0 else str(quality.missing_bars)),
            (
                "为什么",
                "无" if can_backtest else _no_local_data_text(selected_symbol, "1m"),
            ),
            ("安全吗", "没有自动联网，没有写入交易数据"),
            ("下一步", "同步历史行情后再检查覆盖"),
        ),
    )
    _render_card(
        bottom[0],
        labels.section_label("data_center_step_quality"),
        _selected_quality_rows(snapshot, selected_symbol),
    )
    _render_card(
        bottom[0],
        labels.section_label("data_center_step_backtest"),
        (
            ("当前是否可用于回测", "可以回测" if can_backtest else "请先同步历史行情"),
            (
                "下一步",
                "去研究页面查看本地库回测入口"
                if can_backtest
                else "先同步，再检查覆盖和质量",
            ),
        ),
    )
    if developer_mode:
        _render_card(
            ui,
            labels.section_label("developer_diagnostics"),
            (
                ("合约解析", snapshot.diagnostics.resolver),
                ("本地历史库", snapshot.diagnostics.repository),
                ("历史K线", snapshot.diagnostics.historical_bar),
                ("AkShare", snapshot.diagnostics.akshare),
                ("同步服务", snapshot.diagnostics.sync_service),
                ("数据库", snapshot.diagnostics.database),
                ("下一步建议", "覆盖通过后进入研究页面运行本地库回测"),
            ),
        )
    ui.markdown("数据中心只负责数据、质量、同步、覆盖和管理。")
    ui.markdown("保持在行情数据链路内，不进入交易链路。")


def _data_center_primary_action(
    *,
    selected_symbol: str,
    instrument: InstrumentDataCenterRow,
    coverage: HistoricalCoverageRow,
    quality: DataQualityRow,
) -> _PrimaryAction:
    if instrument.mapping == "未解析":
        return _PrimaryAction(
            label="检查品种映射（只读本地配置）",
            action_key=None,
            disabled=True,
            why_disabled="品种映射缺失，当前不能同步历史行情。",
            next_step="先补齐品种映射，再回到数据中心检查配置。",
        )
    if instrument.trade_contract == "未解析":
        return _PrimaryAction(
            label="检查合约解析（只读本地配置）",
            action_key=None,
            disabled=True,
            why_disabled="交易合约没有解析出来，当前不能同步历史行情。",
            next_step="先确认合约解析结果，再同步历史行情。",
        )
    if coverage.latest_sync == "未同步":
        return _PrimaryAction(
            label=f"同步 {selected_symbol} 历史行情（不连接券商，不下单）",
            action_key="data_center:sync_selected",
            disabled=False,
            why_disabled="当前可以点击。尚未同步历史行情，回测没有可用输入。",
            next_step=f"点击同步 {selected_symbol} 历史行情。",
        )
    if coverage.bar_count == 0:
        return _PrimaryAction(
            label=f"检查 {selected_symbol} 覆盖率（只读本地数据）",
            action_key="data_center:check_coverage",
            disabled=False,
            why_disabled="当前可以点击。历史行情同步后还没有确认覆盖率。",
            next_step=f"点击检查 {selected_symbol} 覆盖率。",
        )
    if quality.sync_status != "正常":
        return _PrimaryAction(
            label=f"检查 {selected_symbol} 数据质量（只读本地数据）",
            action_key="data_center:check_quality",
            disabled=False,
            why_disabled="当前可以点击。覆盖已有数据，但质量还没有确认通过。",
            next_step=f"点击检查 {selected_symbol} 数据质量。",
        )
    return _PrimaryAction(
        label=f"进入本地库回测（只读 {selected_symbol} 历史行情）",
        action_key="data_center:open_backtest",
        disabled=False,
        why_disabled="当前可以点击。覆盖和质量已通过。",
        next_step="进入研究页面查看本地库回测结果。",
    )


def _data_center_instrument(
    snapshot: DataCenterSnapshot,
    symbol: str,
) -> InstrumentDataCenterRow:
    for row in snapshot.instruments:
        if row.symbol == symbol.upper():
            return row
    return snapshot.instruments[0]


def _data_center_coverage(
    snapshot: DataCenterSnapshot,
    symbol: str,
) -> HistoricalCoverageRow:
    for row in snapshot.coverage:
        if row.symbol == symbol.upper():
            return row
    return snapshot.coverage[0]


def _data_center_quality(
    snapshot: DataCenterSnapshot,
    symbol: str,
) -> DataQualityRow:
    for row in snapshot.quality:
        if row.symbol == symbol.upper():
            return row
    return snapshot.quality[0]


def _selected_coverage_rows(
    snapshot: DataCenterSnapshot,
    symbol: str,
) -> tuple[tuple[str, str], ...]:
    coverage = _data_center_coverage(snapshot, symbol)
    quality = _data_center_quality(snapshot, symbol)
    return (
        ("覆盖开始", coverage.coverage_start),
        ("覆盖结束", coverage.coverage_end),
        ("K 线数量", str(coverage.bar_count)),
        ("最近同步时间", coverage.latest_sync),
        ("覆盖率", quality.coverage_ratio),
        ("缺失情况", "无" if quality.missing_bars == 0 else str(quality.missing_bars)),
    )


def _selected_quality_rows(
    snapshot: DataCenterSnapshot,
    symbol: str,
) -> tuple[tuple[str, str], ...]:
    quality = _data_center_quality(snapshot, symbol)
    return (
        ("缺失 K 线", str(quality.missing_bars)),
        ("重复 K 线", str(quality.duplicate_bars)),
        ("异常 K 线", str(quality.abnormal_bars)),
        ("连续性", quality.continuity),
        ("缺口", str(quality.gap_count)),
        ("同步状态", quality.sync_status),
    )


def _no_local_data_text(symbol: str, timeframe: str) -> str:
    return (
        f"本地历史库暂无 {symbol.upper()} 的 {timeframe} 数据。"
        "系统没有访问外部行情，也没有写入交易数据。"
        "请先点击“同步该品种历史行情”。"
    )


def _run_data_center_sync(
    service: DataCenterService,
    symbol: str,
    start_text: str,
    end_text: str,
    timeframe: str,
) -> DataCenterSyncResult:
    try:
        start = date.fromisoformat(start_text.strip())
        end = date.fromisoformat(end_text.strip())
    except ValueError:
        return DataCenterSyncResult(
            status="已阻断",
            added=0,
            updated=0,
            skipped=0,
            failed=1,
            elapsed_ms=0,
            diagnostics=("日期格式无效", "未进入券商，未启用交易目标"),
        )
    return service.sync_history(
        symbol=symbol.strip(),
        start=start,
        end=end,
        timeframe=timeframe,
    )


def _data_center_sync_result_rows(
    result: DataCenterSyncResult,
) -> tuple[tuple[str, str], ...]:
    return (
        ("状态", result.status),
        ("新增", str(result.added)),
        ("更新", str(result.updated)),
        ("跳过", str(result.skipped)),
        ("失败", str(result.failed)),
        ("耗时", f"{result.elapsed_ms}ms"),
        *tuple(("诊断", item) for item in result.diagnostics),
    )


def _sync_historical_bars(
    service: Any | None,
    symbol: str,
    trading_day_text: str,
    end_trading_day_text: str,
    timeframe: str,
) -> tuple[object, ...]:
    if service is None:
        return (
            ("状态", "已阻断"),
            ("失败原因", "历史行情同步服务未配置"),
            ("安全边界", "未进入交易链路，未连接券商，未启用交易目标"),
        )
    try:
        trading_day = date.fromisoformat(trading_day_text.strip())
        end_trading_day = date.fromisoformat(end_trading_day_text.strip())
    except ValueError:
        return (
            ("状态", "已阻断"),
            ("失败原因", "交易日格式无效"),
            ("安全边界", "未进入交易链路，未连接券商，未启用交易目标"),
        )
    result = service.ingest_symbol(
        symbol.strip(),
        trading_day,
        timeframe,
        end_trading_day=end_trading_day,
    )
    return (
        ("状态", labels.status_label(str(getattr(result, "status", "UNKNOWN")))),
        ("写入条数", str(getattr(result, "bars_written", 0))),
        ("更新条数", str(getattr(result, "bars_updated", 0))),
        ("跳过条数", str(getattr(result, "bars_skipped", 0))),
        ("K 线数量", str(getattr(result, "bar_count", 0))),
        ("覆盖开始", str(getattr(result, "first_bar_ts", None) or "无")),
        ("覆盖结束", str(getattr(result, "latest_bar_ts", None) or "无")),
        ("最近入库时间", str(getattr(result, "latest_ingested_at", None) or "无")),
        ("数据源", str(getattr(result, "source", "只读行情"))),
        ("失败原因", str(getattr(result, "reason", None) or "无")),
        *tuple(("诊断", item) for item in getattr(result, "diagnostics", ())),
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


def _render_diagnostics(
    ui: OperatorConsoleUI,
    model: OperatorConsoleViewModel,
    *,
    developer_mode: bool = False,
) -> None:
    _render_card(
        ui,
        "普通用户安全检查",
        (
            ("行情", "未配置真实行情时不会访问网络"),
            ("纸面模拟", "默认只预演，不写账本"),
            ("券商", "只读展示，不登录，不报单，不撤单"),
            ("交易", "实盘禁用，真实资金未使用"),
            ("下一步", "回到总览，按今日任务流程继续"),
        ),
    )
    if not developer_mode:
        ui.markdown("高级诊断默认隐藏。需要排障时，在左侧打开开发者模式。")
        return
    row = ui.columns(7)
    _render_card(row[0], labels.section_label("resolver_diagnostics"), model.diagnostics.resolver)
    _render_card(
        row[1],
        labels.section_label("market_data_diagnostics"),
        model.diagnostics.market_data,
    )
    _render_card(
        row[2],
        labels.section_label("data_center_diagnostics"),
        model.diagnostics.data_center,
    )
    _render_card(row[3], labels.section_label("broker_diagnostics"), model.diagnostics.broker)
    _render_card(row[4], labels.section_label("research_diagnostics"), model.diagnostics.research)
    _render_card(row[5], labels.section_label("paper_diagnostics"), model.diagnostics.paper)
    _render_card(row[6], labels.section_label("safety_checks"), model.diagnostics.safety)
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


def _render_button(ui: OperatorConsoleUI, button: ButtonViewModel) -> bool:
    clicked = ui.button(
        labels.action_label(button.action_key),
        disabled=button.disabled,
        key=f"action:{button.action_key}",
    )
    if button.disabled:
        ui.markdown(labels.section_label("disabled_placeholder"))
    return clicked


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
    dry_run_col = ui.columns(1)[0]
    result = _render_dry_run_button(dry_run_col, session, provider)
    ui.markdown("纸面模拟写入功能保持关闭；本页面不会写账本，不连接真实交易所。")
    return result


def _with_result(
    ui: OperatorConsoleUI,
    model: OperatorConsoleViewModel,
    mode: str,
    result: DryRunActionResult,
) -> OperatorConsoleViewModel:
    history = append_history(model.results.history, mode=mode, result=result)
    ui.set_session_value("operator_console_result_history", history)
    if (
        result.run_status == "DRY_RUN_COMPLETED"
        and result.db_delta == 0
        and result.target == "MOCK only"
    ):
        ui.set_session_value("operator_console_paper_completed", True)
    return OperatorConsoleViewModel(
        pages=model.pages,
        dashboard=model.dashboard,
        config_center=model.config_center,
        research=model.research,
        portfolio=model.portfolio,
        paper_page=model.paper_page,
        broker=model.broker,
        market_data=model.market_data,
        data_center=model.data_center,
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
        config_center=model.config_center,
        research=model.research,
        portfolio=model.portfolio,
        paper_page=model.paper_page,
        broker=model.broker,
        market_data=model.market_data,
        data_center=model.data_center,
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


def _run_preview_items(
    config: ConsoleDryRunConfig,
    fallback: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    if not any(
        (
            config.account_id.strip(),
            config.symbol.strip(),
            config.trading_day.strip(),
            config.quantity.strip(),
            config.price.strip(),
        )
    ):
        return fallback
    symbols = config.symbol.strip().upper() or "未配置"
    return (
        ("account_id", _display_config_value(config.account_id, config.is_example)),
        ("market_data_source", _data_source_display(config.market_data_source)),
        ("strategy", "BuyAndHold"),
        ("symbols", symbols),
        ("commission", "0.0001"),
        ("slippage", "1 Tick"),
        ("rollout mode", "MOCK"),
    )


def _render_check_items(
    ui: OperatorConsoleUI,
    checks: tuple[tuple[str, str], ...],
) -> None:
    ui.subheader(labels.section_label("config_checks"))
    for key, value in checks:
        ui.markdown(f"✓ {labels.field_label(key)}：{value}")


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
        return "仅静态样例，不是真实行情源"
    if not source:
        return "仅静态样例，不是真实行情源"
    return source


def _data_source_display(source: str) -> str:
    if source == STATIC_FIXTURE_DATA_SOURCE:
        return "静态样例"
    if source == READ_ONLY_ADAPTER_DATA_SOURCE:
        return "只读行情数据"
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
        config_center=model.config_center,
        research=model.research,
        portfolio=model.portfolio,
        paper_page=model.paper_page,
        broker=model.broker,
        market_data=model.market_data,
        data_center=model.data_center,
        paper=model.paper,
        safety=model.safety,
        configuration=ConfigurationViewModel(
            normal=model.configuration.normal,
            advanced=model.configuration.advanced,
            sources=model.configuration.sources,
            dry_run_config=config,
            preview=model.configuration.preview,
            validation=model.configuration.validation,
            market_data_sources=model.configuration.market_data_sources,
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
