from __future__ import annotations

from futures_mvp.modules.operator_console.view_models import DiagnosticViewModel


def read_only_diagnostics_placeholder() -> DiagnosticViewModel:
    return DiagnosticViewModel(
        items=(
            ("pytest", "DISABLED"),
            ("ruff", "DISABLED"),
            ("mypy", "DISABLED"),
            ("alembic current", "DISABLED"),
            ("git commit/tag", "DISABLED"),
            ("worktree clean", "DISABLED"),
            ("DB health", "DISABLED"),
            ("Redis health", "DISABLED"),
            ("last error", "无"),
        )
    )
