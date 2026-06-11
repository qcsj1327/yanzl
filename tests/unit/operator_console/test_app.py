from dataclasses import dataclass, field

from futures_mvp.modules.operator_console import app, labels
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
    selected_label: str | None = None

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
        return False

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

    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(app, "import_module", lambda name: fake_streamlit)

    app.main()

    assert fake_streamlit.ui.titles == ["本地操作台"]
    assert fake_streamlit.ui.headers == ["总览"]
    assert fake_streamlit.selectboxes[0][0] == "页面"
    assert "运行时: 正常" in "\n".join(str(item) for item in fake_streamlit.ui.writes)


def test_render_console_uses_chinese_field_and_diagnostic_labels() -> None:
    ui = FakeUI()

    render_console(ui, default_console_view_model())

    rendered = "\n".join(str(item) for item in [*ui.writes, *ui.markdowns])
    assert "运行时: 正常" in rendered
    assert "运行模式: PAPER" in rendered
    assert "目标类型: 仅 MOCK，本地模拟" in rendered

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

    assert "模式: PAPER" in paper_rendered
    assert "目标类型: 仅 MOCK，本地模拟" in paper_rendered

    assert "Operator Console" not in ui.titles
    assert "Runtime:" not in rendered
    assert "rollout mode:" not in rendered
    assert "mode:" not in paper_rendered
    assert "target:" not in paper_rendered


def test_apply_buttons_are_rendered_disabled() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.PAPER_SESSION.value))

    render_console(ui, default_console_view_model())

    buttons = {label: disabled for label, disabled, _key in ui.buttons}
    assert buttons["确认运行 Paper 写入"] is True

    sim_ui = FakeUI(selected_label=labels.page_title(OperatorPage.SIM_SESSION.value))
    render_console(sim_ui, default_console_view_model())
    sim_buttons = {label: disabled for label, disabled, _key in sim_ui.buttons}
    assert sim_buttons["确认运行 SIM 写入"] is True


def test_forbidden_actions_are_text_only_without_enable_buttons() -> None:
    ui = FakeUI(selected_label=labels.page_title(OperatorPage.LIVE_LOCKED_PAGE.value))

    render_console(ui, default_console_view_model())

    forbidden_labels = set(labels.FORBIDDEN_ACTION_LABELS.values())
    rendered_buttons = {label for label, _disabled, _key in ui.buttons}

    assert forbidden_labels.issubset(set(ui.markdowns))
    assert forbidden_labels.isdisjoint(rendered_buttons)
