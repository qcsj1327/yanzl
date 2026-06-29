from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

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
    assert "### 安全边界" in rendered
    assert "仅本地模拟" in rendered
    assert "仅研究展示" in rendered
    assert "不启用实盘" in rendered
    assert "研究平台: 正常" in rendered
    assert "行情源: 正常" in rendered
    assert "当前来源: static_fixture" in rendered
    assert "最近预演: 尚未运行" in rendered


def test_config_center_renders_unified_local_configuration() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.CONFIG_CENTER.value))

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "### 基本配置" in rendered
    assert "**账户 ID:** demo" in rendered
    assert "**交易日:** 2026-06-28" in rendered
    assert "**行情数据源:** 静态样例" in rendered
    assert "**运行模式:** 本地模拟" in rendered
    assert "**品种:** AO、RB" in rendered
    assert "**时间周期:** 日线" in rendered
    assert "### 研究配置" in rendered
    assert "**策略:** BuyAndHold" in rendered
    assert "**仓位模式:** 固定数量" in rendered
    assert "**固定数量:** 1" in rendered
    assert "**固定资金:** 100000" in rendered
    assert "**手续费:** 0.0001" in rendered
    assert "**滑点:** 1 Tick" in rendered
    assert "**资金分配:** 等权分配" in rendered
    assert "### 纸面配置" in rendered
    assert "**纸面运行时:** 未启动" in rendered
    assert "**运行:** 未启动" in rendered
    assert "**暂停:** 未启动" in rendered
    assert "**停止:** 未启动" in rendered


def test_config_center_renders_safety_broker_market_data_preview_and_checks() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.CONFIG_CENTER.value))

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "### 券商配置" in rendered
    assert "**Broker:** 只读" in rendered
    assert "**只读:** 只读" in rendered
    assert "**影子对照:** 启用" in rendered
    assert "**禁用:** 禁用" in rendered
    assert "Login" not in rendered
    assert "Submit" not in rendered
    assert "Cancel" not in rendered
    assert "### 行情配置" in rendered
    assert "**静态样例:** 可用" in rendered
    assert "**只读行情数据:** 未配置" in rendered
    assert "**网络:** 不会联网" in rendered
    assert "**真实行情:** 不会读取真实行情" in rendered
    assert "**ao:AkShare 符号:** AO0" in rendered
    assert "**rb:AkShare 符号:** RB0" in rendered
    assert "**ag:AkShare 符号:** AG0" in rendered
    assert "**cu:AkShare 符号:** CU0" in rendered
    assert "### 安全锁" in rendered
    assert "**实盘交易:** 关闭" in rendered
    assert "**Paper:** 启用" in rendered
    assert "**Broker:** 只读" in rendered
    assert "**目标类型:** 未启用" in rendered
    assert "### 本次运行配置" in rendered
    assert "**策略:** BuyAndHold" in rendered
    assert "**运行模式:** MOCK" in rendered
    assert "配置检查" in ui.subheaders
    assert "✓ 数据源：通过" in rendered
    assert "✓ 策略：通过" in rendered
    assert "✓ 解析器：通过" in rendered
    assert "✓ 券商：只读" in rendered
    assert "✓ 运行时：未启动" in rendered
    assert "✓ 诊断：通过" in rendered


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
    assert "PaperResearchRuntime: 正常" in rendered
    assert "### 一致性报告" in rendered
    assert "**全部一致:** True" in rendered
    assert ("运行 Paper 预演", False, "action:Run Paper Dry-run") in ui.buttons
    assert ("确认运行 Paper 写入", True, "action:Run Paper Apply") in ui.buttons


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
        clicked_labels={"运行 Paper 预演"},
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
    assert ("启动行情运行时", False, "market_data_runtime:start") in ui.buttons
    assert ("停止行情运行时", False, "market_data_runtime:stop") in ui.buttons
    assert ("单次刷新行情", False, "market_data_runtime:poll_once") in ui.buttons
    assert "### 历史行情同步" in rendered
    assert "### 本地库覆盖情况" in rendered
    assert ("同步历史行情", False, "historical_data_sync:run") in ui.buttons


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
                diagnostics=("历史行情同步完成", "未下单，未启用 ExecutionTarget"),
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
        clicked_labels={"同步历史行情"},
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
    assert "未下单，未启用 ExecutionTarget" in rendered
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
        clicked_labels={"单次刷新行情"},
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
