from futures_mvp.modules.operator_console import labels


def test_all_page_titles_have_chinese_mapping() -> None:
    expected = {
        "Dashboard": "总览",
        "Paper Session": "Paper 纸面交易",
        "SIM Session": "SIM 本地仿真",
        "Safety Controls": "安全控制",
        "Configuration": "配置中心",
        "Results / History": "运行结果",
        "Diagnostics": "系统诊断",
        "Live Locked Page": "LIVE 锁定",
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
    assert labels.safety_label("MOCK only") == "仅 MOCK，本地模拟"

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
        "当前 ExecutionTarget.PAPER / SIM / LIVE 仍未启用",
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
    ):
        assert value in labels.RESULT_LABELS.values()


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
