from futures_mvp.modules.operator_console import labels


def test_all_page_titles_have_chinese_mapping() -> None:
    expected = {
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

    for key, value in expected.items():
        assert labels.page_title(key) == value


def test_required_status_labels_exist() -> None:
    expected = {
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
    }

    for key, value in expected.items():
        assert labels.status_label(key) == value


def test_required_safety_action_risk_and_result_labels_exist() -> None:
    assert labels.safety_label("Kill Switch") == "紧急停止"
    assert labels.safety_label("Scheduler Pause") == "调度暂停"
    assert labels.safety_label("Replay Pause") == "回放暂停"
    assert labels.safety_label("Broker Disabled") == "券商已禁用"
    assert labels.safety_label("Live Disabled") == "实盘已禁用"
    assert labels.safety_label("CTP Disabled") == "CTP 已禁用"
    assert labels.safety_label("SimNow Disabled") == "SimNow 已禁用"
    assert labels.safety_label("MOCK only") == "仅本地模拟，不连接真实交易所"

    assert (
        labels.action_label("Run Paper Dry-run")
        == "查看最近一次纸面模拟结果（只预演，不写账本）"
    )
    assert labels.action_label("Run Paper Apply") == "纸面模拟写入已禁用"
    assert labels.action_label("Run SIM Dry-run") == "查看本地仿真结果"
    assert labels.action_label("Run SIM Apply") == "本地仿真写入已禁用"
    assert labels.action_label("View Result") == "查看最近一次结果（只读）"
    assert labels.action_label("Refresh Health") == "刷新状态"
    assert (
        labels.action_label("Sync Historical Bars")
        == "同步当前品种历史行情（不连接券商，不下单）"
    )
    assert labels.action_label("Resync Historical Bars") == "重新同步该品种历史行情"
    assert labels.action_label("Check Historical Coverage") == "检查覆盖"
    assert labels.action_label("Rebuild Historical Bars") == "删除后重建该品种历史行情"
    assert labels.action_label("Check Data Quality") == "检查数据质量"
    assert labels.action_label("Enable Kill Switch") == "开启紧急停止"
    assert labels.action_label("Disable Kill Switch") == "解除紧急停止"
    assert labels.action_label("Pause Scheduler") == "暂停调度"
    assert labels.action_label("Resume Scheduler") == "恢复调度"
    assert labels.action_label("Pause Replay") == "暂停回放"
    assert labels.action_label("Resume Replay") == "恢复回放"

    for value in (
        "预演不会写入数据库",
        "写入会改本地账本",
        "当前不涉及真实资金",
        "当前不会连接真实交易所",
        "当前不会连接 CTP / SimNow",
        "当前 PAPER / SIM / LIVE 目标仍未启用",
        "当前仅允许 MOCK",
        "危险操作需要二次确认",
    ):
        assert value in labels.RISK_NOTICES.values()

    for value in (
        "执行报告",
        "订单状态",
        "成交记录",
        "仓位更新",
        "保证金计算",
        "盈亏计算",
        "结算快照",
        "重复检测",
        "数据库写入变化",
        "目标类型",
        "原因",
    ):
        assert value in labels.RESULT_LABELS.values()

    assert labels.config_label("missing_fields") == "缺少字段"
    assert labels.config_label("ready_for_dry_run") == "配置可用于预演"
    assert labels.section_label("typed_command_preview") == "命令预览"
    assert labels.section_label("command_sources") == "命令来源"
    assert labels.section_label("result_history") == "最近预演历史"
    assert labels.section_label("basic_config") == "基本配置"
    assert labels.section_label("research_config") == "研究配置"
    assert labels.section_label("paper_config") == "纸面配置"
    assert labels.section_label("broker_config") == "券商配置"
    assert labels.section_label("market_data_config") == "行情配置"
    assert labels.section_label("data_center_sources") == "数据源"
    assert labels.section_label("data_center_instruments") == "当前品种"
    assert labels.section_label("data_center_coverage") == "数据覆盖"
    assert labels.section_label("data_center_quality") == "数据质量"
    assert labels.section_label("data_center_diagnostics") == "数据中心诊断"
    assert labels.section_label("safety_lock") == "安全锁"
    assert labels.section_label("run_config_preview") == "本次运行配置"
    assert labels.section_label("config_checks") == "配置检查"
    assert (
        labels.config_text("preview_blocked")
        == "当前配置还不能生成命令预览。"
    )
    assert labels.config_text("preview_ready") == "配置可用于预演。"


def test_blocked_reason_labels_are_user_facing_chinese() -> None:
    expected = {
        "paper dry-run requires complete session config": (
            "当前缺少完整的纸面模拟预演配置，因此没有执行"
        ),
        "sim dry-run requires complete session config": "当前缺少完整的 SIM 预演配置，因此没有执行",
        "missing provider": "当前没有可用的预演执行器",
        "缺少必填配置": "当前缺少必填配置，因此没有执行",
        "数量必须大于 0": "数量必须大于 0，已阻断",
        "价格必须大于 0": "价格必须大于 0，已阻断",
        "合约不在允许列表中": "合约不在允许列表中，已阻断",
        "resolver metadata 无效": "合约静态信息缺失或无效，已阻断",
        "non-MOCK target": "当前目标不是 MOCK，已阻止执行",
        "db_delta nonzero": "预演出现数据库写入变化，已阻止标记为成功",
    }

    for reason, display in expected.items():
        assert labels.reason_label(reason) == display


def test_ui_polish_field_and_diagnostic_labels_exist() -> None:
    expected_fields = {
        "Operator Console": "本地操作台",
        "Runtime": "运行状态",
        "rollout mode": "运行模式",
        "mode": "模式",
        "target": "目标类型",
        "health": "健康状态",
        "latest result": "最近结果",
        "diagnostics": "诊断信息",
        "history": "历史记录",
        "timeframe": "时间周期",
        "position_mode": "仓位模式",
        "fixed_quantity": "固定数量",
        "fixed_capital": "固定资金",
        "commission": "手续费",
        "slippage": "滑点",
        "capital_allocation": "资金分配",
        "run_action": "本地流程",
        "pause_action": "暂停",
        "stop_action": "停止",
        "read_only_market_data": "只读行情数据",
        "live_trading": "实盘交易",
        "data_source_check": "数据源",
        "strategy_check": "策略",
        "resolver_check": "合约解析",
        "broker_check": "券商",
        "runtime_check": "运行时",
        "diagnostics_check": "诊断",
    }
    for key, value in expected_fields.items():
        lookup = labels.section_label(key) if key == "Operator Console" else labels.field_label(key)
        assert lookup == value

    expected_diagnostics = {
        "pytest status": "pytest 状态",
        "ruff status": "ruff 状态",
        "mypy status": "mypy 状态",
        "git commit/tag": "Git commit/tag",
        "worktree": "工作区状态",
        "last error": "最近错误",
    }
    for key, value in expected_diagnostics.items():
        assert labels.diagnostic_label(key) == value

    assert labels.diagnostic_value_label("unknown/not run") == "未知/未运行"
    assert labels.diagnostic_value_label("unknown/not checked") == "未知/未检查"
    assert labels.diagnostic_value_label("none") == "无"


def test_forbidden_action_labels_exist() -> None:
    expected = {
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

    for key, value in expected.items():
        assert labels.forbidden_action_label(key) == value
