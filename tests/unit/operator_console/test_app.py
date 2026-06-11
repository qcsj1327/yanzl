from __future__ import annotations

from dataclasses import dataclass, field, replace

from futures_mvp.modules.operator_console import app, labels
from futures_mvp.modules.operator_console.actions import DryRunActionResult
from futures_mvp.modules.operator_console.app import render_console
from futures_mvp.modules.operator_console.view_models import (
    OperatorPage,
    ResultHistoryViewModel,
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
        return self.selected_label or options[index]

    def columns(self, count: int) -> tuple[FakeUI, ...]:
        return tuple(self for _ in range(count))

    def container(self) -> FakeUI:
        return self

    def divider(self) -> None:
        self.dividers += 1


def test_render_console_renders_all_page_titles_from_labels() -> None:
    ui = FakeUI()
    model = default_console_view_model()

    render_console(ui, model)

    expected_titles = tuple(labels.page_title(page.value) for page in OperatorPage)
    assert ui.selectboxes == [("页面", expected_titles, 0, "operator_console_page")]
    assert ui.headers == ["总览"]
    assert ui.titles == ["本地操作台"]


def test_render_console_can_select_each_page_by_value_label() -> None:
    for page in OperatorPage:
        ui = FakeUI(selected_label=labels.page_title(page.value))

        render_console(ui, default_console_view_model())

        assert ui.headers == [labels.page_title(page.value)]


def test_main_lazy_import_renders_streamlit_adapter(monkeypatch) -> None:
    class FakeSidebar:
        def __init__(self, owner) -> None:
            self._owner = owner

        def selectbox(
            self,
            label: str,
            options: tuple[str, ...],
            *,
            index: int = 0,
            key: str | None = None,
        ) -> str:
            self._owner.selectboxes.append((label, options, index, key))
            return options[index]

    class FakeStreamlit:
        def __init__(self) -> None:
            self.ui = FakeUI()
            self.sidebar = FakeSidebar(self)
            self.selectboxes: list[tuple[str, tuple[str, ...], int, str | None]] = []

        def title(self, body: str) -> None:
            self.ui.title(body)

        def header(self, body: str) -> None:
            self.ui.header(body)

        def subheader(self, body: str) -> None:
            self.ui.subheader(body)

        def markdown(self, body: str) -> None:
            self.ui.markdown(body)

        def write(self, body: object) -> None:
            self.ui.write(body)

        def button(self, label: str, *, disabled: bool = False, key: str | None = None) -> bool:
            self.ui.button(label, disabled=disabled, key=key)
            return False

        def columns(self, count: int):
            return tuple(self for _ in range(count))

        def container(self):
            return self

        def divider(self) -> None:
            self.ui.divider()

    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(app, "import_module", lambda name: fake_streamlit)

    app.main()

    assert fake_streamlit.ui.titles == ["本地操作台"]
    assert fake_streamlit.ui.headers == ["总览"]
    assert fake_streamlit.selectboxes[0][0] == "页面"
    assert "✅ 运行正常" in "\n".join(str(item) for item in fake_streamlit.ui.markdowns)


def test_render_console_uses_chinese_field_and_diagnostic_labels() -> None:
    ui = FakeUI()

    render_console(ui, default_console_view_model())

    rendered = "\n".join(str(item) for item in [*ui.writes, *ui.markdowns])
    assert "✅ 运行正常" in rendered
    assert "当前模式：PAPER" in rendered
    assert "当前目标：仅 MOCK" in rendered

    diagnostics_ui = FakeUI(selected_label=labels.page_title(OperatorPage.DIAGNOSTICS.value))
    render_console(diagnostics_ui, default_console_view_model())
    diagnostics_rendered = "\n".join(
        str(item) for item in [*diagnostics_ui.writes, *diagnostics_ui.markdowns]
    )

    assert "pytest 状态: 未知/未运行" in diagnostics_rendered
    assert "Alembic 当前版本: 未知/未检查" in diagnostics_rendered
    assert "最近错误: 无" in diagnostics_rendered

    paper_ui = FakeUI(selected_label=labels.page_title(OperatorPage.PAPER_SESSION.value))
    render_console(paper_ui, default_console_view_model())
    paper_rendered = "\n".join(str(item) for item in [*paper_ui.writes, *paper_ui.markdowns])

    assert "目标类型: 仅本地模拟，不连接真实交易所" in paper_rendered

    assert "Operator Console" not in ui.titles
    assert "Runtime:" not in rendered
    assert "rollout mode:" not in rendered
    assert "mode:" not in paper_rendered
    assert "target:" not in paper_rendered


def test_dashboard_renders_four_core_cards() -> None:
    ui = FakeUI()

    render_console(ui, default_console_view_model())

    rendered = "\n".join(str(item) for item in [*ui.writes, *ui.markdowns])
    assert "### 系统状态" in rendered
    assert "✅ 运行正常" in rendered
    assert "当前模式：PAPER" in rendered
    assert "当前目标：仅 MOCK" in rendered
    assert "数据库迁移：正常" in rendered
    assert "### 安全锁定" in rendered
    assert "🔒 LIVE 禁用" in rendered
    assert "🔒 Broker 禁用" in rendered
    assert "🔒 CTP 禁用" in rendered
    assert "🔒 SimNow 禁用" in rendered
    assert "🔒 真实资金禁用" in rendered
    assert "### 下一步操作" in rendered
    assert "1. 先运行 Paper 预演" in rendered
    assert "2. 再查看运行结果" in rendered
    assert "3. 确认安全后再考虑 SIM 预演" in rendered
    assert "### 最近结果" in rendered
    assert "当前尚未运行" in rendered
    assert "数据库写入变化：0" in rendered
    assert "最近状态：无" in rendered


def test_paper_page_renders_flow_sections() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.PAPER_SESSION.value))

    render_console(ui, default_console_view_model())

    rendered = "\n".join(str(item) for item in [*ui.writes, *ui.markdowns, *ui.subheaders])
    assert "🧪 这是什么" in rendered
    assert "Paper 用于验证交易账本链路" in rendered
    assert "不模拟真实交易所" in rendered
    assert "不涉及真实资金" in rendered
    assert "当前仅 MOCK" in rendered
    assert "🧭 操作流程" in rendered
    assert "1. 运行 Paper 预演" in rendered
    assert "2. 查看预演结果" in rendered
    assert "3. 确认后未来才允许 Paper 写入" in rendered
    assert "📄 当前按钮" in rendered
    assert "预演不会写数据库" in rendered
    assert "写入会改本地账本，所以当前禁用" in rendered


def test_sim_page_renders_difference_section() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.SIM_SESSION.value))

    render_console(ui, default_console_view_model())

    rendered = "\n".join(str(item) for item in [*ui.writes, *ui.markdowns, *ui.subheaders])
    assert "SIM 是本地仿真" in rendered
    assert "不是 SimNow" in rendered
    assert "不是 CTP" in rendered
    assert "不是实盘" in rendered
    assert "当前仍然 MOCK only" in rendered
    assert "🧭 与 Paper 的区别" in rendered
    assert "Paper：验证账本链路" in rendered
    assert "SIM：验证仿真交易行为" in rendered
    assert "SIM 未来才可能支持部分成交、滑点、延迟" in rendered


def test_safety_page_renders_control_explanations_and_locked_card() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.SAFETY_CONTROLS.value))

    render_console(ui, default_console_view_model())

    rendered = "\n".join(str(item) for item in [*ui.writes, *ui.markdowns, *ui.subheaders])
    assert "紧急停止" in rendered
    assert "说明：开启后阻止 Paper/SIM 运行" in rendered
    assert "调度暂停" in rendered
    assert "说明：暂停自动任务" in rendered
    assert "回放暂停" in rendered
    assert "说明：暂停历史回放或重放流程" in rendered
    assert "### 锁定项目" in rendered
    assert "LIVE 启用：禁止" in rendered
    assert "手动改账本：禁止" in rendered


def test_results_page_renders_not_run_language_without_disabled_list() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.RESULTS_HISTORY.value))

    render_console(ui, default_console_view_model())

    rendered = "\n".join(str(item) for item in [*ui.writes, *ui.markdowns])
    assert "当前状态：尚未运行" in rendered
    assert "最近运行：无" in rendered
    assert "数据库写入变化：0" in rendered
    assert "执行报告：尚未生成" in rendered
    assert "订单状态：尚未更新" in rendered
    assert "成交记录：尚未生成" in rendered
    assert "仓位更新：尚未生成" in rendered
    assert "保证金 / PnL：尚未计算" in rendered
    assert "结算快照：尚未生成" in rendered
    assert "已禁用" not in rendered


def test_configuration_page_renders_dry_run_required_config() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.CONFIGURATION.value))

    render_console(ui, default_console_view_model())

    rendered = "\n".join(str(item) for item in [*ui.writes, *ui.subheaders])
    assert "预演所需配置" in rendered
    assert "账户 ID: 未配置" in rendered
    assert "交易日: 未配置" in rendered
    assert "合约白名单: 未配置" in rendered
    assert "最大委托数量: 未配置" in rendered
    assert "最大持仓数量: 未配置" in rendered
    assert "最大日亏损: 未配置" in rendered
    assert "命令来源 / typed command provider: 未配置" in rendered
    assert "job_factory: 未配置" in rendered


def test_live_locked_page_renders_strong_warning() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.LIVE_LOCKED_PAGE.value))

    render_console(ui, default_console_view_model())

    rendered = "\n".join(str(item) for item in [*ui.markdowns, *ui.subheaders])
    assert "🔒 当前不是实盘环境" in rendered
    assert "不会连接真实交易所" in rendered
    assert "不会连接 CTP" in rendered
    assert "不会连接 SimNow" in rendered
    assert "不会使用真实资金" in rendered
    assert "没有任何启用 LIVE 的按钮" in rendered


def test_apply_buttons_are_rendered_disabled() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.PAPER_SESSION.value))

    render_console(ui, default_console_view_model())

    buttons = {label: disabled for label, disabled, _key in ui.buttons}
    assert buttons["确认运行 Paper 写入"] is True

    sim_ui = FakeUI(selected_label=labels.page_title(OperatorPage.SIM_SESSION.value))
    render_console(sim_ui, default_console_view_model())
    sim_buttons = {label: disabled for label, disabled, _key in sim_ui.buttons}
    assert sim_buttons["确认运行 SIM 写入"] is True


def test_paper_dry_run_click_calls_provider_and_renders_result() -> None:
    calls = 0

    def provider() -> DryRunActionResult:
        nonlocal calls
        calls += 1
        return DryRunActionResult(
            session_status="DRY_RUN_COMPLETED",
            job_status="DRY_RUN",
            run_status="DRY_RUN_COMPLETED",
            db_delta=0,
            target="MOCK only",
        )

    ui = FakeUI(
        selected_label=labels.page_title(OperatorPage.PAPER_SESSION.value),
        clicked_labels={"运行 Paper 预演"},
    )

    render_console(ui, default_console_view_model(), paper_dry_run=provider)

    rendered = "\n".join(str(item) for item in [*ui.writes, *ui.markdowns, *ui.subheaders])
    assert calls == 1
    assert "会话状态: 预演完成" in rendered
    assert "任务状态: 预演" in rendered
    assert "运行状态: 预演完成" in rendered
    assert "数据库写入变化: 0" in rendered
    assert "目标类型: 仅本地模拟，不连接真实交易所" in rendered


def test_paper_blocked_dry_run_renders_user_guidance() -> None:
    def provider() -> DryRunActionResult:
        return DryRunActionResult(
            session_status="BLOCKED",
            job_status="BLOCKED",
            run_status="BLOCKED",
            reason="paper dry-run requires complete session config",
        )

    ui = FakeUI(
        selected_label=labels.page_title(OperatorPage.PAPER_SESSION.value),
        clicked_labels={"运行 Paper 预演"},
    )

    render_console(ui, default_console_view_model(), paper_dry_run=provider)

    rendered = "\n".join(str(item) for item in [*ui.markdowns, *ui.subheaders])
    assert "⚠️ 本次预演未执行" in rendered
    assert "系统已安全阻断本次操作，没有写入数据库，也没有连接真实交易所。" in rendered
    assert "当前缺少完整的 Paper 预演配置，因此没有执行" in rendered
    assert "1. 打开配置中心" in rendered
    assert "✅ 数据库写入变化：0" in rendered
    assert "✅ 目标类型：仅本地模拟，不连接真实交易所" in rendered
    assert "✅ 真实资金：未使用" in rendered
    assert "requires complete session config" not in rendered


def test_sim_dry_run_click_calls_provider_and_renders_result() -> None:
    calls = 0

    def provider() -> DryRunActionResult:
        nonlocal calls
        calls += 1
        return DryRunActionResult(
            session_status="DRY_RUN_COMPLETED",
            job_status="DRY_RUN",
            run_status="DRY_RUN_COMPLETED",
            db_delta=0,
            target="MOCK only",
        )

    ui = FakeUI(
        selected_label=labels.page_title(OperatorPage.SIM_SESSION.value),
        clicked_labels={"运行 SIM 预演"},
    )

    render_console(ui, default_console_view_model(), sim_dry_run=provider)

    rendered = "\n".join(str(item) for item in [*ui.writes, *ui.markdowns, *ui.subheaders])
    assert calls == 1
    assert "会话状态: 预演完成" in rendered
    assert "数据库写入变化: 0" in rendered


def test_sim_blocked_dry_run_renders_user_guidance() -> None:
    def provider() -> DryRunActionResult:
        return DryRunActionResult(
            session_status="BLOCKED",
            job_status="BLOCKED",
            run_status="BLOCKED",
            reason="sim dry-run requires complete session config",
        )

    ui = FakeUI(
        selected_label=labels.page_title(OperatorPage.SIM_SESSION.value),
        clicked_labels={"运行 SIM 预演"},
    )

    render_console(ui, default_console_view_model(), sim_dry_run=provider)

    rendered = "\n".join(str(item) for item in [*ui.markdowns, *ui.subheaders])
    assert "⚠️ 本次预演未执行" in rendered
    assert "当前缺少完整的 SIM 预演配置，因此没有执行" in rendered
    assert "2. 检查账户 ID、交易日、合约白名单、最大单笔数量、最大持仓数量、最大日亏损" in rendered


def test_apply_click_does_not_call_dry_run_provider() -> None:
    calls = 0

    def provider() -> DryRunActionResult:
        nonlocal calls
        calls += 1
        return DryRunActionResult("DRY_RUN_COMPLETED", "DRY_RUN", "DRY_RUN_COMPLETED")

    ui = FakeUI(
        selected_label=labels.page_title(OperatorPage.PAPER_SESSION.value),
        clicked_labels={"确认运行 Paper 写入"},
    )

    render_console(ui, default_console_view_model(), paper_dry_run=provider)

    assert calls == 0


def test_dry_run_unsafe_result_renders_blocked_reason() -> None:
    def provider() -> DryRunActionResult:
        return DryRunActionResult(
            session_status="DRY_RUN_COMPLETED",
            job_status="DRY_RUN",
            run_status="DRY_RUN_COMPLETED",
            db_delta=1,
            target="MOCK only",
        )

    ui = FakeUI(
        selected_label=labels.page_title(OperatorPage.PAPER_SESSION.value),
        clicked_labels={"运行 Paper 预演"},
    )

    render_console(ui, default_console_view_model(), paper_dry_run=provider)

    rendered = "\n".join(str(item) for item in [*ui.markdowns, *ui.subheaders])
    assert "⚠️ 本次预演未执行" in rendered
    assert "✅ 数据库写入变化：0" in rendered
    assert "原因: 预演出现数据库写入变化，已阻止标记为成功" in rendered


def test_results_blocked_dry_run_renders_safe_result_card() -> None:
    model = default_console_view_model()
    blocked = replace(
        model,
        results=ResultHistoryViewModel(
            items=model.results.items,
            session_status="BLOCKED",
            job_status="BLOCKED",
            run_status="BLOCKED",
            latest_run="dry-run",
            reason="non-MOCK target",
        ),
    )
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.RESULTS_HISTORY.value))

    render_console(ui, blocked)

    rendered = "\n".join(str(item) for item in [*ui.markdowns, *ui.subheaders])
    assert "⚠️ 本次预演未执行" in rendered
    assert "当前目标不是 MOCK，已阻止执行" in rendered
    assert "✅ 数据库写入变化：0" in rendered
    assert "✅ 目标类型：仅本地模拟，不连接真实交易所" in rendered
    assert "✅ 真实资金：未使用" in rendered


def test_forbidden_actions_are_text_only_without_enable_buttons() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.LIVE_LOCKED_PAGE.value))

    render_console(ui, default_console_view_model())

    forbidden_labels = set(labels.FORBIDDEN_ACTION_LABELS.values())
    rendered_buttons = {label for label, _disabled, _key in ui.buttons}

    assert forbidden_labels.issubset(set(ui.markdowns))
    assert forbidden_labels.isdisjoint(rendered_buttons)
