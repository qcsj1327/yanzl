from futures_mvp.modules.operator_console import labels


def test_all_page_titles_have_chinese_mapping() -> None:
    expected = {
        "Dashboard": "总览",
        "Research": "Research 研究",
        "Portfolio": "Portfolio 组合",
        "Paper": "Paper 纸面",
        "Market Data": "Market Data 行情",
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
    assert labels.safety_label("Broker Disabled") == "Broker 已禁用"
    assert labels.safety_label("Live Disabled") == "LIVE 已禁用"
    assert labels.safety_label("CTP Disabled") == "CTP 已禁用"
    assert labels.safety_label("SimNow Disabled") == "SimNow 已禁用"
    assert labels.safety_label("MOCK only") == "仅本地模拟，不连接真实交易所"

    assert labels.action_label("Run Paper Dry-run") == "运行 Paper 预演"
    assert labels.action_label("Run Paper Apply") == "确认运行 Paper 写入"
    assert labels.action_label("Run SIM Dry-run") == "运行 SIM 预演"
    assert labels.action_label("Run SIM Apply") == "确认运行 SIM 写入"
    assert labels.action_label("View Result") == "查看结果"
    assert labels.action_label("Refresh Health") == "刷新状态"
    assert labels.action_label("Enable Kill Switch") == "开启紧急停止"
    assert labels.action_label("Disable Kill Switch") == "解除紧急停止"
    assert labels.action_label("Pause Scheduler") == "暂停调度"
    assert labels.action_label("Resume Scheduler") == "恢复调度"
    assert labels.action_label("Pause Replay") == "暂停回放"
    assert labels.action_label("Resume Replay") == "恢复回放"

    for value in (
        "dry-run 不会写入数据库",
        "apply 会写入本地账本",
        "当前不涉及真实资金",
        "当前不会连接真实交易所",
        "当前不会连接 CTP / SimNow",
        "当前 PAPER / SIM / LIVE 目标仍未启用",
        "当前仅允许 MOCK target",
        "危险操作需要二次确认",
    ):
        assert value in labels.RISK_NOTICES.values()

    for value in (
        "执行报告",
        "订单状态",
        "成交记录",
        "仓位更新",
        "保证金计算",
        "PnL 计算",
        "结算快照",
        "重复检测",
        "数据库写入变化",
        "目标类型",
        "原因",
    ):
        assert value in labels.RESULT_LABELS.values()

    assert labels.config_label("missing_fields") == "缺少字段"
    assert labels.config_label("ready_for_dry_run") == "配置可用于预演"
    assert labels.section_label("typed_command_preview") == "typed 命令预览"
    assert labels.section_label("command_sources") == "命令来源"
    assert labels.section_label("result_history") == "最近预演历史"
    assert (
        labels.config_text("preview_blocked")
        == "当前配置还不能生成 typed dry-run command preview。"
    )
    assert labels.config_text("preview_ready") == "配置可用于预演。"


def test_blocked_reason_labels_are_user_facing_chinese() -> None:
    expected = {
        "paper dry-run requires complete session config": (
            "当前缺少完整的 Paper 预演配置，因此没有执行"
        ),
        "sim dry-run requires complete session config": "当前缺少完整的 SIM 预演配置，因此没有执行",
        "missing provider": "当前没有可用的预演执行器",
        "缺少必填配置": "当前缺少必填配置，因此没有执行",
        "数量必须大于 0": "数量必须大于 0，已阻断",
        "价格必须大于 0": "价格必须大于 0，已阻断",
        "合约不在允许列表中": "合约不在允许列表中，已阻断",
        "resolver metadata 无效": "resolver 静态元数据缺失或无效，已阻断",
        "non-MOCK target": "当前目标不是 MOCK，已阻止执行",
        "db_delta nonzero": "预演出现数据库写入变化，已阻止标记为成功",
    }

    for reason, display in expected.items():
        assert labels.reason_label(reason) == display


def test_ui_polish_field_and_diagnostic_labels_exist() -> None:
    expected_fields = {
        "Operator Console": "本地操作台",
        "Runtime": "运行时",
        "rollout mode": "运行模式",
        "mode": "模式",
        "target": "目标类型",
        "health": "健康状态",
        "latest result": "最近结果",
        "diagnostics": "诊断",
        "history": "历史记录",
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

    for key, value in expected.items():
        assert labels.forbidden_action_label(key) == value
