from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from futures_mvp.modules.market_data.data_center import DataCenterService
from futures_mvp.modules.market_data.ingestion import (
    HistoricalDataIngestionResult,
    HistoricalIngestionStatus,
)
from futures_mvp.modules.market_data.runtime import MarketDataRuntime
from futures_mvp.modules.operator_console import app, labels
from futures_mvp.modules.operator_console.actions import DryRunActionResult
from futures_mvp.modules.operator_console.app import render_console
from futures_mvp.modules.operator_console.view_models import (
    OperatorPage,
    default_console_view_model,
)


@dataclass
class FakeUI:
    titles: list[str] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    subheaders: list[str] = field(default_factory=list)
    markdowns: list[str] = field(default_factory=list)
    writes: list[object] = field(default_factory=list)
    buttons: list[tuple[str, bool, str | None]] = field(default_factory=list)
    selectboxes: list[tuple[str, tuple[str, ...], int, str | None]] = field(default_factory=list)
    dividers: int = 0
    selected_label: str | None = None
    display_mode: str = "普通用户"
    clicked_labels: set[str] = field(default_factory=set)
    session_state: dict[str, object] = field(default_factory=dict)

    def title(self, body: str) -> None:
        self.titles.append(body)

    def header(self, body: str) -> None:
        self.headers.append(body)

    def subheader(self, body: str) -> None:
        self.subheaders.append(body)

    def markdown(self, body: str) -> None:
        self.markdowns.append(body)

    def write(self, body: object) -> None:
        self.writes.append(body)

    def text_input(self, label: str, *, value: str = "", key: str | None = None) -> str:
        if key is not None:
            self.session_state[key] = value
        return value

    def number_input(self, label: str, *, value: str = "", key: str | None = None) -> str:
        if key is not None:
            self.session_state[key] = value
        return value

    def text_area(self, label: str, *, value: str = "", key: str | None = None) -> str:
        if key is not None:
            self.session_state[key] = value
        return value

    def button(self, label: str, *, disabled: bool = False, key: str | None = None) -> bool:
        self.buttons.append((label, disabled, key))
        return (not disabled) and label in self.clicked_labels

    def selectbox(
        self,
        label: str,
        options: tuple[str, ...],
        *,
        index: int = 0,
        key: str | None = None,
    ) -> str:
        self.selectboxes.append((label, options, index, key))
        if key == "operator_console_display_mode":
            return self.display_mode
        if key == "operator_console_page":
            return self.selected_label or options[index]
        if key == "data_center:selected_symbol":
            return "AO"
        if key in {"data_center:timeframe", "historical_data_sync:timeframe"}:
            return "1m"
        return options[index]

    def columns(self, count: int) -> tuple[FakeUI, ...]:
        return tuple(self for _ in range(count))

    def container(self) -> FakeUI:
        return self

    def divider(self) -> None:
        self.dividers += 1

    def session_value(self, key: str, default: object | None = None) -> object | None:
        return self.session_state.get(key, default)

    def set_session_value(self, key: str, value: object) -> None:
        self.session_state[key] = value


def _rendered(ui: FakeUI) -> str:
    return "\n".join(str(item) for item in [*ui.writes, *ui.subheaders, *ui.markdowns])


def test_home_is_task_driven_for_first_time_user() -> None:
    ui = FakeUI()

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert ui.titles == ["本地操作台"]
    assert ui.headers == ["总览"]
    assert ui.selectboxes[0][0] == "开发者模式"
    assert ui.selectboxes[1][0] == "今天要完成什么"
    assert "### 今天要完成什么" in rendered
    assert "**今天目标:** 完成 AO 历史行情准备，并确认能否进入回测" in rendered
    assert "1. 选择品种" in rendered
    assert "2. 检查配置" in rendered
    assert "3. 同步历史行情" in rendered
    assert "4. 检查覆盖率" in rendered
    assert "5. 检查数据质量" in rendered
    assert "6. 运行回测" in rendered
    assert "7. 查看纸面模拟" in rendered
    assert "8. 查看券商只读对照" in rendered
    assert "不会联网，不会下单" in rendered
    assert ui.buttons == [
        (
            "同步 AO 历史行情（不连接券商，不下单）",
            False,
            "data_center:sync_selected",
        )
    ]


def test_data_center_single_symbol_workflow_and_button_results() -> None:
    class FakeHistoricalIngestionService:
        def ingest_symbol(
            self,
            symbol: str,
            trading_day: date,
            timeframe: str,
            *,
            end_trading_day: date | None = None,
        ) -> HistoricalDataIngestionResult:
            assert symbol == "ao"
            assert trading_day == date(2024, 1, 1)
            assert end_trading_day == date(2026, 6, 30)
            assert timeframe == "1m"
            return HistoricalDataIngestionResult(
                status=HistoricalIngestionStatus.COMPLETED,
                diagnostics=("历史行情同步完成", "未进入券商，未启用交易目标"),
                bars_written=7,
                bars_updated=0,
                bars_skipped=2,
            )

    ui = FakeUI(
        selected_label=labels.page_title(OperatorPage.DATA_CENTER.value),
        clicked_labels={"同步 AO 历史行情（不连接券商，不下单）"},
    )

    render_console(
        ui,
        default_console_view_model(),
        historical_ingestion_service=FakeHistoricalIngestionService(),
    )

    rendered = _rendered(ui)
    assert "### 当前品种" in rendered
    assert "**品种名称:** AO" in rendered
    assert "RB:" not in rendered
    assert "### 步骤 1：检查配置" in rendered
    assert "步骤 2：同步历史行情" in rendered
    assert "### 步骤 3：检查覆盖" in rendered
    assert "### 步骤 4：检查质量" in rendered
    assert "### 步骤 5：进入回测" in rendered
    assert "### 同步结果" in rendered
    assert "**新增:** 7" in rendered
    assert "**更新:** 0" in rendered
    assert "**跳过:** 2" in rendered
    assert "**失败:** 0" in rendered
    assert "未进入券商，未启用交易目标" in rendered


def test_data_center_unsynced_state_only_shows_sync_as_primary_action() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.DATA_CENTER.value))

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "**按钮:** 同步 AO 历史行情（不连接券商，不下单）" in rendered
    assert ui.buttons == [
        (
            "同步 AO 历史行情（不连接券商，不下单）",
            False,
            "data_center:sync_selected",
        )
    ]
    assert "进入本地库回测（只读 AO 历史行情）" not in [item[0] for item in ui.buttons]
    assert "查看纸面模拟（只读结果）" not in [item[0] for item in ui.buttons]


class _SyncedWithoutCoverageRepository:
    def list_coverage(
        self,
        *,
        symbols: tuple[str, ...],
        timeframe: object,
        source: str,
    ) -> tuple[dict[str, object], ...]:
        return (
            {
                "symbol": "ao",
                "coverage_start": "无",
                "coverage_end": "无",
                "bar_count": 0,
                "latest_sync": "2026-06-29T10:00:00",
                "source": source,
            },
        )

    def get_quality_summary(
        self,
        *,
        symbol: str,
        timeframe: object,
        source: str,
    ) -> dict[str, object]:
        return {"coverage_ratio": "0%", "sync_status": "待检查"} if symbol == "ao" else {}


class _CoveredDataCenterRepository:
    def list_coverage(
        self,
        *,
        symbols: tuple[str, ...],
        timeframe: object,
        source: str,
    ) -> tuple[dict[str, object], ...]:
        return (
            {
                "symbol": "ao",
                "coverage_start": "2024-01-01",
                "coverage_end": "2026-06-30",
                "bar_count": 365000,
                "latest_sync": "2026-06-29T10:00:00",
                "source": source,
            },
        )

    def get_quality_summary(
        self,
        *,
        symbol: str,
        timeframe: object,
        source: str,
    ) -> dict[str, object]:
        if symbol != "ao":
            return {}
        return {
            "missing_bars": 0,
            "duplicate_bars": 0,
            "abnormal_bars": 0,
            "gap_count": 0,
            "continuity": "连续",
            "coverage_ratio": "100%",
            "sync_status": "正常",
        }


def test_data_center_without_coverage_cannot_enter_backtest() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.DATA_CENTER.value))

    render_console(
        ui,
        default_console_view_model(),
        data_center_service=DataCenterService(repository=_SyncedWithoutCoverageRepository()),
    )

    rendered = _rendered(ui)
    assert "**按钮:** 检查 AO 覆盖率（只读本地数据）" in rendered
    assert ui.buttons == [
        (
            "检查 AO 覆盖率（只读本地数据）",
            False,
            "data_center:check_coverage",
        )
    ]
    assert "进入本地库回测" not in [item[0] for item in ui.buttons]


def test_data_center_shows_backtest_only_after_coverage_and_quality_pass() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.DATA_CENTER.value))

    render_console(
        ui,
        default_console_view_model(),
        data_center_service=DataCenterService(repository=_CoveredDataCenterRepository()),
    )

    rendered = _rendered(ui)
    assert "**按钮:** 进入本地库回测（只读 AO 历史行情）" in rendered
    assert ui.buttons == [
        (
            "进入本地库回测（只读 AO 历史行情）",
            False,
            "data_center:open_backtest",
        )
    ]


def test_data_center_does_not_render_empty_entry_buttons() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.DATA_CENTER.value))

    render_console(ui, default_console_view_model())

    button_labels = {label for label, _disabled, _key in ui.buttons}
    assert "查看纸面模拟（只读结果）" not in button_labels
    assert "查看券商只读对照（不登录）" not in button_labels
    assert len(button_labels) == 1


def test_paper_page_is_blocked_until_history_workflow_is_ready() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.PAPER.value))

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "### 纸面模拟页面暂时不能进入" in rendered
    assert "**下一步:** 点击同步 AO 历史行情。" in rendered
    assert ui.buttons == []


def test_covered_history_without_backtest_blocks_later_business_pages() -> None:
    service = DataCenterService(repository=_CoveredDataCenterRepository())

    research_ui = FakeUI(selected_label=labels.page_title(OperatorPage.RESEARCH.value))
    render_console(
        research_ui,
        default_console_view_model(),
        data_center_service=service,
    )
    research_rendered = _rendered(research_ui)
    assert "### 本地库回测可以开始" in research_rendered
    assert "### 研究状态" not in research_rendered
    assert "### 盈亏摘要" not in research_rendered
    assert research_ui.buttons == []

    paper_ui = FakeUI(selected_label=labels.page_title(OperatorPage.PAPER.value))
    render_console(
        paper_ui,
        default_console_view_model(),
        data_center_service=service,
    )
    paper_rendered = _rendered(paper_ui)
    assert "### 纸面模拟页面暂时不能进入" in paper_rendered
    assert "**下一步:** 请先完成本地库回测。" in paper_rendered
    assert "### 模拟委托" not in paper_rendered
    assert paper_ui.buttons == []

    broker_ui = FakeUI(selected_label=labels.page_title(OperatorPage.BROKER.value))
    render_console(
        broker_ui,
        default_console_view_model(),
        data_center_service=service,
    )
    broker_rendered = _rendered(broker_ui)
    assert "### 券商只读页面暂时不能进入" in broker_rendered
    assert "**下一步:** 请先完成本地库回测。" in broker_rendered
    assert "### 券商账户" not in broker_rendered
    assert broker_ui.buttons == []


def test_backtest_completed_allows_paper_action_without_fake_result() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.PAPER.value))
    ui.session_state["operator_console_backtest_completed"] = True

    render_console(
        ui,
        default_console_view_model(),
        data_center_service=DataCenterService(repository=_CoveredDataCenterRepository()),
    )

    rendered = _rendered(ui)
    assert "### 纸面模拟尚未完成" in rendered
    assert "### 模拟委托" not in rendered
    assert ui.buttons == [
        (
            "查看最近一次纸面模拟结果（只预演，不写账本）",
            False,
            "action:Run Paper Dry-run",
        )
    ]


def test_paper_page_has_one_action_after_backtest_is_completed() -> None:
    def provider() -> DryRunActionResult:
        return DryRunActionResult(
            session_status="DRY_RUN_COMPLETED",
            job_status="DRY_RUN",
            run_status="DRY_RUN_COMPLETED",
            db_delta=0,
            target="MOCK only",
        )

    ui = FakeUI(
        selected_label=labels.page_title(OperatorPage.PAPER.value),
        clicked_labels={"查看最近一次纸面模拟结果（只预演，不写账本）"},
    )
    ui.session_state["operator_console_backtest_completed"] = True

    render_console(
        ui,
        default_console_view_model(),
        paper_dry_run=provider,
        data_center_service=DataCenterService(repository=_CoveredDataCenterRepository()),
    )

    rendered = _rendered(ui)
    assert "会话状态: 预演完成" in rendered
    assert "数据库写入变化: 0" in rendered
    assert "目标类型: 仅本地模拟，不连接真实交易所" in rendered
    assert ui.session_state["operator_console_paper_completed"] is True
    assert ui.buttons == [
        (
            "查看最近一次纸面模拟结果（只预演，不写账本）",
            False,
            "action:Run Paper Dry-run",
        )
    ]


def test_paper_completed_allows_broker_read_only_page() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.BROKER.value))
    ui.session_state["operator_console_backtest_completed"] = True
    ui.session_state["operator_console_paper_completed"] = True

    render_console(
        ui,
        default_console_view_model(),
        data_center_service=DataCenterService(repository=_CoveredDataCenterRepository()),
    )

    rendered = _rendered(ui)
    assert "### 券商状态" in rendered
    assert "### 券商账户" in rendered
    assert "暂时不能进入" not in rendered
    assert ui.buttons == []


def test_broker_and_diagnostics_hide_developer_information_by_default() -> None:
    broker_ui = FakeUI(selected_label=labels.page_title(OperatorPage.BROKER.value))
    render_console(broker_ui, default_console_view_model())
    broker_rendered = _rendered(broker_ui)
    assert "### 高级诊断" not in broker_rendered
    assert "### 券商只读页面暂时不能进入" in broker_rendered
    assert "点击同步 AO 历史行情" in broker_rendered

    diagnostic_ui = FakeUI(selected_label=labels.page_title(OperatorPage.DIAGNOSTICS.value))
    render_console(diagnostic_ui, default_console_view_model())
    diagnostic_rendered = _rendered(diagnostic_ui)
    assert "### 普通用户安全检查" in diagnostic_rendered
    assert "高级诊断默认隐藏" in diagnostic_rendered
    assert "git commit" not in diagnostic_rendered
    assert "Repository" not in diagnostic_rendered


def test_developer_mode_reveals_advanced_diagnostics() -> None:
    ui = FakeUI(
        selected_label=labels.page_title(OperatorPage.DIAGNOSTICS.value),
        display_mode="开发者模式",
    )

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "### 高级诊断" not in rendered
    assert "### 本地检查" in rendered
    assert "git commit/tag" in rendered


def test_market_data_buttons_remain_fail_closed() -> None:
    ui = FakeUI(
        selected_label=labels.page_title(OperatorPage.MARKET_DATA.value),
        clicked_labels={"刷新一次行情状态"},
    )

    render_console(ui, default_console_view_model(), market_data_runtime=MarketDataRuntime())

    rendered = _rendered(ui)
    assert "### 行情数据当前任务" in rendered
    assert "当前主操作" in rendered
    assert ui.buttons == []
    assert "operator_console_result_history" not in ui.session_state


def test_market_data_normal_mode_has_no_extra_buttons_after_coverage_pass() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.MARKET_DATA.value))

    render_console(
        ui,
        default_console_view_model(),
        data_center_service=DataCenterService(repository=_CoveredDataCenterRepository()),
        market_data_runtime=MarketDataRuntime(),
    )

    rendered = _rendered(ui)
    assert "### 行情数据当前任务" in rendered
    assert "检查行情运行状态" not in [label for label, _disabled, _key in ui.buttons]
    assert "停止本地行情查看" not in [label for label, _disabled, _key in ui.buttons]
    assert "刷新一次行情状态" not in [label for label, _disabled, _key in ui.buttons]
    assert len(ui.buttons) <= 1


def test_beginner_surfaces_do_not_render_dangerous_english_buttons() -> None:
    forbidden_words = ("Login", "Submit", "Cancel", "Live", "Run", "Start", "Execute", "Apply")
    for page in (
        OperatorPage.DASHBOARD,
        OperatorPage.DATA_CENTER,
        OperatorPage.MARKET_DATA,
        OperatorPage.DIAGNOSTICS,
    ):
        ui = FakeUI(selected_label=labels.page_title(page.value))
        render_console(ui, default_console_view_model())
        button_text = "\n".join(label for label, _disabled, _key in ui.buttons)
        for word in forbidden_words:
            assert word not in button_text


def test_beginner_surfaces_do_not_leak_internal_status_words() -> None:
    forbidden_words = ("Gap", "READY", "BLOCKED", "DIFFERENCE", "True")
    for page in (
        OperatorPage.DASHBOARD,
        OperatorPage.CONFIG_CENTER,
        OperatorPage.DATA_CENTER,
        OperatorPage.RESEARCH,
        OperatorPage.PAPER,
        OperatorPage.BROKER,
        OperatorPage.MARKET_DATA,
    ):
        ui = FakeUI(selected_label=labels.page_title(page.value))
        render_console(ui, default_console_view_model())
        rendered = _rendered(ui)
        for word in forbidden_words:
            assert word not in rendered


def test_main_lazy_import_renders_streamlit_adapter(monkeypatch) -> None:
    class FakeSidebar:
        def __init__(self, owner: FakeStreamlit) -> None:
            self._owner = owner

        def selectbox(
            self,
            label: str,
            options: tuple[str, ...],
            *,
            index: int = 0,
            key: str | None = None,
        ) -> str:
            self._owner.ui.selectboxes.append((label, options, index, key))
            return options[index]

    class FakeStreamlit:
        def __init__(self) -> None:
            self.ui = FakeUI()
            self.sidebar = FakeSidebar(self)
            self.session_state: dict[str, object] = {}

        def set_page_config(self, **_kwargs: object) -> None:
            return None

        def title(self, body: str) -> None:
            self.ui.title(body)

        def header(self, body: str) -> None:
            self.ui.header(body)

        def subheader(self, body: str) -> None:
            self.ui.subheader(body)

        def markdown(self, body: str, **_kwargs: object) -> None:
            self.ui.markdown(body)

        def write(self, body: object) -> None:
            self.ui.write(body)

        def text_input(self, label: str, *, value: str = "", key: str | None = None) -> str:
            if key is not None:
                self.session_state.setdefault(key, value)
                return str(self.session_state[key])
            return value

        def text_area(self, label: str, *, value: str = "", key: str | None = None) -> str:
            if key is not None:
                self.session_state.setdefault(key, value)
                return str(self.session_state[key])
            return value

        def button(self, label: str, *, disabled: bool = False, key: str | None = None) -> bool:
            self.ui.button(label, disabled=disabled, key=key)
            return False

        def columns(self, count: int) -> tuple[FakeStreamlit, ...]:
            return tuple(self for _ in range(count))

        def container(self) -> FakeStreamlit:
            return self

        def divider(self) -> None:
            self.ui.divider()

    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(app, "import_module", lambda name: fake_streamlit)

    app.main()

    assert fake_streamlit.ui.titles == ["本地操作台"]
    assert fake_streamlit.ui.headers == ["总览"]
    assert fake_streamlit.ui.selectboxes[0][0] == "开发者模式"
