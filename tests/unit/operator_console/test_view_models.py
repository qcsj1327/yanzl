from futures_mvp.modules.operator_console.labels import safety_label
from futures_mvp.modules.operator_console.view_models import (
    ConsoleActionStatus,
    OperatorPage,
    default_console_view_model,
)


def test_default_view_model_has_all_pages() -> None:
    model = default_console_view_model()

    assert model.pages == tuple(OperatorPage)
    assert len(model.pages) == 8
    assert model.pages[1] is OperatorPage.CONFIG_CENTER


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
    assert dict(model.research.metrics)["total_return"] == "0.0012"
    assert model.portfolio.cash == "96420"
    assert dict(model.portfolio.position_weights)["ao"] == "0.0050"
    assert model.market_data.selected_source == "static_fixture"
    assert model.market_data.read_only_adapter_status == "已阻断"
    assert model.market_data.configuration_status == "未配置"
    assert model.market_data.connection_status == "未连接"
    assert model.market_data.blocked_reason == "只读行情适配器未配置，不会访问网络"
    assert model.market_data.supported_symbols == ("ao", "rb", "ag", "cu")
    assert dict(model.paper_page.consistency)["all_match"] == "True"
    assert model.broker.status == "READY"
    assert dict(model.broker.shadow_compare)["status"] == "DIFFERENCE"
    assert model.broker.accounts


def test_default_view_model_has_config_center_sections() -> None:
    model = default_console_view_model()

    assert dict(model.config_center.basic) == {
        "account_id": "demo",
        "trading_day": "2026-06-28",
        "market_data_source": "静态样例",
        "rollout mode": "本地模拟",
        "symbols": "AO、RB",
        "timeframe": "日线",
    }
    assert dict(model.config_center.research)["strategy"] == "BuyAndHold"
    assert dict(model.config_center.research)["commission"] == "0.0001"
    assert dict(model.config_center.research)["slippage"] == "1 Tick"
    assert dict(model.config_center.paper)["status"] == "未启动"
    assert dict(model.config_center.broker) == {
        "Broker": "只读",
        "broker_read_only": "只读",
        "shadow_mode": "启用",
        "broker_disabled": "禁用",
    }
    assert dict(model.config_center.market_data)["read_only_market_data"] == "未配置"
    assert dict(model.config_center.market_data)["network"] == "不会联网"
    assert dict(model.config_center.market_data)["real_quote"] == "不会读取真实行情"
    assert dict(model.config_center.safety_locks) == {
        "live_trading": "关闭",
        "Paper": "启用",
        "Broker": "只读",
        "ExecutionTarget": "未启用",
    }
    assert dict(model.config_center.run_preview)["rollout mode"] == "MOCK"
    assert dict(model.config_center.checks)["broker_check"] == "只读"


def test_default_diagnostics_are_unknown_read_only_values() -> None:
    model = default_console_view_model()

    assert dict(model.diagnostics.items) == {
        "git commit/tag": "unknown/not checked",
        "worktree": "unknown/not checked",
        "last error": "none",
    }
    assert dict(model.diagnostics.safety) == {
        "ExecutionTarget": "MOCK only",
        "DB write": "禁用",
        "live trading": "禁用",
        "broker/CTP/SimNow": "禁用",
    }
    assert dict(model.diagnostics.broker)["submit/cancel"] == "禁用"


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
