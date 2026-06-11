from __future__ import annotations

from futures_mvp.modules.operator_console.view_models import DiagnosticViewModel


def read_only_diagnostics_placeholder() -> DiagnosticViewModel:
    return DiagnosticViewModel(
        items=(
            ("pytest status", "unknown/not run"),
            ("ruff status", "unknown/not run"),
            ("mypy status", "unknown/not run"),
            ("alembic current", "unknown/not checked"),
            ("git commit/tag", "unknown/not checked"),
            ("worktree", "unknown/not checked"),
            ("DB health", "unknown/not checked"),
            ("Redis health", "unknown/not checked"),
            ("last error", "none"),
        )
    )
