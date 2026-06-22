from __future__ import annotations

from futures_mvp.modules.operator_console.view_models import DiagnosticViewModel


def read_only_diagnostics_placeholder() -> DiagnosticViewModel:
    return DiagnosticViewModel(
        items=(
            ("git commit/tag", "unknown/not checked"),
            ("worktree", "unknown/not checked"),
            ("last error", "none"),
        ),
        resolver=(
            ("resolver_status", "READY"),
            ("resolver_source", "static_fixture"),
        ),
        market_data=(
            ("selected_source", "static_fixture"),
            ("read_only_adapter_placeholder", "BLOCKED"),
        ),
        research=(("source_of_truth", "research only"),),
        paper=(("PaperResearchRuntime", "READY"),),
        safety=(
            ("ExecutionTarget", "MOCK only"),
            ("DB write", "disabled"),
            ("live trading", "disabled"),
            ("broker/CTP/SimNow", "disabled"),
        ),
    )
