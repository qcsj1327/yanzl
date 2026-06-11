from __future__ import annotations

from enum import StrEnum


class LabelKey(StrEnum):
    DASHBOARD = "Dashboard"
    PAPER_SESSION = "Paper Session"
    SIM_SESSION = "SIM Session"
    SAFETY_CONTROLS = "Safety Controls"
    CONFIGURATION = "Configuration"
    RESULTS_HISTORY = "Results / History"
    DIAGNOSTICS = "Diagnostics"
    LIVE_LOCKED_PAGE = "Live Locked Page"


PAGE_TITLES: dict[str, str] = {
    "Dashboard": "总览",
    "Paper Session": "Paper 纸面交易",
    "SIM Session": "SIM 本地仿真",
    "Safety Controls": "安全控制",
    "Configuration": "配置中心",
    "Results / History": "运行结果",
    "Diagnostics": "系统诊断",
    "Live Locked Page": "LIVE 锁定",
}

STATUS_LABELS: dict[str, str] = {
    "READY": "正常",
    "PAUSED": "已暂停",
    "FAILED": "失败",
    "BLOCKED": "已阻断",
    "DISABLED": "已禁用",
    "DRY_RUN": "预演",
    "DRY_RUN_COMPLETED": "预演完成",
    "COMPLETED": "完成",
    "DUPLICATE": "重复，无新写入",
    "CONFLICT": "冲突",
    "ERROR": "错误",
    "SETTLED": "已结算",
    "CALCULATED": "已计算",
    "APPLIED": "已应用",
    "CREATED": "已创建",
    "ACKED": "已确认",
    "FILLED": "已成交",
    "REJECTED": "已拒绝",
    "NOT_RUN": "尚未运行",
}

SAFETY_LABELS: dict[str, str] = {
    "Kill Switch": "紧急停止",
    "Scheduler Pause": "调度暂停",
    "Replay Pause": "回放暂停",
    "Broker Disabled": "Broker 已禁用",
    "Live Disabled": "LIVE 已禁用",
    "CTP Disabled": "CTP 已禁用",
    "SimNow Disabled": "SimNow 已禁用",
    "Real Capital Disabled": "真实资金禁用",
    "MOCK only": "仅本地模拟，不连接真实交易所",
}

ACTION_LABELS: dict[str, str] = {
    "Run Paper Dry-run": "运行 Paper 预演",
    "Run Paper Apply": "确认运行 Paper 写入",
    "Run SIM Dry-run": "运行 SIM 预演",
    "Run SIM Apply": "确认运行 SIM 写入",
    "View Result": "查看结果",
    "Refresh Health": "刷新状态",
    "Enable Kill Switch": "开启紧急停止",
    "Disable Kill Switch": "解除紧急停止",
    "Pause Scheduler": "暂停调度",
    "Resume Scheduler": "恢复调度",
    "Pause Replay": "暂停回放",
    "Resume Replay": "恢复回放",
}

RISK_NOTICES: dict[str, str] = {
    "dry-run no db write": "dry-run 不会写入数据库",
    "apply writes local ledger": "apply 会写入本地账本",
    "no real capital": "当前不涉及真实资金",
    "no real exchange": "当前不会连接真实交易所",
    "no ctp simnow": "当前不会连接 CTP / SimNow",
    "targets disabled": "当前 ExecutionTarget.PAPER / SIM / LIVE 仍未启用",
    "mock only target": "当前仅允许 MOCK target",
    "danger requires confirmation": "危险操作需要二次确认",
}

RESULT_LABELS: dict[str, str] = {
    "session status": "会话状态",
    "job status": "任务状态",
    "run status": "运行状态",
    "execution reports": "执行报告",
    "order status": "订单状态",
    "trades": "成交记录",
    "position updates": "仓位更新",
    "margin calculation": "保证金计算",
    "pnl calculation": "PnL 计算",
    "settlement snapshot": "结算快照",
    "duplicate detection": "重复检测",
    "db delta": "数据库写入变化",
    "target type": "目标类型",
}

FORBIDDEN_ACTION_LABELS: dict[str, str] = {
    "LIVE Enable": "LIVE 启用：禁止",
    "Broker Enable": "Broker 启用：禁止",
    "CTP Connect": "CTP 连接：禁止",
    "SimNow Connect": "SimNow 连接：禁止",
    "Real Capital Trading": "真实资金交易：禁止",
    "Manual Order Edit": "手动改订单：禁止",
    "Manual Trade Edit": "手动改成交：禁止",
    "Manual Position Edit": "手动改仓位：禁止",
    "Manual Ledger Edit": "手动改账本：禁止",
}

SECTION_LABELS: dict[str, str] = {
    "Operator Console": "本地操作台",
    "system_status_card": "系统状态",
    "safety_lock_card": "安全锁定",
    "next_step_card": "下一步操作",
    "latest_result_card": "最近结果",
    "what_is_this": "这是什么",
    "operation_flow": "操作流程",
    "current_buttons": "当前按钮",
    "paper_vs_sim": "与 Paper 的区别",
    "locked_actions": "锁定项目",
    "status_overview": "状态概览",
    "risk_notices": "风险提示",
    "allowed_actions": "允许操作",
    "forbidden_actions": "禁止项",
    "normal_config": "普通配置",
    "advanced_config": "高级配置",
    "diagnostic_items": "诊断项目",
    "placeholder": "第一版仅展示占位，不执行真实动作",
    "disabled_placeholder": "当前为禁用占位",
    "live_locked_notice": "🔒 当前不是实盘环境",
}

FIELD_LABELS: dict[str, str] = {
    "Runtime": "运行时",
    "rollout mode": "运行模式",
    "mode": "模式",
    "target": "目标类型",
    "health": "健康状态",
    "latest result": "最近结果",
    "diagnostics": "诊断",
    "history": "历史记录",
    "page": "页面",
    "ExecutionTarget": "目标类型",
    "migration": "迁移状态",
    "Paper": "Paper 最近结果",
    "SIM": "SIM 最近结果",
    "Kill Switch": "紧急停止",
    "Scheduler Pause": "调度暂停",
    "Replay Pause": "回放暂停",
    "account_id": "账户 ID",
    "trading_day": "交易日",
    "instrument whitelist": "合约白名单",
    "max order size": "最大委托数量",
    "max position size": "最大持仓数量",
    "max daily loss": "最大日亏损",
    "Paper/SIM mode": "Paper/SIM 模式",
    "dry-run/apply": "预演/写入",
    "runtime_id": "运行时 ID",
    "config_hash": "配置哈希",
    "migration revision": "迁移版本",
    "capital control details": "资金控制详情",
}

DIAGNOSTIC_LABELS: dict[str, str] = {
    "pytest status": "pytest 状态",
    "ruff status": "ruff 状态",
    "mypy status": "mypy 状态",
    "alembic current": "Alembic 当前版本",
    "git commit/tag": "Git commit/tag",
    "worktree": "工作区状态",
    "DB health": "DB 健康状态",
    "Redis health": "Redis 健康状态",
    "last error": "最近错误",
}

DIAGNOSTIC_VALUE_LABELS: dict[str, str] = {
    "unknown/not run": "未知/未运行",
    "unknown/not checked": "未知/未检查",
    "none": "无",
}

DASHBOARD_TEXT: dict[str, str] = {
    "system_ready": "✅ 运行正常",
    "current_mode": "当前模式：PAPER",
    "current_target": "当前目标：仅 MOCK",
    "migration_ready": "数据库迁移：正常",
    "recommended_actions": "推荐操作：",
    "paper_dry_run_first": "1. 先运行 Paper 预演",
    "view_result_second": "2. 再查看运行结果",
    "sim_after_safety": "3. 确认安全后再考虑 SIM 预演",
    "not_run_yet": "当前尚未运行",
    "db_delta_zero": "数据库写入变化：0",
    "latest_status_none": "最近状态：无",
}

PAPER_TEXT: dict[str, str] = {
    "purpose_ledger": "Paper 用于验证交易账本链路",
    "not_exchange": "不模拟真实交易所",
    "no_capital": "不涉及真实资金",
    "mock_only": "当前仅 MOCK",
    "step_dry_run": "1. 运行 Paper 预演",
    "step_view_result": "2. 查看预演结果",
    "step_future_apply": "3. 确认后未来才允许 Paper 写入",
    "dry_run_hint": "预演不会写数据库",
    "apply_disabled_hint": "写入会改本地账本，所以当前禁用",
}

SIM_TEXT: dict[str, str] = {
    "local_sim": "SIM 是本地仿真",
    "not_simnow": "不是 SimNow",
    "not_ctp": "不是 CTP",
    "not_live": "不是实盘",
    "mock_only": "当前仍然 MOCK only",
    "paper_difference": "Paper：验证账本链路",
    "sim_difference": "SIM：验证仿真交易行为",
    "future_behaviors": "SIM 未来才可能支持部分成交、滑点、延迟",
}

SAFETY_EXPLANATIONS: dict[str, str] = {
    "Kill Switch": "说明：开启后阻止 Paper/SIM 运行",
    "Scheduler Pause": "说明：暂停自动任务",
    "Replay Pause": "说明：暂停历史回放或重放流程",
}

RESULT_STATUS_TEXT: dict[str, str] = {
    "current_status": "当前状态：尚未运行",
    "latest_run": "最近运行：无",
    "db_delta": "数据库写入变化：0",
    "execution_reports": "执行报告：尚未生成",
    "order_status": "订单状态：尚未更新",
    "trades": "成交记录：尚未生成",
    "position_updates": "仓位更新：尚未生成",
    "margin_pnl": "保证金 / PnL：尚未计算",
    "settlement_snapshot": "结算快照：尚未生成",
}

LIVE_LOCKED_TEXT: dict[str, str] = {
    "no_exchange": "不会连接真实交易所",
    "no_ctp": "不会连接 CTP",
    "no_simnow": "不会连接 SimNow",
    "no_capital": "不会使用真实资金",
    "no_live_button": "没有任何启用 LIVE 的按钮",
}


def page_title(key: str) -> str:
    return PAGE_TITLES.get(key, key)


def status_label(value: object) -> str:
    key = _label_key(value)
    return STATUS_LABELS.get(key, key)


def safety_label(key: str) -> str:
    return SAFETY_LABELS.get(key, key)


def action_label(key: str) -> str:
    return ACTION_LABELS.get(key, key)


def risk_notice(key: str) -> str:
    return RISK_NOTICES.get(key, key)


def result_label(key: str) -> str:
    return RESULT_LABELS.get(key, key)


def forbidden_action_label(key: str) -> str:
    return FORBIDDEN_ACTION_LABELS.get(key, f"{key}：禁止")


def section_label(key: str) -> str:
    return SECTION_LABELS.get(key, key)


def field_label(key: str) -> str:
    return FIELD_LABELS.get(key, key)


def diagnostic_label(key: str) -> str:
    return DIAGNOSTIC_LABELS.get(key, key)


def diagnostic_value_label(value: str) -> str:
    return DIAGNOSTIC_VALUE_LABELS.get(value, value)


def dashboard_text(key: str) -> str:
    return DASHBOARD_TEXT.get(key, key)


def paper_text(key: str) -> str:
    return PAPER_TEXT.get(key, key)


def sim_text(key: str) -> str:
    return SIM_TEXT.get(key, key)


def safety_explanation(key: str) -> str:
    return SAFETY_EXPLANATIONS.get(key, key)


def result_status_text(key: str) -> str:
    return RESULT_STATUS_TEXT.get(key, key)


def live_locked_text(key: str) -> str:
    return LIVE_LOCKED_TEXT.get(key, key)


def _label_key(value: object) -> str:
    if isinstance(value, StrEnum):
        return value.value
    return str(value)
