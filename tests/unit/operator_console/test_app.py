from dataclasses import dataclass, field

from futures_mvp.modules.operator_console import labels
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


def test_render_console_renders_all_page_titles_from_labels() -> None:
    ui = FakeUI()
    model = default_console_view_model()

    render_console(ui, model)

    expected_headers = [labels.page_title(page.value) for page in OperatorPage]
    assert ui.headers == expected_headers


def test_apply_buttons_are_rendered_disabled() -> None:
    ui = FakeUI()

    render_console(ui, default_console_view_model())

    buttons = {label: disabled for label, disabled, _key in ui.buttons}
    assert buttons["确认运行 Paper 写入"] is True
    assert buttons["确认运行 SIM 写入"] is True


def test_forbidden_actions_are_text_only_without_enable_buttons() -> None:
    ui = FakeUI()

    render_console(ui, default_console_view_model())

    forbidden_labels = set(labels.FORBIDDEN_ACTION_LABELS.values())
    rendered_buttons = {label for label, _disabled, _key in ui.buttons}

    assert forbidden_labels.issubset(set(ui.markdowns))
    assert forbidden_labels.isdisjoint(rendered_buttons)
