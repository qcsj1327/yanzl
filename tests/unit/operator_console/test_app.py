from __future__ import annotations

from dataclasses import dataclass, field

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
    assert "MOCK only" in rendered
    assert "research only" in rendered
    assert "no live trading" in rendered
    assert "研究平台: 正常" in rendered
    assert "行情源: 正常" in rendered
    assert "当前来源: static_fixture" in rendered
    assert "最近预演: 尚未运行" in rendered


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
    assert "只读行情 Adapter 尚未配置，已阻断" in rendered
    assert "当前配置还不能生成 typed dry-run command preview。" in rendered
    assert "配置可用于预演。" not in rendered


def test_diagnostics_render_safety_boundary() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.DIAGNOSTICS.value))

    render_console(ui, default_console_view_model())

    rendered = _rendered(ui)
    assert "### 安全检查" in rendered
    assert "**目标类型:** MOCK only" in rendered
    assert "**写库:** disabled" in rendered
    assert "**真实交易:** disabled" in rendered
    assert "**Broker/CTP/SimNow:** disabled" in rendered


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
