from __future__ import annotations

from enum import StrEnum


class LabelKey(StrEnum):
    DASHBOARD = "总览"
    CONFIG_CENTER = "配置中心"
    DATA_CENTER = "数据中心"
    RESEARCH = "研究"
    PORTFOLIO = "组合"
    PAPER = "纸面模拟"
    BROKER = "券商只读"
    MARKET_DATA = "行情数据"
    DIAGNOSTICS = "系统诊断"


PAGE_TITLES: dict[str, str] = {
    "总览": "总览",
    "Dashboard": "总览",
    "配置中心": "配置中心",
    "数据中心": "数据中心",
    "Research": "研究",
    "Portfolio": "组合",
    "Paper": "纸面运行",
    "Broker": "券商只读",
    "Market Data": "行情数据",
    "系统诊断": "系统诊断",
    "Diagnostics": "系统诊断",
}

STATUS_LABELS: dict[str, str] = {
    "READY": "正常",
    "PAUSED": "已暂停",
    "FAILED": "失败",
    "BLOCKED": "已阻断",
    "DEGRADED": "降级",
    "DISABLED": "已禁用",
    "NOT_CONFIGURED": "未配置",
    "STOPPED": "已停止",
    "RUNNING": "运行中",
    "DRY_RUN": "预演",
    "DRY_RUN_COMPLETED": "预演完成",
    "COMPLETED": "完成",
    "DUPLICATE": "重复，无新写入",
    "CONFLICT": "冲突",
    "ERROR": "错误",
    "MATCH": "一致",
    "DIFFERENCE": "存在差异",
    "SETTLED": "已结算",
    "CALCULATED": "已计算",
    "APPLIED": "已应用",
    "CREATED": "已创建",
    "ACKED": "已确认",
    "FILLED": "已成交",
    "REJECTED": "已拒绝",
    "NOT_RUN": "尚未运行",
    "UNKNOWN": "未知",
    "True": "匹配",
    "False": "不匹配",
}

SAFETY_LABELS: dict[str, str] = {
    "Kill Switch": "紧急停止",
    "Scheduler Pause": "调度暂停",
    "Replay Pause": "回放暂停",
    "Broker Disabled": "券商已禁用",
    "Live Disabled": "实盘已禁用",
    "CTP Disabled": "CTP 已禁用",
    "SimNow Disabled": "SimNow 已禁用",
    "Real Capital Disabled": "真实资金禁用",
    "MOCK only": "仅本地模拟，不连接真实交易所",
}

ACTION_LABELS: dict[str, str] = {
    "Run Paper Dry-run": "查看最近一次纸面模拟结果（只预演，不写账本）",
    "Run Paper Apply": "纸面模拟写入已禁用",
    "Run SIM Dry-run": "查看本地仿真结果",
    "Run SIM Apply": "本地仿真写入已禁用",
    "View Result": "查看最近一次结果（只读）",
    "Refresh Health": "刷新状态",
    "Start Market Data Runtime": "检查行情运行状态（不连接券商，不下单）",
    "Stop Market Data Runtime": "停止本地行情查看",
    "Poll Market Data Once": "刷新一次行情状态",
    "Sync Historical Bars": "同步当前品种历史行情（不连接券商，不下单）",
    "Sync Selected Historical Bars": "同步当前品种历史行情（不连接券商，不下单）",
    "Resync Historical Bars": "重新同步该品种历史行情",
    "Check Historical Coverage": "检查覆盖",
    "Rebuild Historical Bars": "删除后重建该品种历史行情",
    "Check Data Quality": "检查数据质量",
    "Open Backtest Entry": "进入回测（只读本地历史行情）",
    "Open Paper Result": "查看纸面模拟（只读结果）",
    "Open Broker Read Only": "查看券商只读对照（不登录）",
    "Enable Kill Switch": "开启紧急停止",
    "Disable Kill Switch": "解除紧急停止",
    "Pause Scheduler": "暂停调度",
    "Resume Scheduler": "恢复调度",
    "Pause Replay": "暂停回放",
    "Resume Replay": "恢复回放",
}

RISK_NOTICES: dict[str, str] = {
    "dry-run no db write": "预演不会写入数据库",
    "apply writes local ledger": "写入会改本地账本",
    "no real capital": "当前不涉及真实资金",
    "no real exchange": "当前不会连接真实交易所",
    "no ctp simnow": "当前不会连接 CTP / SimNow",
    "targets disabled": "当前 PAPER / SIM / LIVE 目标仍未启用",
    "mock only target": "当前仅允许 MOCK",
    "research only": "当前只展示研究结果",
    "danger requires confirmation": "危险操作需要二次确认",
}

RESULT_LABELS: dict[str, str] = {
    "session status": "会话状态",
    "job status": "任务状态",
    "run status": "运行状态",
    "reason": "原因",
    "execution reports": "执行报告",
    "order status": "订单状态",
    "trades": "成交记录",
    "position updates": "仓位更新",
    "margin calculation": "保证金计算",
    "pnl calculation": "盈亏计算",
    "settlement snapshot": "结算快照",
    "duplicate detection": "重复检测",
    "db delta": "数据库写入变化",
    "target type": "目标类型",
}

CONFIG_LABELS: dict[str, str] = {
    "missing_fields": "缺少字段",
    "ready_for_dry_run": "配置可用于预演",
}

FORBIDDEN_ACTION_LABELS: dict[str, str] = {
    "LIVE Enable": "实盘启用：禁止",
    "Broker Enable": "券商启用：禁止",
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
    "beginner_workflow": "今天要完成什么",
    "workflow_help": "下一步",
    "workflow_board": "今日任务流程",
    "workflow_step": "任务步骤",
    "workflow_status": "当前状态",
    "workflow_next": "下一步",
    "workflow_action": "可点击操作",
    "why_blocked": "为什么",
    "safe_result": "安全吗",
    "next_action": "下一步",
    "developer_mode": "开发者模式",
    "developer_diagnostics": "高级诊断",
    "button_effect": "按钮后果",
    "safety_lock_card": "安全锁定",
    "safety_lock": "安全锁",
    "basic_config": "基本配置",
    "research_config": "研究配置",
    "paper_config": "纸面配置",
    "broker_config": "券商配置",
    "market_data_config": "行情配置",
    "run_config_preview": "本次运行配置",
    "config_checks": "配置检查",
    "next_step_card": "下一步操作",
    "latest_result_card": "最近结果",
    "what_is_this": "这是什么",
    "operation_flow": "操作流程",
    "current_buttons": "当前按钮",
    "paper_vs_sim": "与纸面模拟的区别",
    "locked_actions": "锁定项目",
    "status_overview": "状态概览",
    "risk_notices": "风险提示",
    "allowed_actions": "允许操作",
    "forbidden_actions": "禁止项",
    "normal_config": "普通配置",
    "advanced_config": "高级配置",
    "resolver_preview": "resolver 预览",
    "diagnostic_items": "诊断项目",
    "safety_banner": "安全边界",
    "market_data_status": "行情状态",
    "research_status": "研究状态",
    "pnl_summary": "盈亏摘要",
    "metrics": "指标",
    "orders": "订单",
    "trades": "成交",
    "positions": "持仓",
    "equity_curve": "权益曲线",
    "cash": "现金",
    "equity": "权益",
    "market_value": "市值",
    "cash_weight": "现金权重",
    "symbol_contributions": "品种贡献",
    "position_weights": "持仓权重",
    "allocation": "配置",
    "paper_runtime": "纸面模拟状态",
    "paper_lifecycle": "纸面模拟流程",
    "paper_consistency": "一致性报告",
    "paper_orders": "模拟委托",
    "paper_fills": "模拟成交",
    "paper_positions": "模拟持仓",
    "paper_portfolio": "模拟组合",
    "broker_status": "券商状态",
    "broker_accounts": "券商账户",
    "broker_positions": "券商持仓",
    "broker_orders": "券商订单",
    "broker_trades": "券商成交",
    "broker_shadow_compare": "只读对照",
    "broker_differences": "对照结果",
    "broker_diagnostics": "券商诊断",
    "broker_read_only_notice": (
        "券商只读页面只展示样例快照和只读对照，不登录、不重试、不报单、不撤单、不写数据库"
    ),
    "selected_data_source": "当前数据源",
    "static_fixture_status": "静态样例状态",
    "read_only_adapter_status": "只读适配器状态",
    "connection_status": "连接状态",
    "configuration_status": "配置状态",
    "latest_quote": "最近行情",
    "latest_bars": "最近 K 线",
    "updated_at": "更新时间",
    "runtime_status": "运行状态",
    "runtime_started": "是否已启动",
    "runtime_configured": "是否已配置",
    "runtime_source": "当前数据源",
    "symbol_status": "品种状态",
    "last_price": "最近价",
    "bars_summary": "K 线摘要",
    "akshare_available": "AkShare 可用性",
    "network_call_occurred": "网络调用是否已发生",
    "latest_error": "最近错误",
    "resolver_source": "resolver 来源",
    "blocked_reason": "阻断原因",
    "supported_symbols": "支持品种",
    "source_diagnostics": "数据源诊断",
    "historical_sync_controls": "历史行情同步",
    "historical_coverage": "本地库覆盖情况",
    "historical_sync_result": "历史行情同步结果",
    "data_center_sources": "数据源",
    "data_center_instruments": "当前品种",
    "data_center_coverage": "数据覆盖",
    "data_center_quality": "数据质量",
    "data_center_sync": "同步历史行情",
    "data_center_sync_result": "同步结果",
    "data_center_coverage_chart": "覆盖图",
    "data_center_diagnostics": "数据中心诊断",
    "data_quality_result": "数据质量检查结果",
    "data_center_step_config": "步骤 1：检查配置",
    "data_center_step_sync": "步骤 2：同步历史行情",
    "data_center_step_coverage": "步骤 3：检查覆盖",
    "data_center_step_quality": "步骤 4：检查质量",
    "data_center_step_backtest": "步骤 5：进入回测",
    "resolver_diagnostics": "合约解析诊断",
    "market_data_diagnostics": "行情诊断",
    "research_diagnostics": "研究诊断",
    "paper_diagnostics": "纸面模拟诊断",
    "safety_checks": "安全检查",
    "local_checks": "本地检查",
    "dry_run_required_config": "预演所需配置",
    "typed_command_preview": "命令预览",
    "command_sources": "命令来源",
    "result_history": "最近预演历史",
    "blocked_dry_run_title": "⚠️ 本次预演未执行",
    "blocked_next_steps": "下一步：",
    "blocked_safe_result": "安全结果：",
    "placeholder": "当前只展示可读结果，不执行真实动作",
    "disabled_placeholder": "当前不能点击，因为写入功能已关闭",
    "live_locked_notice": "🔒 当前不是实盘环境",
}

FIELD_LABELS: dict[str, str] = {
    "Runtime": "运行状态",
    "rollout mode": "运行模式",
    "mode": "模式",
    "target": "目标类型",
    "health": "健康状态",
    "latest result": "最近结果",
    "Research Platform": "研究平台",
    "Paper Runtime": "纸面运行时",
    "Portfolio": "组合",
    "Market Data": "行情源",
    "Diagnostics": "诊断信息",
    "current_source": "当前来源",
    "latest dry-run": "最近预演",
    "backtest_status": "回测状态",
    "strategy": "策略",
    "symbols": "品种",
    "timeframe": "时间周期",
    "realized_pnl": "已实现盈亏",
    "unrealized_pnl": "未实现盈亏",
    "total_return": "总收益",
    "max_equity": "最高权益",
    "min_equity": "最低权益",
    "points": "点数",
    "first_equity": "初始权益",
    "last_equity": "最新权益",
    "position_count": "持仓数",
    "all_match": "全部一致",
    "cash_matches": "现金一致",
    "equity_matches": "权益一致",
    "positions_match": "持仓一致",
    "orders_match": "订单一致",
    "fills_match": "成交一致",
    "selected_source": "选择数据源",
    "market_data_source": "行情数据源",
    "static_fixture": "静态样例",
    "read_only_market_data": "只读行情数据",
    "network": "网络",
    "real_quote": "真实行情",
    "position_mode": "仓位模式",
    "fixed_quantity": "固定数量",
    "fixed_capital": "固定资金",
    "commission": "手续费",
    "slippage": "滑点",
    "capital_allocation": "资金分配",
    "run_action": "本地流程",
    "pause_action": "暂停",
    "stop_action": "停止",
    "broker_read_only": "只读",
    "shadow_mode": "影子对照",
    "broker_disabled": "禁用",
    "live_trading": "实盘交易",
    "data_source_check": "数据源",
    "strategy_check": "策略",
    "resolver_check": "合约解析",
    "broker_check": "券商",
    "runtime_check": "运行时",
    "diagnostics_check": "诊断",
    "supported_symbols": "支持品种",
    "read_only_adapter_placeholder": "只读 Adapter 占位",
    "source_of_truth": "事实边界",
    "DB write": "写库",
    "live trading": "真实交易",
    "broker/CTP/SimNow": "券商/CTP/SimNow",
    "diagnostics": "诊断信息",
    "history": "历史记录",
    "page": "页面",
    "ExecutionTarget": "目标类型",
    "migration": "迁移状态",
    "Paper": "纸面模拟",
    "SIM": "SIM 最近结果",
    "Broker": "券商",
    "status": "状态",
    "reason": "原因",
    "currency": "币种",
    "broker_cash": "现金",
    "available": "可用资金",
    "equity": "权益",
    "margin": "保证金",
    "frozen": "冻结资金",
    "updated_at": "更新时间",
    "difference_count": "差异数量",
    "difference": "差异",
    "Kill Switch": "紧急停止",
    "Scheduler Pause": "调度暂停",
    "Replay Pause": "回放暂停",
    "account_id": "账户 ID",
    "trading_day": "交易日",
    "instrument_id": "行情合约",
    "trade_instrument_id": "交易合约",
    "symbol": "品种",
    "historical_symbol": "历史行情品种",
    "historical_trading_day": "历史行情开始日期",
    "historical_end_trading_day": "历史行情结束日期",
    "historical_timeframe": "历史行情周期",
    "data_center_symbol": "数据中心品种",
    "data_center_start": "覆盖开始",
    "data_center_end": "覆盖结束",
    "data_center_timeframe": "时间周期",
    "exchange": "交易所",
    "resolver_status": "合约解析状态",
    "resolver_source": "来源",
    "resolver_confidence": "置信度",
    "effective_window": "生效区间",
    "resolver_note": "合约来源",
    "resolver_notice": "合约解析说明",
    "quantity": "数量",
    "price": "价格",
    "allowed instruments": "合约白名单：默认使用合约解析得到的交易合约",
    "direction_offset": "方向/开平",
    "dry_run": "预演",
    "db_write": "写库",
    "instrument whitelist": "合约白名单：默认使用合约解析得到的交易合约",
    "current_whitelist": "当前白名单",
    "max_order_size": "最大委托数量",
    "max_position_size": "最大持仓数量",
    "max_daily_loss": "最大日亏损",
    "max order size": "最大委托数量",
    "max position size": "最大持仓数量",
    "max daily loss": "最大日亏损",
    "Paper/SIM mode": "纸面模拟/SIM 模式",
    "dry-run/apply": "预演/写入",
    "runtime_id": "运行时 ID",
    "config_hash": "配置哈希",
    "migration revision": "迁移版本",
    "capital control details": "资金控制详情",
    "command source / typed command provider": "命令来源",
    "job_factory": "任务工厂",
}

DIAGNOSTIC_LABELS: dict[str, str] = {
    "pytest status": "pytest 状态",
    "ruff status": "ruff 状态",
    "mypy status": "mypy 状态",
    "git commit/tag": "Git commit/tag",
    "worktree": "工作区状态",
    "last error": "最近错误",
}

DIAGNOSTIC_VALUE_LABELS: dict[str, str] = {
    "unknown/not run": "未知/未运行",
    "unknown/not checked": "未知/未检查",
    "none": "无",
}

DASHBOARD_TEXT: dict[str, str] = {
    "system_ready": "✅ 运行正常",
    "current_mode": "当前模式：纸面模拟",
    "current_target": "当前目标：仅 MOCK",
    "migration_ready": "数据库迁移：正常",
    "recommended_actions": "推荐操作：",
    "paper_dry_run_first": "1. 先运行纸面模拟预演",
    "view_result_second": "2. 再查看运行结果",
    "sim_after_safety": "3. 确认安全后再考虑 SIM 预演",
    "not_run_yet": "当前尚未运行",
    "db_delta_zero": "数据库写入变化：0",
    "latest_status_none": "最近状态：无",
}

PAPER_TEXT: dict[str, str] = {
    "purpose_ledger": "纸面模拟用于验证交易账本链路",
    "not_exchange": "不模拟真实交易所",
    "no_capital": "不涉及真实资金",
    "mock_only": "当前仅 MOCK",
    "step_dry_run": "1. 运行纸面模拟预演",
    "step_view_result": "2. 查看预演结果",
    "step_future_apply": "3. 确认后未来才允许纸面模拟写入",
    "dry_run_hint": "预演不会写数据库",
    "apply_disabled_hint": "写入会改本地账本，所以当前禁用",
}

SIM_TEXT: dict[str, str] = {
    "local_sim": "SIM 是本地仿真",
    "not_simnow": "不是 SimNow",
    "not_ctp": "不是 CTP",
    "not_live": "不是实盘",
    "mock_only": "当前仍然 MOCK only",
    "paper_difference": "纸面模拟：验证账本链路",
    "sim_difference": "SIM：验证仿真交易行为",
    "future_behaviors": "SIM 未来才可能支持部分成交、滑点、延迟",
}

SAFETY_EXPLANATIONS: dict[str, str] = {
    "Kill Switch": "说明：开启后阻止纸面模拟/SIM 运行",
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
    "margin_pnl": "保证金 / 盈亏：尚未计算",
    "settlement_snapshot": "结算快照：尚未生成",
}

REASON_LABELS: dict[str, str] = {
    "paper dry-run requires complete session config": (
        "当前缺少完整的纸面模拟预演配置，因此没有执行"
    ),
    "sim dry-run requires complete session config": "当前缺少完整的 SIM 预演配置，因此没有执行",
    "paper dry-run requires a session job factory": "当前缺少完整的纸面模拟预演配置，因此没有执行",
    "sim dry-run requires a session job factory": "当前缺少完整的 SIM 预演配置，因此没有执行",
    "paper dry-run requires typed commands or command_provider": (
        "当前缺少完整的纸面模拟预演配置，因此没有执行"
    ),
    "sim dry-run requires typed commands or command_provider": (
        "当前缺少完整的 SIM 预演配置，因此没有执行"
    ),
    "dry-run provider is not configured": "当前没有可用的预演执行器",
    "缺少必填配置": "当前缺少必填配置，因此没有执行",
    "配置中心不允许请求 apply": "配置中心不允许请求 apply，已阻断",
    "配置中心只允许 MOCK 目标": "配置中心只允许 MOCK 目标，已阻断",
    "数量必须大于 0": "数量必须大于 0，已阻断",
    "价格必须大于 0": "价格必须大于 0，已阻断",
    "交易日格式必须是 YYYY-MM-DD": "交易日格式必须是 YYYY-MM-DD，已阻断",
    "合约不在允许列表中": "合约不在允许列表中，已阻断",
    "resolver 未找到合约": "合约解析未找到匹配合约，已阻断",
    "resolver 结果不唯一": "合约解析结果不唯一，已阻断",
    "resolver 合约已过期": "合约解析结果不覆盖当前交易日，已阻断",
    "resolver 输入无效": "合约解析输入无效，已阻断",
    "resolver metadata 无效": "合约静态信息缺失或无效，已阻断",
    "resolver 未解析合约": "合约解析未解析出合约，已阻断",
    "只读行情 Adapter 尚未配置": "只读行情 Adapter 尚未配置，已阻断",
    "broker read only adapter is not configured": "券商只读适配器未配置，已阻断",
    "broker snapshot source is not configured": "券商快照源未配置，已阻断",
    "broker account id is required": "券商账户 ID 缺失，已阻断",
    "broker network blocked": "券商网络错误，已阻断",
    "broker login failed": "券商登录失败，已阻断",
    "broker account does not exist": "券商账户不存在，已阻断",
    "broker snapshot missing": "券商快照缺失，已阻断",
    "broker snapshot blocked": "券商快照被阻断",
    "paper result blocked": "纸面模拟结果被阻断",
    "默认样例仅用于展示，不代表业务事实": "默认样例仅用于展示，不代表业务事实",
    "无": "无",
    "missing provider": "当前没有可用的预演执行器",
    "dry-run returned non-MOCK target": "当前目标不是 MOCK，已阻止执行",
    "paper console dry-run supports MOCK target only": "当前目标不是 MOCK，已阻止执行",
    "sim console dry-run supports MOCK target only": "当前目标不是 MOCK，已阻止执行",
    "non-MOCK target": "当前目标不是 MOCK，已阻止执行",
    "dry-run returned non-zero DB delta": "预演出现数据库写入变化，已阻止标记为成功",
    "db_delta nonzero": "预演出现数据库写入变化，已阻止标记为成功",
}

CONFIG_TEXT: dict[str, str] = {
    "preview_blocked": "当前配置还不能生成命令预览。",
    "preview_ready": "配置可用于预演。",
}

BLOCKED_RESULT_TEXT: dict[str, str] = {
    "description": "系统已安全阻断本次操作，没有写入数据库，也没有连接真实交易所。",
    "next_step_config": "1. 打开配置中心",
    "next_step_check": (
        "2. 检查账户 ID、交易日、resolver 推荐交易合约白名单、"
        "最大单笔数量、最大持仓数量、最大日亏损"
    ),
    "next_step_retry": "3. 回到纸面模拟/SIM 页面重新运行预演",
    "safe_db_delta_zero": "✅ 数据库写入变化：0",
    "safe_target_mock": "✅ 目标类型：仅本地模拟，不连接真实交易所",
    "safe_no_capital": "✅ 真实资金：未使用",
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


def config_label(key: str) -> str:
    return CONFIG_LABELS.get(key, key)


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


def config_text(key: str) -> str:
    return CONFIG_TEXT.get(key, key)


def reason_label(reason: str | None) -> str:
    if reason is None:
        return ""
    return REASON_LABELS.get(reason, reason)


def blocked_result_text(key: str) -> str:
    return BLOCKED_RESULT_TEXT.get(key, key)


def live_locked_text(key: str) -> str:
    return LIVE_LOCKED_TEXT.get(key, key)


def _label_key(value: object) -> str:
    if isinstance(value, StrEnum):
        return value.value
    return str(value)
