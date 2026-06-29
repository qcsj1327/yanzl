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
            ("券商只读适配器", "已阻断"),
            ("Snapshot", "未配置"),
            ("只读对照", "已阻断"),
            ("网络/登录/重试", "禁用"),
            ("报单/撤单/写库", "禁用"),
        ),
        research=(("事实来源", "仅研究结果"),),
        paper=(("纸面模拟运行状态", "正常"),),
        safety=(
            ("交易目标", "MOCK only"),
            ("写库", "禁用"),
            ("实盘交易", "禁用"),
            ("券商/CTP/SimNow", "禁用"),
        ),
    )
