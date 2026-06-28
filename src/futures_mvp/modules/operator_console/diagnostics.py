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
            ("read_only_adapter", "已阻断"),
            ("configuration", "未配置"),
            ("network", "不会访问网络"),
        ),
        broker=(
            ("BrokerReadOnlyAdapter", "BLOCKED"),
            ("Snapshot", "未配置"),
            ("Shadow Compare", "BLOCKED"),
            ("network/login/retry", "禁用"),
            ("submit/cancel/db_write", "禁用"),
        ),
        research=(("source_of_truth", "research only"),),
        paper=(("PaperResearchRuntime", "READY"),),
        safety=(
            ("ExecutionTarget", "MOCK only"),
            ("DB write", "禁用"),
            ("live trading", "禁用"),
            ("broker/CTP/SimNow", "禁用"),
        ),
    )
