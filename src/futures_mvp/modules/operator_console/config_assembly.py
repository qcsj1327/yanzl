from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from futures_mvp.domain.enums import (
    Direction,
    ExecutionCommandType,
    ExecutionTarget,
    Offset,
    OrderType,
)
from futures_mvp.domain.models import ExecutionCommand
from futures_mvp.modules.operator_console.actions import DryRunActionResult

MOCK_TARGET = "MOCK only"
READ_ONLY_DIRECTION = Direction.BUY
READ_ONLY_OFFSET = Offset.OPEN
DEFAULT_HISTORY_LIMIT = 5


@dataclass(frozen=True)
class ConsoleDryRunConfig:
    account_id: str = ""
    trading_day: str = ""
    instrument_id: str = ""
    trade_instrument_id: str = ""
    symbol: str = ""
    exchange: str = ""
    quantity: str = ""
    price: str = ""
    max_order_size: str = ""
    max_position_size: str = ""
    max_daily_loss: str = ""
    allowed_instruments: tuple[str, ...] = ()
    is_example: bool = False
    target: str = MOCK_TARGET
    apply_requested: bool = False


@dataclass(frozen=True)
class CommandPreview:
    account_id: str
    trading_day: str
    instrument_id: str
    trade_instrument_id: str
    symbol: str
    exchange: str
    direction: str
    offset: str
    quantity: str
    price: str
    target: str
    dry_run: str
    db_write: str


@dataclass(frozen=True)
class ConfigValidationResult:
    blocked: bool
    reason: str | None = None
    missing_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConfigAssemblyResult:
    config: ConsoleDryRunConfig
    validation: ConfigValidationResult
    preview: CommandPreview | None = None
    command: ExecutionCommand | None = None


@dataclass(frozen=True)
class DryRunHistoryEntry:
    mode: str
    session_status: str
    job_status: str
    run_status: str
    db_delta: int
    target: str
    reason: str | None = None


def example_dry_run_config() -> ConsoleDryRunConfig:
    return ConsoleDryRunConfig(
        account_id="示例-account",
        trading_day="2026-06-12",
        instrument_id="示例-au2608",
        trade_instrument_id="示例-au2608",
        symbol="示例-au",
        exchange="示例-SHFE",
        quantity="1",
        price="500",
        max_order_size="1",
        max_position_size="1",
        max_daily_loss="1000",
        allowed_instruments=("示例-au2608",),
        is_example=True,
    )


def assemble_config(config: ConsoleDryRunConfig) -> ConfigAssemblyResult:
    validation = validate_config(config)
    if validation.blocked:
        return ConfigAssemblyResult(config=config, validation=validation)
    command = build_preview_command(config)
    return ConfigAssemblyResult(
        config=config,
        validation=validation,
        preview=build_command_preview(config),
        command=command,
    )


def validate_config(config: ConsoleDryRunConfig) -> ConfigValidationResult:
    missing = _missing_fields(config)
    if missing:
        return ConfigValidationResult(
            blocked=True,
            reason=_missing_reason(missing),
            missing_fields=missing,
        )
    if config.apply_requested:
        return ConfigValidationResult(
            blocked=True,
            reason="配置中心不允许请求 apply",
            missing_fields=("apply_requested",),
        )
    if config.target != MOCK_TARGET:
        return ConfigValidationResult(
            blocked=True,
            reason="配置中心只允许 MOCK 目标",
            missing_fields=("target",),
        )
    quantity = _decimal_or_none(config.quantity)
    if quantity is None or quantity <= 0:
        return ConfigValidationResult(
            blocked=True,
            reason="数量必须大于 0",
            missing_fields=("quantity",),
        )
    price = _decimal_or_none(config.price)
    if price is None or price <= 0:
        return ConfigValidationResult(
            blocked=True,
            reason="价格必须大于 0",
            missing_fields=("price",),
        )
    try:
        date.fromisoformat(config.trading_day.strip())
    except ValueError:
        return ConfigValidationResult(
            blocked=True,
            reason="交易日格式必须是 YYYY-MM-DD",
            missing_fields=("trading_day",),
        )
    allowed = tuple(item.strip() for item in config.allowed_instruments if item.strip())
    if config.instrument_id.strip() not in allowed:
        return ConfigValidationResult(
            blocked=True,
            reason="合约不在允许列表中",
            missing_fields=("allowed instruments",),
        )
    return ConfigValidationResult(blocked=False)


def build_command_preview(config: ConsoleDryRunConfig) -> CommandPreview:
    return CommandPreview(
        account_id=config.account_id.strip(),
        trading_day=config.trading_day.strip(),
        instrument_id=config.instrument_id.strip(),
        trade_instrument_id=config.trade_instrument_id.strip(),
        symbol=config.symbol.strip(),
        exchange=config.exchange.strip(),
        direction=READ_ONLY_DIRECTION.value,
        offset=READ_ONLY_OFFSET.value,
        quantity=str(_required_decimal(config.quantity)),
        price=str(_required_decimal(config.price)),
        target=MOCK_TARGET,
        dry_run="是",
        db_write="否",
    )


def build_preview_command(config: ConsoleDryRunConfig) -> ExecutionCommand:
    quantity = _required_decimal(config.quantity)
    price = _required_decimal(config.price)
    trading_day = date.fromisoformat(config.trading_day.strip())
    payload = "|".join(
        (
            config.account_id.strip(),
            trading_day.isoformat(),
            config.instrument_id.strip(),
            config.trade_instrument_id.strip(),
            config.symbol.strip(),
            config.exchange.strip(),
            str(quantity),
            str(price),
            ExecutionTarget.MOCK.value,
        )
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()
    return ExecutionCommand(
        command_id=f"console-dry-run-{digest[:16]}",
        order_id=f"console-preview-order-{digest[:16]}",
        client_order_id=f"console-preview-client-{digest[:16]}",
        account_id=config.account_id.strip(),
        symbol=config.symbol.strip(),
        instrument_id=config.instrument_id.strip(),
        trade_instrument_id=config.trade_instrument_id.strip(),
        exchange=config.exchange.strip(),
        side=READ_ONLY_DIRECTION,
        offset=READ_ONLY_OFFSET,
        quantity=quantity,
        price=price,
        order_type=OrderType.LIMIT,
        tif="GFD",
        command_type=ExecutionCommandType.SUBMIT_ORDER,
        execution_target=ExecutionTarget.MOCK,
        command_payload_hash=digest,
        created_at=datetime(1970, 1, 1, tzinfo=UTC),
    )


def blocked_config_result(reason: str, missing_fields: tuple[str, ...] = ()) -> DryRunActionResult:
    suffix = ""
    if missing_fields:
        suffix = f"：{', '.join(missing_fields)}"
    return DryRunActionResult(
        session_status="BLOCKED",
        job_status="BLOCKED",
        run_status="BLOCKED",
        db_delta=0,
        target=MOCK_TARGET,
        reason=f"{reason}{suffix}",
    )


def append_history(
    history: tuple[DryRunHistoryEntry, ...],
    *,
    mode: str,
    result: DryRunActionResult,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> tuple[DryRunHistoryEntry, ...]:
    next_history = (
        DryRunHistoryEntry(
            mode=mode,
            session_status=result.session_status,
            job_status=result.job_status,
            run_status=result.run_status,
            db_delta=result.db_delta,
            target=result.target,
            reason=result.reason,
        ),
        *history,
    )
    return next_history[:limit]


def parse_allowed_instruments(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def format_allowed_instruments(value: tuple[str, ...]) -> str:
    return ", ".join(value)


def _missing_fields(config: ConsoleDryRunConfig) -> tuple[str, ...]:
    missing: list[str] = []
    for field_name in (
        "account_id",
        "trading_day",
        "instrument_id",
        "trade_instrument_id",
    ):
        if not getattr(config, field_name).strip():
            missing.append(field_name)
    return tuple(missing)


def _missing_reason(missing: tuple[str, ...]) -> str:
    return "缺少必填配置"


def _decimal_or_none(value: str) -> Decimal | None:
    try:
        return Decimal(value.strip())
    except (InvalidOperation, ValueError):
        return None


def _required_decimal(value: str) -> Decimal:
    result = _decimal_or_none(value)
    if result is None:
        raise ValueError("invalid decimal")
    return result
