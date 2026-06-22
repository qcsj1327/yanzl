from decimal import Decimal

from futures_mvp.domain.enums import ExecutionTarget
from futures_mvp.modules.market_data.models import (
    InstrumentResolution,
    InstrumentResolveStatus,
)
from futures_mvp.modules.operator_console.config_assembly import (
    MOCK_TARGET,
    READ_ONLY_ADAPTER_DATA_SOURCE,
    STATIC_FIXTURE_DATA_SOURCE,
    ConsoleDryRunConfig,
    append_history,
    assemble_config,
    blocked_config_result,
    validate_config,
)
from futures_mvp.modules.operator_console.labels import reason_label


def test_valid_config_creates_typed_command_preview() -> None:
    assembly = assemble_config(_valid_config())

    assert assembly.validation.blocked is False
    assert assembly.preview is not None
    assert assembly.preview.account_id == "account-1"
    assert assembly.preview.trading_day == "2026-06-12"
    assert assembly.preview.instrument_id == "ao9999"
    assert assembly.preview.trade_instrument_id == "ao2609"
    assert assembly.preview.direction == "BUY"
    assert assembly.preview.offset == "OPEN"
    assert assembly.preview.quantity == "1"
    assert assembly.preview.price == "500"
    assert assembly.preview.target == MOCK_TARGET
    assert assembly.preview.dry_run == "是"
    assert assembly.preview.db_write == "否"
    assert assembly.preview.market_data_source == STATIC_FIXTURE_DATA_SOURCE
    assert assembly.command is not None
    assert assembly.command.execution_target is ExecutionTarget.MOCK
    assert assembly.command.instrument_id == "ao9999"
    assert assembly.command.trade_instrument_id == "ao2609"
    assert assembly.command.quantity == Decimal("1")
    assert assembly.command.price == Decimal("500")
    assert assembly.resolver_consumer_context is not None
    assert assembly.resolver_consumer_context.identity.symbol == "ao"
    assert assembly.resolver_consumer_context.identity.trading_day.isoformat() == "2026-06-12"
    assert assembly.resolver_consumer_context.lineage.resolver_source == "static_fixture"


def test_read_only_adapter_placeholder_blocks_preview_without_command() -> None:
    assembly = assemble_config(
        _valid_config(market_data_source=READ_ONLY_ADAPTER_DATA_SOURCE)
    )

    assert assembly.validation.blocked is True
    assert assembly.validation.reason == "只读行情 Adapter 尚未配置"
    assert assembly.validation.missing_fields == ("market_data_source",)
    assert assembly.preview is None
    assert assembly.command is None


def test_missing_fields_are_blocked_with_chinese_reason_and_list() -> None:
    validation = validate_config(ConsoleDryRunConfig())

    assert validation.blocked is True
    assert validation.reason == "缺少必填配置"
    assert validation.missing_fields == (
        "account_id",
        "trading_day",
        "symbol",
    )

    result = blocked_config_result(validation.reason, validation.missing_fields)
    assert result.session_status == "BLOCKED"
    assert "account_id" in (result.reason or "")
    assert reason_label(validation.reason) == "当前缺少必填配置，因此没有执行"


def test_non_mock_and_apply_requested_are_impossible_from_valid_ui_config() -> None:
    config = _valid_config()

    assert config.target == MOCK_TARGET
    assert config.apply_requested is False

    non_mock = validate_config(_valid_config(target="SIM"))
    apply_requested = validate_config(_valid_config(apply_requested=True))

    assert non_mock.blocked is True
    assert non_mock.reason == "配置中心只允许 MOCK 目标"
    assert apply_requested.blocked is True
    assert apply_requested.reason == "配置中心不允许请求 apply"


def test_quantity_and_price_must_be_positive() -> None:
    bad_quantity = validate_config(_valid_config(quantity="0"))
    bad_price = validate_config(_valid_config(price="-1"))

    assert bad_quantity.blocked is True
    assert bad_quantity.reason == "数量必须大于 0"
    assert bad_quantity.missing_fields == ("quantity",)
    assert bad_price.blocked is True
    assert bad_price.reason == "价格必须大于 0"
    assert bad_price.missing_fields == ("price",)


def test_allowed_instruments_mismatch_is_blocked() -> None:
    validation = validate_config(
        _valid_config(allowed_instruments=("rb2601",))
    )

    assert validation.blocked is True
    assert validation.reason == "合约不在允许列表中"
    assert validation.missing_fields == ("allowed instruments",)


def test_config_uses_resolver_result_over_manual_instrument_fields() -> None:
    assembly = assemble_config(
        _valid_config(
            instrument_id="manual9999",
            trade_instrument_id="manual2609",
            exchange="MANUAL",
        )
    )

    assert assembly.validation.blocked is False
    assert assembly.preview is not None
    assert assembly.preview.instrument_id == "ao9999"
    assert assembly.preview.trade_instrument_id == "ao2609"
    assert assembly.preview.exchange == "SHFE"


def test_unresolved_resolver_blocks_dry_run_even_with_manual_instruments() -> None:
    validation = validate_config(
        _valid_config(
            symbol="unknown",
            instrument_id="ao9999",
            trade_instrument_id="ao2609",
        )
    )

    assert validation.blocked is True
    assert validation.reason == "resolver 未找到合约"
    assert validation.missing_fields == ("resolver",)


def test_metadata_invalid_resolver_blocks_dry_run() -> None:
    validation = validate_config(
        _valid_config(
            resolver_resolution=InstrumentResolution(
                status=InstrumentResolveStatus.METADATA_INVALID,
                symbol="ao",
                instrument_id="ao9999",
                trade_instrument_id="ao2609",
                diagnostics=(
                    "static fixture only, not live market source",
                    "metadata invalid / missing",
                    "trade contract ao2609 metadata missing",
                ),
            )
        )
    )

    assert validation.blocked is True
    assert validation.reason == "resolver metadata 无效"
    assert validation.missing_fields == ("resolver",)


def test_history_append_is_in_memory_and_limited() -> None:
    history = ()
    for index in range(7):
        history = append_history(
            history,
            mode="PAPER",
            result=blocked_config_result(f"reason-{index}"),
            limit=5,
        )

    assert len(history) == 5
    assert history[0].reason == "reason-6"
    assert history[-1].reason == "reason-2"


def _valid_config(**overrides: object) -> ConsoleDryRunConfig:
    values: dict[str, object] = {
        "account_id": "account-1",
        "trading_day": "2026-06-12",
        "instrument_id": "",
        "trade_instrument_id": "",
        "symbol": "ao",
        "exchange": "",
        "quantity": "1",
        "price": "500",
        "max_order_size": "1",
        "max_position_size": "1",
        "max_daily_loss": "1000",
        "allowed_instruments": ("ao2609",),
    }
    values.update(overrides)
    return ConsoleDryRunConfig(**values)
