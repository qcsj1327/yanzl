from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from futures_mvp.modules.market_data.data_center import DataCenterService
from futures_mvp.modules.market_data.ingestion import (
    HistoricalDataIngestionResult,
    HistoricalIngestionStatus,
)
from futures_mvp.modules.market_data.runtime import (
    MarketDataRuntime,
    MarketDataRuntimeConfig,
    MarketDataRuntimeSnapshot,
    MarketDataRuntimeStatus,
)
from futures_mvp.modules.operator_console import app, labels
from futures_mvp.modules.operator_console.actions import DryRunActionResult
from futures_mvp.modules.operator_console.app import render_console
from futures_mvp.modules.operator_console.config_assembly import (
    READ_ONLY_ADAPTER_DATA_SOURCE,
    ConsoleDryRunConfig,
)
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
        if key == "operator_console_page":
            return self.selected_label or options[index]
        if key == "operator_console_market_data_source":
            return str(
                self.session_state.get(
                    "operator_console_selected_market_data_source",
                    options[index],
                )
            )
        if key is not None and key in self.session_state:
            return str(self.session_state[key])
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
    return "\n".join(str(item) for item in [*ui.writes, *ui.markdowns])


def test_render_console_renders_v1_page_titles() -> None:
    ui = FakeUI()

    render_console(ui, default_console_view_model())

    expected_titles = tuple(labels.page_title(page.value) for page in OperatorPage)
    assert ui.selectboxes[0] == ("页面", expected_titles, 0, "operator_console_page")
    assert ui.headers == ["总览"]
    assert ui.titles == ["本地操作台"]


def test_dashboard_renders_status_and_safety_banner() -> None:
    ui = FakeUI()

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "### 新手上手流程" in rendered
    assert "第一步：选择品种" in rendered
    assert "第二步：检查合约解析" in rendered
    assert "第三步：检查 AkShare 映射" in rendered
    assert "第四步：同步历史行情" in rendered
    assert "第五步：检查数据覆盖" in rendered
    assert "第六步：运行本地库回测" in rendered
    assert "第七步：查看纸面模拟 / Broker 只读影子对照" in rendered
    assert "状态：已阻断；原因：本地历史库暂无确认覆盖" in rendered
    assert "研究平台: 正常" in rendered
    assert "行情源: 正常" in rendered
    assert "当前来源: static_fixture" in rendered
    assert "### 我下一步该做什么" in rendered
    assert "如果不知道先做什么：打开数据中心，选择 AO，然后点击检查配置。" in rendered
    assert "什么时候能回测：本地历史库已有数据，覆盖和质量检查通过后。" in rendered


def test_config_center_renders_unified_local_configuration() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.CONFIG_CENTER.value))

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "### 基本配置" in rendered
    assert "**我是谁:** 账户 ID：demo" in rendered
    assert "**我要跑哪天:** 交易日：2026-06-28" in rendered
    assert "**我要看哪些品种:** AO、RB、AG、CU" in rendered
    assert "**我要用什么数据:** 默认静态样例；真实数据需在数据中心同步" in rendered
    assert "**我要跑什么模式:** 本地模拟 / 只读 / 禁止实盘" in rendered
    assert "### 研究配置" in rendered
    assert "**用什么策略:** BuyAndHold" in rendered
    assert "**用多少数量:** 固定数量 1" in rendered
    assert "**手续费多少:** 0.0001" in rendered
    assert "**滑点多少:** 1 Tick" in rendered
    assert "**当前是否可回测:** 请先确认数据中心已有本地历史数据" in rendered
    assert "### 纸面配置" in rendered
    assert "**纸面模拟:** 只查看结果，不自动执行" in rendered
    assert "**本地流程:** 等待用户进入纸面模拟页面查看" in rendered
    assert "**暂停:** 未启动" in rendered
    assert "**停止:** 未启动" in rendered


def test_config_center_renders_safety_broker_market_data_preview_and_checks() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.CONFIG_CENTER.value))

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "### 券商配置" in rendered
    assert "**券商模式:** 只读" in rendered
    assert "**只读:** 只读" in rendered
    assert "**影子对照:** 启用" in rendered
    assert "**禁止登录:** 是" in rendered
    assert "**禁止下单:** 是" in rendered
    assert "**禁止撤单:** 是" in rendered
    assert "Login" not in rendered
    assert "Submit" not in rendered
    assert "Cancel" not in rendered
    assert "### 行情配置" in rendered
    assert "**当前是静态样例还是真实数据:** 默认静态样例" in rendered
    assert "**真实行情是否已配置:** 未配置" in rendered
    assert "**是否会联网:** 不会自动联网" in rendered
    assert "**是否已有本地历史数据:** 请进入数据中心检查" in rendered
    assert "**ao:AkShare 符号:** AO0" in rendered
    assert "**rb:AkShare 符号:** RB0" in rendered
    assert "**ag:AkShare 符号:** AG0" in rendered
    assert "**cu:AkShare 符号:** CU0" in rendered
    assert "### 安全锁" in rendered
    assert "**实盘交易:** 关闭" in rendered
    assert "**纸面模拟:** 只查看，不自动执行" in rendered
    assert "**Broker:** 只读" in rendered
    assert "**目标类型:** 未启用" in rendered
    assert "**数据库:** 只写历史K线，不写交易事实" in rendered
    assert "### 本次运行配置" in rendered
    assert "**当前建议:** 先进入数据中心选择品种" in rendered
    assert "**运行模式:** 仅本地模拟" in rendered
    assert "配置检查" in ui.subheaders
    assert "✓ 数据源：通过" in rendered
    assert "✓ 策略：通过" in rendered
    assert "✓ 合约解析：通过" in rendered
    assert "✓ 券商：只读" in rendered
    assert "✓ 运行时：未启动" in rendered
    assert "✓ 诊断：通过" in rendered


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
        if symbol == "ao":
            return {
                "missing_bars": 0,
                "duplicate_bars": 0,
                "abnormal_bars": 0,
                "gap_count": 0,
                "continuity": "连续",
                "coverage_ratio": "100%",
                "sync_status": "正常",
            }
        return {}


def test_data_center_renders_single_symbol_workflow_and_unsynced_hint() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.DATA_CENTER.value))

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert ui.headers == ["数据中心"]
    assert "### 数据源" in rendered
    assert "**AkShare 是否可用:** 否" in rendered
    assert "**版本:** 运行时检测" in rendered
    assert "### 当前品种" in rendered
    assert "**品种名称:** AO" in rendered
    assert "**品种映射:** AO0" in rendered
    assert "**合约解析:** 可用" in rendered
    assert "**主力合约:** ao9999" in rendered
    assert "**交易合约:** ao2609" in rendered
    assert "**交易所:** SHFE" in rendered
    assert "**RB:**" not in rendered
    assert "**AG:**" not in rendered
    assert "**CU:**" not in rendered
    assert "### 步骤 1：检查配置" in rendered
    assert "### 步骤 2：同步历史行情" in rendered
    assert "### 步骤 3：检查覆盖" in rendered
    assert "### 步骤 4：检查质量" in rendered
    assert "### 步骤 5：进入回测" in rendered
    assert "本地历史库暂无 AO 的 1m 数据" in rendered
    assert "请先点击“同步该品种历史行情”" in rendered
    assert "**当前是否可用于回测:** 请先同步历史行情" in rendered
    assert "### 数据中心诊断" in rendered
    assert "**合约解析:** 可用" in rendered
    assert "**本地历史库:** 未配置" in rendered
    assert "**历史K线:** 已建模" in rendered
    assert "**AkShare:** 显式点击才读取" in rendered
    assert ("同步该品种历史行情", False, "data_center:sync_selected") in ui.buttons
    assert ("检查覆盖", False, "data_center:check_coverage") in ui.buttons
    assert ("检查数据质量", False, "data_center:check_quality") in ui.buttons
    assert ("查看本地库回测入口", True, "data_center:open_backtest") in ui.buttons
    assert ("查看纸面模拟结果", False, "data_center:open_paper") in ui.buttons
    assert "登录" not in rendered
    assert "下单" not in rendered
    assert "撤单" not in rendered
    assert "成交" not in rendered


def test_data_center_covered_symbol_shows_backtest_ready() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.DATA_CENTER.value))

    render_console(
        ui,
        default_console_view_model(),
        data_center_service=DataCenterService(repository=_CoveredDataCenterRepository()),
    )

    rendered = _rendered(ui)
    assert "**覆盖开始:** 2024-01-01" in rendered
    assert "**覆盖结束:** 2026-06-30" in rendered
    assert "**Bar 数量:** 365000" in rendered
    assert "**覆盖率:** 100%" in rendered
    assert "**当前是否可用于回测:** 可以回测" in rendered
    assert ("查看本地库回测入口", False, "data_center:open_backtest") in ui.buttons


def test_data_center_sync_button_renders_result_without_trading_command() -> None:
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
                diagnostics=("历史行情同步完成", "未进入 Broker"),
                bars_written=7,
                bars_updated=0,
                bars_skipped=2,
            )

    ui = FakeUI(
        selected_label=labels.page_title(OperatorPage.DATA_CENTER.value),
        clicked_labels={"同步该品种历史行情"},
    )

    render_console(
        ui,
        default_console_view_model(),
        historical_ingestion_service=FakeHistoricalIngestionService(),
    )

    rendered = _rendered(ui)
    assert "### 同步结果" in rendered
    assert "**新增:** 7" in rendered
    assert "**更新:** 0" in rendered
    assert "**跳过:** 2" in rendered
    assert "**失败:** 0" in rendered
    assert "**诊断:** 历史行情同步完成" in rendered
    assert "未进入 Broker，未启用 ExecutionTarget" in rendered
    assert "operator_console_result_history" not in ui.session_state


def test_data_center_quality_button_renders_chinese_quality_result() -> None:
    ui = FakeUI(
        selected_label=labels.page_title(OperatorPage.DATA_CENTER.value),
        clicked_labels={"检查数据质量"},
    )

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "### 数据质量检查结果" in rendered
    assert "**重复 Bar:** 0" in rendered
    assert "**缺失 Bar:** 0" in rendered
    assert "**异常 Bar:** 0" in rendered
    assert "**Gap:** 0" in rendered
    assert "**连续性:** 待检查" in rendered


def test_main_pages_do_not_render_dangerous_english_action_words() -> None:
    forbidden = ("Login", "Submit", "Cancel", "Live", "Run", "Start", "Execute", "Apply")
    for page in (
        OperatorPage.DASHBOARD,
        OperatorPage.CONFIG_CENTER,
        OperatorPage.DATA_CENTER,
        OperatorPage.MARKET_DATA,
        OperatorPage.DIAGNOSTICS,
    ):
        ui = FakeUI(selected_label=labels.page_title(page.value))
        render_console(ui, default_console_view_model())
        rendered = _rendered(ui)
        button_text = "\n".join(label for label, _disabled, _key in ui.buttons)
        for word in forbidden:
            assert word not in rendered
            assert word not in button_text


def test_research_view_renders_metrics() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.RESEARCH.value))

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "Backtest 状态: 完成" in rendered
    assert "策略: sample_breakout_research" in rendered
    assert "**总收益:** 0.0012" in rendered
    assert "**最高权益:** 100120" in rendered
    assert "**最低权益:** 100000" in rendered


def test_portfolio_view_renders_contributions_and_weights() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.PORTFOLIO.value))

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "### 品种贡献" in rendered
    assert "**ao:** 市值 500 / PnL 20" in rendered
    assert "### 持仓权重" in rendered
    assert "现金权重" in rendered
    assert "**cash:** 96.30%" in rendered


def test_paper_view_renders_consistency_and_dry_run_controls() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.PAPER.value))

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "纸面模拟运行状态: 正常" in rendered
    assert "### 一致性报告" in rendered
    assert "**全部一致:** True" in rendered
    assert ("查看纸面模拟结果", False, "action:Run Paper Dry-run") in ui.buttons
    assert ("纸面模拟写入已禁用", True, "action:Run Paper Apply") in ui.buttons


def test_broker_view_renders_read_only_snapshot_and_difference_report() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.BROKER.value))

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "### 券商状态" in rendered
    assert "### 券商账户" in rendered
    assert "### 券商持仓" in rendered
    assert "### 券商订单" in rendered
    assert "### 券商成交" in rendered
    assert "### 影子对照" in rendered
    assert "### 差异报告" in rendered
    assert "不登录、不重试、不报单、不撤单、不写数据库" in rendered


def test_paper_dry_run_click_renders_zero_db_result() -> None:
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
        clicked_labels={"查看纸面模拟结果"},
    )

    render_console(ui, default_console_view_model(), paper_dry_run=provider)

    rendered = _rendered(ui)
    assert "会话状态: 预演完成" in rendered
    assert "数据库写入变化: 0" in rendered
    assert "目标类型: 仅本地模拟，不连接真实交易所" in rendered


def test_market_data_placeholder_blocks_without_command() -> None:
    ui = FakeUI(
        selected_label=labels.page_title(OperatorPage.MARKET_DATA.value),
        session_state={
            "operator_console_selected_market_data_source": READ_ONLY_ADAPTER_DATA_SOURCE,
            "operator_console_dry_run_config": ConsoleDryRunConfig(
                account_id="account-1",
                trading_day="2026-06-12",
                symbol="ao",
                quantity="1",
                price="500",
                max_order_size="1",
                max_position_size="1",
                max_daily_loss="1000",
                allowed_instruments=("ao2609",),
            ),
        },
    )

    render_console(ui, default_console_view_model())

    config = ui.session_state["operator_console_dry_run_config"]
    rendered = _rendered(ui)
    assert isinstance(config, ConsoleDryRunConfig)
    assert config.market_data_source == READ_ONLY_ADAPTER_DATA_SOURCE
    assert "只读行情适配器未配置，不会访问网络" in rendered
    assert "当前配置还不能生成命令预览。" in rendered
    assert "配置可用于预演。" not in rendered


def test_market_data_page_displays_runtime_status() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.MARKET_DATA.value))
    runtime = MarketDataRuntime()

    render_console(ui, default_console_view_model(), market_data_runtime=runtime)

    rendered = _rendered(ui)
    assert "### 运行状态" in rendered
    assert "未配置" in rendered
    assert "### 是否已启动" in rendered
    assert "否" in rendered
    assert "### 当前数据源" in rendered
    assert "real_market_data" in rendered
    assert ("检查行情运行状态", False, "market_data_runtime:start") in ui.buttons
    assert ("停止本地行情查看", False, "market_data_runtime:stop") in ui.buttons
    assert ("刷新一次行情状态", False, "market_data_runtime:poll_once") in ui.buttons
    assert "### 历史行情同步" in rendered
    assert "### 本地库覆盖情况" in rendered
    assert ("同步该品种历史行情", False, "historical_data_sync:run") in ui.buttons


def test_market_data_sync_button_renders_local_coverage_without_command() -> None:
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
            assert trading_day == date(2026, 6, 12)
            assert end_trading_day == date(2026, 6, 12)
            assert timeframe == "1m"
            return HistoricalDataIngestionResult(
                status=HistoricalIngestionStatus.COMPLETED,
                diagnostics=("历史行情同步完成", "未进入交易链路，未启用 ExecutionTarget"),
                bars_written=3,
                bars_updated=0,
                bars_skipped=0,
                bar_count=3,
                first_bar_ts=datetime(2026, 6, 12, 9, 1),
                latest_bar_ts=datetime(2026, 6, 12, 9, 3),
                latest_ingested_at=datetime(2026, 6, 12, 10, 0),
            )

    ui = FakeUI(
        selected_label=labels.page_title(OperatorPage.MARKET_DATA.value),
        clicked_labels={"同步该品种历史行情"},
    )

    render_console(
        ui,
        default_console_view_model(),
        historical_ingestion_service=FakeHistoricalIngestionService(),
    )

    rendered = _rendered(ui)
    assert "### 历史行情同步结果" in rendered
    assert "**写入条数:** 3" in rendered
    assert "**更新条数:** 0" in rendered
    assert "**跳过条数:** 0" in rendered
    assert "**bar 数量:** 3" in rendered
    assert "**覆盖开始:** 2026-06-12 09:01:00" in rendered
    assert "**覆盖结束:** 2026-06-12 09:03:00" in rendered
    assert "**数据源:** real_market_data" in rendered
    assert "未进入交易链路，未启用 ExecutionTarget" in rendered
    assert "配置可用于预演。" not in rendered
    assert "operator_console_result_history" not in ui.session_state


def test_diagnostics_page_renders_broker_diagnostics() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.DIAGNOSTICS.value))

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "### 券商诊断" in rendered
    assert "**BrokerReadOnlyAdapter:** READY" in rendered
    assert "**submit/cancel:** 禁用" in rendered


def test_market_data_poll_button_does_not_generate_command() -> None:
    ui = FakeUI(
        selected_label=labels.page_title(OperatorPage.MARKET_DATA.value),
        clicked_labels={"刷新一次行情状态"},
    )
    runtime = MarketDataRuntime(
        MarketDataRuntimeConfig(enabled=True, trading_day=date(2026, 6, 12)),
        client=_FakeAkShareClient(),
    )

    render_console(ui, default_console_view_model(), market_data_runtime=runtime)

    snapshot = ui.session_state["operator_console_market_data_runtime_snapshot"]
    rendered = _rendered(ui)
    assert isinstance(snapshot, MarketDataRuntimeSnapshot)
    assert snapshot.status is MarketDataRuntimeStatus.BLOCKED
    assert snapshot.network_call_occurred is False
    assert snapshot.latest_error == "行情运行时未启动，需先启动后刷新"
    assert "配置可用于预演。" not in rendered
    assert "当前配置还不能生成命令预览。" in rendered
    assert "operator_console_result_history" not in ui.session_state


def test_diagnostics_render_safety_boundary() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.DIAGNOSTICS.value))

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "### 安全检查" in rendered
    assert "**目标类型:** MOCK only" in rendered
    assert "**写库:** 禁用" in rendered
    assert "**真实交易:** 禁用" in rendered
    assert "**Broker/CTP/SimNow:** 禁用" in rendered


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
    assert fake_streamlit.ui.selectboxes[0][0] == "页面"


class _FakeAkShareClient:
    def futures_display_main_sina(self) -> list[dict[str, object]]:
        return [{"symbol": "AO0", "exchange": "SHFE"}]

    def match_main_contract(self, symbol: str) -> str:
        return "AO0"

    def futures_zh_spot(
        self,
        symbol: str,
        market: str = "CF",
        adjust: str = "0",
    ) -> list[dict[str, object]]:
        return [
            {
                "symbol": "ao2609",
                "current_price": "3205",
                "volume": "10",
                "hold": "20",
                "bid_price": "3204",
                "ask_price": "3206",
            }
        ]

    def futures_zh_minute_sina(self, symbol: str, period: str) -> list[dict[str, object]]:
        return [
            {
                "datetime": "2026-06-12 09:01:00",
                "open": "3200",
                "high": "3210",
                "low": "3190",
                "close": "3205",
                "volume": "10",
                "hold": "20",
            }
        ]

    def futures_zh_daily_sina(self, symbol: str) -> list[dict[str, object]]:
        return self.futures_zh_minute_sina(symbol, "1")
