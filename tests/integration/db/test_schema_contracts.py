from datetime import UTC, date, datetime
from decimal import Decimal
from importlib import util
from pathlib import Path
from types import ModuleType

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    select,
)

from futures_mvp.db.models import (
    Base,
    ExecutionCommand,
    FeatureSnapshot,
    MarginSnapshot,
    MarketBar,
    MarketTick,
    NormalizedExecutionReport,
    Order,
    OrderEvent,
    OrderIntent,
    PnLSnapshot,
    Position,
    PositionEvent,
    SettlementSnapshot,
    SignalCandidate,
    SignalEvent,
    Trade,
    TradingRiskResult,
)
from futures_mvp.domain.enums import SettlementResultStatus
from futures_mvp.domain.models import SettlementSnapshot as DomainSettlementSnapshot


def _unique_constraint_columns(model: type[object], name: str) -> tuple[str, ...]:
    for constraint in model.__table__.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.name == name:
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"missing unique constraint {name}")


def _load_stage_f_migration() -> ModuleType:
    migration_path = Path("alembic/versions/0007_stage_f_settlement_engine.py")
    spec = util.spec_from_file_location("stage_f_settlement_migration", migration_path)
    if spec is None or spec.loader is None:
        raise AssertionError("failed to load stage f migration")
    migration = util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_required_tables_are_declared() -> None:
    assert {
        "instruments",
        "trading_calendars",
        "trading_sessions",
        "orders",
        "order_events",
        "trades",
        "positions",
        "position_events",
        "pnl_snapshots",
        "account_snapshots",
        "settlement_snapshots",
        "market_ticks",
        "market_bars",
        "feature_snapshots",
        "signal_candidates",
        "signal_events",
        "risk_results",
        "order_intents",
        "execution_commands",
        "normalized_execution_reports",
        "risk_events",
    }.issubset(Base.metadata.tables)


def test_order_events_match_current_schema_idempotency() -> None:
    assert _unique_constraint_columns(OrderEvent, "uq_order_events_source_external") == (
        "event_source",
        "external_event_id",
    )
    assert "raw_payload" in OrderEvent.__table__.columns


def test_order_events_have_business_occurred_at() -> None:
    occurred_at = OrderEvent.__table__.columns["occurred_at"]

    assert isinstance(occurred_at.type, DateTime)
    assert occurred_at.type.timezone is True
    assert occurred_at.nullable is False


def test_orders_have_repository_version_column() -> None:
    version = Order.__table__.columns["version"]

    assert isinstance(version.type, Integer)
    assert version.nullable is False
    assert version.default is not None


def test_trades_unique_constraint_matches_exchange_trade_identity() -> None:
    assert _unique_constraint_columns(Trade, "uq_trades_account_exchange_trade") == (
        "account_id",
        "exchange",
        "exchange_trade_id",
    )


def test_trades_have_stage_b_typed_fact_fields() -> None:
    for column_name in [
        "fee_amount",
        "fee_currency",
        "fee_source",
        "trading_day",
        "source_exchange_report_id",
        "raw_payload",
    ]:
        assert column_name in Trade.__table__.columns


def test_trades_have_stage_l3_oms_to_trade_bridge_fields() -> None:
    for column_name in [
        "client_order_id",
        "trade_instrument_id",
        "symbol",
        "identity_source",
        "source_report_id",
        "source_order_event_id",
    ]:
        assert column_name in Trade.__table__.columns


def test_normalized_execution_reports_have_stage_l3_typed_trade_inputs() -> None:
    for column_name in [
        "exchange_trade_id",
        "fill_id",
        "fee_amount",
        "fee_currency",
        "fee_source",
    ]:
        assert column_name in NormalizedExecutionReport.__table__.columns


def test_execution_commands_match_stage_k_idempotency_contract() -> None:
    assert _unique_constraint_columns(
        ExecutionCommand,
        "uq_execution_commands_command_id",
    ) == ("command_id",)
    for column_name in [
        "command_id",
        "order_id",
        "client_order_id",
        "account_id",
        "symbol",
        "instrument_id",
        "trade_instrument_id",
        "exchange",
        "side",
        "offset",
        "quantity",
        "price",
        "order_type",
        "tif",
        "command_type",
        "execution_target",
        "command_payload_hash",
        "raw_payload",
        "created_at",
    ]:
        assert column_name in ExecutionCommand.__table__.columns

    assert isinstance(ExecutionCommand.__table__.columns["quantity"].type, Numeric)
    assert isinstance(ExecutionCommand.__table__.columns["price"].type, Numeric)
    assert "ix_execution_commands_order_id" in {
        index.name for index in ExecutionCommand.__table__.indexes
    }
    assert "ix_execution_commands_client_order_id" in {
        index.name for index in ExecutionCommand.__table__.indexes
    }
    assert "ix_execution_commands_execution_target" in {
        index.name for index in ExecutionCommand.__table__.indexes
    }


def test_normalized_execution_reports_match_stage_l_idempotency_contract() -> None:
    assert _unique_constraint_columns(
        NormalizedExecutionReport,
        "uq_normalized_execution_reports_report_id",
    ) == ("report_id",)
    assert _unique_constraint_columns(
        NormalizedExecutionReport,
        "uq_normalized_execution_reports_raw_report_id",
    ) == ("raw_report_id",)
    for column_name in [
        "report_id",
        "raw_report_id",
        "adapter_name",
        "execution_target",
        "command_id",
        "order_id",
        "client_order_id",
        "adapter_order_ref",
        "exchange_order_id",
        "execution_status",
        "filled_qty",
        "fill_price",
        "cumulative_filled_qty",
        "remaining_qty",
        "report_ts",
        "source_report_hash",
        "reason",
        "raw_payload",
        "normalized_at",
        "created_at",
    ]:
        assert column_name in NormalizedExecutionReport.__table__.columns

    assert isinstance(NormalizedExecutionReport.__table__.columns["filled_qty"].type, Numeric)
    assert isinstance(NormalizedExecutionReport.__table__.columns["fill_price"].type, Numeric)
    assert "ix_normalized_execution_reports_order_id" in {
        index.name for index in NormalizedExecutionReport.__table__.indexes
    }
    assert "ix_normalized_execution_reports_command_id" in {
        index.name for index in NormalizedExecutionReport.__table__.indexes
    }
    assert "ix_normalized_execution_reports_client_order_id" in {
        index.name for index in NormalizedExecutionReport.__table__.indexes
    }
    assert "ix_normalized_execution_reports_execution_status" in {
        index.name for index in NormalizedExecutionReport.__table__.indexes
    }
    assert "ix_normalized_execution_reports_report_ts" in {
        index.name for index in NormalizedExecutionReport.__table__.indexes
    }


def test_positions_are_single_row_per_account_and_instrument() -> None:
    assert _unique_constraint_columns(Position, "uq_positions_account_inst") == (
        "account_id",
        "instrument_id",
    )
    for column_name in [
        "long_today_qty",
        "long_yesterday_qty",
        "short_today_qty",
        "short_yesterday_qty",
        "frozen_long_qty",
        "frozen_short_qty",
        "long_avg_price",
        "short_avg_price",
        "settlement_price",
        "last_price",
        "realized_pnl",
        "unrealized_pnl",
        "margin_used",
        "version",
    ]:
        assert column_name in Position.__table__.columns

    version = Position.__table__.columns["version"]
    assert isinstance(version.type, Integer)
    assert version.nullable is False


def test_position_events_match_stage_c_idempotency_and_audit_contract() -> None:
    assert _unique_constraint_columns(
        PositionEvent,
        "uq_position_events_account_exchange_trade",
    ) == ("account_id", "exchange", "exchange_trade_id")
    for column_name in [
        "id",
        "account_id",
        "instrument_id",
        "exchange",
        "exchange_trade_id",
        "trade_id",
        "position_id",
        "event_type",
        "direction",
        "offset",
        "price",
        "quantity",
        "before_snapshot",
        "after_snapshot",
        "occurred_at",
        "created_at",
        "raw_payload",
    ]:
        assert column_name in PositionEvent.__table__.columns

    assert isinstance(PositionEvent.__table__.columns["price"].type, Numeric)
    assert isinstance(PositionEvent.__table__.columns["quantity"].type, Numeric)
    assert PositionEvent.__table__.columns["created_at"].nullable is False


def test_margin_snapshots_match_stage_l5_accounting_identity_contract() -> None:
    assert _unique_constraint_columns(
        MarginSnapshot,
        "uq_margin_snapshots_account_instrument_calculation",
    ) == ("account_id", "instrument_id", "calculation_key")
    for column_name in [
        "id",
        "account_id",
        "instrument_id",
        "position_version",
        "trading_day",
        "config_hash",
        "rule_id",
        "rule_version",
        "calculation_key",
        "long_qty",
        "short_qty",
        "price",
        "contract_multiplier",
        "initial_margin",
        "maintenance_margin",
        "margin_used",
        "available_cash",
        "equity",
        "calculated_at",
        "created_at",
    ]:
        assert column_name in MarginSnapshot.__table__.columns

    assert MarginSnapshot.__table__.columns["trading_day"].nullable is False
    assert MarginSnapshot.__table__.columns["config_hash"].nullable is False
    assert {
        "ix_margin_snapshots_l5_accounting_identity",
    }.issubset({index.name for index in MarginSnapshot.__table__.indexes})


def test_pnl_snapshots_match_stage_e_idempotency_contract() -> None:
    assert _unique_constraint_columns(
        PnLSnapshot,
        "uq_pnl_snapshots_account_instrument_calculation",
    ) == ("account_id", "instrument_id", "calculation_key")
    for column_name in [
        "id",
        "account_id",
        "instrument_id",
        "position_version",
        "trading_day",
        "config_hash",
        "trade_id",
        "margin_snapshot_id",
        "calculation_key",
        "price_basis",
        "mark_price",
        "contract_multiplier",
        "realized_pnl",
        "unrealized_pnl",
        "total_pnl",
        "fee_amount",
        "calculated_at",
        "created_at",
    ]:
        assert column_name in PnLSnapshot.__table__.columns

    assert isinstance(PnLSnapshot.__table__.columns["mark_price"].type, Numeric)
    assert isinstance(PnLSnapshot.__table__.columns["realized_pnl"].type, Numeric)
    assert PnLSnapshot.__table__.columns["trading_day"].nullable is False
    assert PnLSnapshot.__table__.columns["config_hash"].nullable is False
    assert PnLSnapshot.__table__.columns["created_at"].nullable is False
    assert {
        "ix_pnl_snapshots_l5_accounting_identity",
    }.issubset({index.name for index in PnLSnapshot.__table__.indexes})


def test_settlement_snapshots_match_stage_f_account_day_contract() -> None:
    assert _unique_constraint_columns(
        SettlementSnapshot,
        "uq_settlement_account_day",
    ) == ("account_id", "trading_day")
    for column_name in [
        "id",
        "account_id",
        "trading_day",
        "calculation_key",
        "status",
        "reason",
        "positions_before",
        "positions_after",
        "settlement_prices",
        "pnl_snapshot_ids",
        "margin_snapshot_ids",
        "account_snapshot_before_id",
        "account_snapshot_after_id",
        "cash_before",
        "cash_after",
        "realized_pnl",
        "unrealized_pnl",
        "margin_used",
        "created_at",
    ]:
        assert column_name in SettlementSnapshot.__table__.columns

    assert isinstance(SettlementSnapshot.__table__.columns["cash_before"].type, Numeric)
    assert isinstance(SettlementSnapshot.__table__.columns["cash_after"].type, Numeric)
    assert isinstance(SettlementSnapshot.__table__.columns["margin_used"].type, Numeric)
    assert SettlementSnapshot.__table__.columns["calculation_key"].nullable is False
    assert {
        "ix_settlement_snapshots_account_id",
        "ix_settlement_snapshots_trading_day",
        "ix_settlement_snapshots_account_day",
        "ix_settlement_snapshots_calculation_key",
    }.issubset({index.name for index in SettlementSnapshot.__table__.indexes})


def test_market_ticks_match_stage_g_market_data_contract() -> None:
    assert _unique_constraint_columns(MarketTick, "uq_market_ticks_identity") == (
        "exchange",
        "instrument_id",
        "ts",
        "source",
    )
    for column_name in [
        "id",
        "symbol",
        "instrument_id",
        "trade_instrument_id",
        "exchange",
        "trading_day",
        "ts",
        "price",
        "volume",
        "turnover",
        "open_interest",
        "bid_price_1",
        "ask_price_1",
        "bid_volume_1",
        "ask_volume_1",
        "source",
        "raw_payload",
        "received_at",
    ]:
        assert column_name in MarketTick.__table__.columns
    assert isinstance(MarketTick.__table__.columns["price"].type, Numeric)
    assert {
        "ix_market_ticks_exchange",
        "ix_market_ticks_instrument_id",
        "ix_market_ticks_trading_day",
        "ix_market_ticks_ts",
        "ix_market_ticks_exchange_instrument_day",
    }.issubset({index.name for index in MarketTick.__table__.indexes})


def test_market_bars_match_stage_g_market_data_contract() -> None:
    assert _unique_constraint_columns(MarketBar, "uq_market_bars_identity") == (
        "exchange",
        "instrument_id",
        "timeframe",
        "bar_ts",
        "source",
    )
    for column_name in [
        "id",
        "symbol",
        "instrument_id",
        "trade_instrument_id",
        "exchange",
        "trading_day",
        "timeframe",
        "bar_ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover",
        "open_interest",
        "source",
        "quality_status",
        "raw_payload",
        "received_at",
    ]:
        assert column_name in MarketBar.__table__.columns
    assert isinstance(MarketBar.__table__.columns["open"].type, Numeric)
    assert {
        "ix_market_bars_exchange",
        "ix_market_bars_instrument_id",
        "ix_market_bars_trading_day",
        "ix_market_bars_bar_ts",
        "ix_market_bars_timeframe",
        "ix_market_bars_exchange_instrument_day",
    }.issubset({index.name for index in MarketBar.__table__.indexes})


def test_feature_snapshots_match_stage_h_feature_snapshot_contract() -> None:
    assert _unique_constraint_columns(FeatureSnapshot, "uq_feature_snapshots_identity") == (
        "exchange",
        "instrument_id",
        "timeframe",
        "bar_ts",
        "feature_version",
        "feature_config_hash",
    )
    for column_name in [
        "id",
        "symbol",
        "instrument_id",
        "trade_instrument_id",
        "exchange",
        "trading_day",
        "timeframe",
        "bar_ts",
        "feature_version",
        "feature_config_hash",
        "source_bar_keys",
        "returns",
        "bar_return",
        "price_range",
        "range",
        "atr",
        "volume_ratio",
        "moving_average",
        "bias",
        "breakout_level",
        "volatility",
        "momentum",
        "source_window_start",
        "source_window_end",
        "warmup_complete",
        "quality_status",
        "missing_bar_count",
        "gap_count",
        "raw_payload",
        "calculated_at",
        "received_at",
    ]:
        assert column_name in FeatureSnapshot.__table__.columns
    assert isinstance(FeatureSnapshot.__table__.columns["source_bar_keys"].type, JSON)
    assert isinstance(FeatureSnapshot.__table__.columns["returns"].type, Numeric)
    assert {
        "ix_feature_snapshots_exchange",
        "ix_feature_snapshots_instrument_id",
        "ix_feature_snapshots_trading_day",
        "ix_feature_snapshots_timeframe",
        "ix_feature_snapshots_bar_ts",
        "ix_feature_snapshots_feature_version",
        "ix_feature_snapshots_feature_config_hash",
        "ix_feature_snapshots_exchange_instrument_day",
    }.issubset({index.name for index in FeatureSnapshot.__table__.indexes})


def test_signal_candidates_match_stage_i_signal_contract() -> None:
    assert _unique_constraint_columns(SignalCandidate, "uq_signal_candidates_signal_id") == (
        "signal_id",
    )
    assert _unique_constraint_columns(
        SignalCandidate,
        "uq_signal_candidates_strategy_feature_identity",
    ) == (
        "strategy_name",
        "strategy_version",
        "strategy_config_hash",
        "instrument_id",
        "timeframe",
        "bar_ts",
        "feature_version",
        "feature_config_hash",
    )
    for column_name in [
        "signal_id",
        "strategy_name",
        "strategy_version",
        "strategy_config_hash",
        "runtime_id",
        "symbol",
        "instrument_id",
        "trade_instrument_id",
        "exchange",
        "trading_day",
        "timeframe",
        "bar_ts",
        "feature_version",
        "feature_config_hash",
        "decision",
        "side",
        "position_side",
        "confidence",
        "strength",
        "reason",
        "expected_price",
        "stop_loss",
        "take_profit",
        "holding_period_hint",
        "tags",
        "features_ref",
        "raw_payload",
        "created_at",
    ]:
        assert column_name in SignalCandidate.__table__.columns
    assert isinstance(SignalCandidate.__table__.columns["confidence"].type, Numeric)
    assert isinstance(SignalCandidate.__table__.columns["tags"].type, JSON)
    assert isinstance(SignalCandidate.__table__.columns["features_ref"].type, JSON)
    assert {
        "ix_signal_candidates_strategy_version",
        "ix_signal_candidates_exchange_instrument_day",
        "ix_signal_candidates_timeframe_bar_ts",
        "ix_signal_candidates_signal_id",
    }.issubset({index.name for index in SignalCandidate.__table__.indexes})


def test_signal_events_match_stage_i_lifecycle_contract() -> None:
    assert _unique_constraint_columns(SignalEvent, "uq_signal_events_event_key") == ("event_key",)
    for column_name in [
        "id",
        "event_key",
        "signal_id",
        "lifecycle_status",
        "event_reason",
        "event_ts",
        "raw_payload",
        "created_at",
    ]:
        assert column_name in SignalEvent.__table__.columns
    assert isinstance(SignalEvent.__table__.columns["raw_payload"].type, JSON)
    assert {
        "ix_signal_events_signal_id",
        "ix_signal_events_signal_created",
    }.issubset({index.name for index in SignalEvent.__table__.indexes})


def test_stage_j_trading_workflow_tables_match_contract() -> None:
    assert _unique_constraint_columns(
        TradingRiskResult,
        "uq_risk_results_risk_result_id",
    ) == ("risk_result_id",)
    for column_name in [
        "risk_result_id",
        "signal_id",
        "evaluation_context_hash",
        "risk_status",
        "risk_reason",
        "risk_level",
        "requested_quantity",
        "approved_quantity",
        "max_quantity",
        "expected_margin",
        "expected_notional",
        "config_hash",
        "evaluation_ts",
        "raw_payload",
        "created_at",
    ]:
        assert column_name in TradingRiskResult.__table__.columns
    for column_name in [
        "evaluation_context_hash",
        "requested_quantity",
        "approved_quantity",
        "max_quantity",
        "expected_margin",
        "expected_notional",
    ]:
        assert TradingRiskResult.__table__.columns[column_name].nullable is False

    assert _unique_constraint_columns(OrderIntent, "uq_order_intents_intent_id") == (
        "intent_id",
    )
    for column_name in [
        "intent_id",
        "signal_id",
        "risk_result_id",
        "strategy_name",
        "strategy_version",
        "strategy_config_hash",
        "runtime_id",
        "symbol",
        "instrument_id",
        "trade_instrument_id",
        "exchange",
        "trading_day",
        "timeframe",
        "bar_ts",
        "feature_version",
        "feature_config_hash",
        "side",
        "offset",
        "quantity",
        "price",
        "order_type",
        "tif",
        "expected_margin",
        "expected_notional",
        "intent_reason",
        "raw_payload",
        "created_at",
    ]:
        assert column_name in OrderIntent.__table__.columns
    assert isinstance(OrderIntent.__table__.columns["quantity"].type, Numeric)
    assert isinstance(OrderIntent.__table__.columns["price"].type, Numeric)
    assert OrderIntent.__table__.columns["expected_margin"].nullable is False
    assert OrderIntent.__table__.columns["expected_notional"].nullable is False
    assert {
        "ix_order_intents_signal_id",
        "ix_order_intents_risk_result_id",
        "ix_order_intents_instrument_id",
        "ix_order_intents_trading_day",
    }.issubset({index.name for index in OrderIntent.__table__.indexes})


def test_stage_f_migration_backfills_legacy_calculation_key() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    metadata = MetaData()
    settlement_snapshots = Table(
        "settlement_snapshots",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("trading_day", Date, nullable=False),
        Column("account_id", String(length=64), nullable=False),
        Column("cash_before", Numeric(precision=28, scale=8), nullable=False),
        Column("cash_after", Numeric(precision=28, scale=8), nullable=False),
        Column("positions_before", JSON, nullable=False),
        Column("positions_after", JSON, nullable=False),
        Column("settlement_prices", JSON, nullable=False),
        Column("raw_payload", JSON, nullable=False),
        Column("calculation_key", String(length=256), nullable=False, server_default=""),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            settlement_snapshots.insert().values(
                id=7,
                trading_day=date(2026, 6, 4),
                account_id="account-1",
                cash_before=Decimal("10000"),
                cash_after=Decimal("10100"),
                positions_before=[],
                positions_after=[],
                settlement_prices=[],
                raw_payload={},
            )
        )
        migration = _load_stage_f_migration()
        migration._backfill_legacy_calculation_keys(connection)  # type: ignore[attr-defined]
        row = connection.execute(select(settlement_snapshots)).mappings().one()

    assert row["calculation_key"] == "legacy:account-1:2026-06-04:7"
    DomainSettlementSnapshot(
        account_id=row["account_id"],
        trading_day=row["trading_day"],
        calculation_key=row["calculation_key"],
        positions_before=(),
        positions_after=(),
        settlement_prices=(),
        pnl_snapshot_ids=(),
        margin_snapshot_ids=(),
        cash_before=row["cash_before"],
        cash_after=row["cash_after"],
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        margin_used=Decimal("0"),
        status=SettlementResultStatus.SETTLED,
        created_at=datetime(2026, 6, 4, 15, tzinfo=UTC),
    )
