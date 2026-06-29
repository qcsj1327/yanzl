from futures_mvp.modules.operator_console.labels import safety_label
from futures_mvp.modules.operator_console.view_models import (
    ConsoleActionStatus,
    OperatorPage,
    default_console_view_model,
)


def test_default_view_model_has_all_pages() -> None:
    model = default_console_view_model()

    assert model.pages == tuple(OperatorPage)
    assert len(model.pages) == 9
    assert model.pages[1] is OperatorPage.CONFIG_CENTER
    assert model.pages[2] is OperatorPage.DATA_CENTER


def test_default_view_model_is_mock_only_and_live_locked() -> None:
    model = default_console_view_model()

    assert model.dashboard.execution_target_status == "MOCK only"
    assert safety_label(model.dashboard.execution_target_status) == "仅本地模拟，不连接真实交易所"
    assert set(model.live_locked.disabled_states) == {
        "Live Disabled",
        "Broker Disabled",
        "CTP Disabled",
        "SimNow Disabled",
        "MOCK only",
    }
    assert all(not action.clickable for action in model.live_locked.forbidden_actions)


def test_apply_buttons_are_disabled_placeholders() -> None:
    model = default_console_view_model()

    assert model.paper.apply_button.disabled is True
    assert model.paper.apply_button.status is ConsoleActionStatus.DISABLED_PLACEHOLDER


def test_default_view_model_renders_research_portfolio_and_market_data() -> None:
    model = default_console_view_model()

    assert model.research.backtest_status == "COMPLETED"
    assert dict(model.research.metrics)["总收益"] == "0.0012"
    assert model.portfolio.cash == "96420"
    assert dict(model.portfolio.position_weights)["AO"] == "0.0050"
    assert model.market_data.selected_source == "static_fixture"
    assert model.market_data.read_only_adapter_status == "已阻断"
    assert model.market_data.configuration_status == "未配置"
    assert model.market_data.connection_status == "未连接"
    assert model.market_data.blocked_reason == "只读行情适配器未配置，不会访问网络"
    assert model.market_data.supported_symbols == ("ao", "rb", "ag", "cu")
    assert "AkShare" in dict(model.data_center.data_sources)
    assert set(dict(model.data_center.instruments)) == {"AO", "RB", "AG", "CU"}
    assert set(dict(model.data_center.historical_coverage)) == {"AO", "RB", "AG", "CU"}
    assert set(dict(model.data_center.data_quality)) == {"AO", "RB", "AG", "CU"}
    assert dict(model.paper_page.consistency)["全部一致"] == "是"
    assert model.broker.status == "READY"
    assert dict(model.broker.shadow_compare)["状态"] == "样例对照"
    assert model.broker.accounts


def test_default_view_model_has_config_center_sections() -> None:
    model = default_console_view_model()

    assert dict(model.config_center.basic) == {
        "我是谁": "账户 ID：demo",
        "我要跑哪天": "交易日：2026-06-28",
        "我要看哪些品种": "AO、RB、AG、CU",
        "我要用什么数据": "默认静态样例；真实数据需在数据中心同步",
        "我要跑什么模式": "本地模拟 / 只读 / 禁止实盘",
    }
    assert dict(model.config_center.research)["用什么策略"] == "BuyAndHold"
    assert dict(model.config_center.research)["手续费多少"] == "0.0001"
    assert dict(model.config_center.research)["滑点多少"] == "1 Tick"
    assert dict(model.config_center.paper)["当前状态"] == "未启动"
    assert dict(model.config_center.broker) == {
        "券商模式": "只读",
        "只读快照": "只展示，不登录",
        "只读对照": "启用",
        "禁止登录": "是",
        "禁止下单": "是",
        "禁止撤单": "是",
    }
    assert dict(model.config_center.market_data)["真实行情是否已配置"] == "未配置"
    assert dict(model.config_center.market_data)["是否会联网"] == "不会自动联网"
    assert dict(model.config_center.market_data)["是否已有本地历史数据"] == "请进入数据中心检查"
    assert dict(model.config_center.safety_locks) == {
        "实盘交易": "关闭",
        "纸面模拟": "只查看，不自动执行",
            "券商": "只读",
        "交易目标": "未启用",
        "数据库": "只写历史K线，不写交易事实",
    }
    assert dict(model.config_center.run_preview)["运行模式"] == "仅本地模拟"
    assert dict(model.config_center.checks)["broker_check"] == "只读"


def test_default_diagnostics_are_unknown_read_only_values() -> None:
    model = default_console_view_model()

    assert dict(model.diagnostics.items) == {
        "git commit/tag": "unknown/not checked",
        "worktree": "unknown/not checked",
        "last error": "none",
    }
    assert dict(model.diagnostics.safety) == {
        "交易目标": "MOCK only",
        "写库": "禁用",
        "实盘交易": "禁用",
        "券商/CTP/SimNow": "禁用",
    }
    assert dict(model.diagnostics.data_center)["AkShare"] == "显式点击才读取"
    assert dict(model.diagnostics.broker)["报单/撤单"] == "禁用"


def test_default_config_view_model_is_unconfigured_and_mock_only() -> None:
    model = default_console_view_model()

    assert model.configuration.dry_run_config.target == "MOCK only"
    assert model.configuration.dry_run_config.apply_requested is False
    assert model.configuration.validation.blocked is True
    assert ("静态样例", "可用") in model.configuration.market_data_sources
    assert ("只读适配器", "已阻断/未配置") in model.configuration.market_data_sources
    assert "instrument_id" not in dict(model.configuration.dry_run_required)
    assert "trade_instrument_id" not in dict(model.configuration.dry_run_required)
    assert "resolver_status" in dict(model.configuration.dry_run_required)
    assert model.results.history == ()
