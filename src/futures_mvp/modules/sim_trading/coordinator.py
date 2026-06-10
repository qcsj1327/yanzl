from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from futures_mvp.domain.enums import (
    ExecutionReportNormalizeResultStatus,
    ExecutionReportStatus,
    ExecutionTarget,
    MarginResultStatus,
    Offset,
    OMSEventApplyResultStatus,
    PnLPriceBasis,
    PnLResultStatus,
    PositionManagerResultStatus,
    SettlementResultStatus,
    TradeBridgeResultStatus,
)
from futures_mvp.domain.models import (
    AccountContext,
    ExecutionCommand,
    ExecutionCommandResult,
    ExecutionReportNormalizeResult,
    MarginResult,
    MarginRule,
    MarginSnapshot,
    NormalizedExecutionReport,
    OMSEventApplyContext,
    OMSEventApplyResult,
    OrderEvent,
    OrderEventCandidate,
    OrderState,
    PnLResult,
    PnLSnapshot,
    Position,
    PositionManagerResult,
    RawExecutionReport,
    SettlementContext,
    SettlementResult,
    Trade,
    TradeBridgeContext,
    TradeBridgeResult,
    TradingCalendar,
)
from futures_mvp.modules.ops_safety import (
    CapitalControlContext,
    CapitalControlDecision,
    MigrationReadinessReport,
    OperatorApproval,
    RolloutMode,
    SafetyConfig,
    evaluate_capital_controls,
)
from futures_mvp.modules.ops_safety.kill_switch import (
    evaluate_replay_gate,
    evaluate_scheduler_gate,
)
from futures_mvp.modules.sim_trading.harness import (
    SimExecutionHarness,
    SimExecutionResult,
)


class SimRunStatus(StrEnum):
    CREATED = "CREATED"
    APPLIED = "APPLIED"
    COMPLETED = "COMPLETED"
    REJECTED_SAFETY_GATE = "REJECTED_SAFETY_GATE"
    REJECTED_NON_SIM_MODE = "REJECTED_NON_SIM_MODE"
    REJECTED_CAPITAL_CONTROL = "REJECTED_CAPITAL_CONTROL"
    REJECTED_UNSUPPORTED_TARGET = "REJECTED_UNSUPPORTED_TARGET"
    REJECTED_NO_REPORT = "REJECTED_NO_REPORT"
    DUPLICATE = "DUPLICATE"
    CONFLICT = "CONFLICT"
    ERROR = "ERROR"


class _Harness(Protocol):
    def execute(self, command: ExecutionCommand) -> SimExecutionResult: ...


class _ExecutionReportNormalizer(Protocol):
    def normalize(self, raw_report: RawExecutionReport) -> ExecutionReportNormalizeResult: ...


class _OMSEventApplication(Protocol):
    def apply_candidate(self, context: OMSEventApplyContext) -> OMSEventApplyResult: ...


class _OMSToTradeBridge(Protocol):
    def create_trade(self, context: TradeBridgeContext) -> TradeBridgeResult: ...


class _PositionManager(Protocol):
    def apply_trade(self, trade: Trade) -> PositionManagerResult: ...


class _MarginEngine(Protocol):
    def calculate_margin(
        self,
        position: Position,
        rule: MarginRule | None,
        account: AccountContext,
        *,
        calculation_key: str,
        calculated_at: datetime,
        trading_day: date | None = None,
        config_hash: str | None = None,
        latest_price: Decimal | None = None,
        settlement_price: Decimal | None = None,
    ) -> MarginResult: ...


class _PnLEngine(Protocol):
    def calculate_pnl(
        self,
        position: object,
        *,
        price_basis: PnLPriceBasis,
        mark_price: Decimal | None,
        contract_multiplier: Decimal | None,
        calculation_key: str,
        calculated_at: datetime,
        trading_day: date | None = None,
        config_hash: str | None = None,
        trade: Trade | None = None,
        close_context: object | None = None,
        margin_snapshot_id: str | None = None,
    ) -> PnLResult: ...


class _SettlementEngine(Protocol):
    def settle(
        self,
        context: object,
        *,
        calendar: TradingCalendar | None = None,
    ) -> SettlementResult: ...


@dataclass(frozen=True)
class SimAccountingContext:
    account: AccountContext
    margin_rule: MarginRule | None = None
    latest_price: Decimal | None = None
    settlement_price: Decimal | None = None
    pnl_price_basis: PnLPriceBasis = PnLPriceBasis.LAST_PRICE
    mark_price: Decimal | None = None
    contract_multiplier: Decimal | None = None
    calculated_at: datetime | None = None
    settlement_context: object | None = None
    settlement_calendar: TradingCalendar | None = None


@dataclass(frozen=True)
class SimRunContext:
    rollout_mode: RolloutMode
    safety_config: SafetyConfig
    migration: MigrationReadinessReport
    capital_control_context: CapitalControlContext
    account_id: str
    trading_day: date
    config_hash: str
    command: ExecutionCommand
    current_order_state: OrderState
    symbol: str
    trade_instrument_id: str
    runtime_ready: bool
    operator_approval: OperatorApproval | None = None
    unresolved_critical_incidents: tuple[str, ...] = ()
    apply_oms_events: bool = True
    accounting: SimAccountingContext | None = None


@dataclass(frozen=True)
class SimRunResult:
    status: SimRunStatus
    reason: str | None = None
    command_result: ExecutionCommandResult | None = None
    raw_reports: tuple[RawExecutionReport, ...] = ()
    normalized_reports: tuple[NormalizedExecutionReport, ...] = ()
    order_event_candidates: tuple[OrderEventCandidate, ...] = ()
    oms_results: tuple[OMSEventApplyResult, ...] = ()
    applied_order_events: tuple[OrderEvent, ...] = ()
    trade_results: tuple[TradeBridgeResult, ...] = ()
    trades: tuple[Trade, ...] = ()
    position_results: tuple[PositionManagerResult, ...] = ()
    margin_results: tuple[MarginResult, ...] = ()
    pnl_results: tuple[PnLResult, ...] = ()
    settlement_results: tuple[SettlementResult, ...] = ()
    capital_control_decision: CapitalControlDecision | None = None
    duplicate: bool = False
    conflict: bool = False
    dry_run: bool = False
    applied: bool = False


class SimTradingCoordinator:
    def __init__(
        self,
        *,
        normalizer: _ExecutionReportNormalizer,
        oms_event_application: _OMSEventApplication,
        oms_to_trade: _OMSToTradeBridge,
        position_manager: _PositionManager,
        harness: _Harness | None = None,
        margin_engine: _MarginEngine | None = None,
        pnl_engine: _PnLEngine | None = None,
        settlement_engine: _SettlementEngine | None = None,
    ) -> None:
        self._harness = harness or SimExecutionHarness()
        self._normalizer = normalizer
        self._oms_event_application = oms_event_application
        self._oms_to_trade = oms_to_trade
        self._position_manager = position_manager
        self._margin_engine = margin_engine
        self._pnl_engine = pnl_engine
        self._settlement_engine = settlement_engine

    def run(self, context: SimRunContext) -> SimRunResult:
        preflight = _preflight(context)
        if preflight is not None:
            return preflight

        harness_result = self._harness.execute(context.command)
        if not harness_result.raw_reports:
            return SimRunResult(
                status=SimRunStatus.REJECTED_NO_REPORT,
                reason=harness_result.reason or "sim execution produced no report",
                command_result=harness_result.command_result,
                dry_run=not context.apply_oms_events,
            )

        state = _RunState(
            context=context,
            command_result=harness_result.command_result,
            raw_reports=list(harness_result.raw_reports),
            current_order_state=context.current_order_state,
            dry_run=not context.apply_oms_events,
        )
        for raw_report in harness_result.raw_reports:
            stop = self._apply_report(raw_report, state)
            if stop is not None:
                return stop
        return state.result()

    def _apply_report(
        self,
        raw_report: RawExecutionReport,
        state: _RunState,
    ) -> SimRunResult | None:
        normalized = self._normalizer.normalize(raw_report)
        if normalized.normalized_report is not None:
            state.normalized_reports.append(normalized.normalized_report)

        if normalized.status is ExecutionReportNormalizeResultStatus.DUPLICATE:
            state.duplicate = True
            return None
        if normalized.status is ExecutionReportNormalizeResultStatus.CONFLICT:
            return state.result(
                status=SimRunStatus.CONFLICT,
                reason=normalized.reason,
                conflict=True,
            )
        if normalized.status is not ExecutionReportNormalizeResultStatus.NORMALIZED:
            return state.result(
                status=SimRunStatus.ERROR,
                reason=normalized.reason or normalized.status.value,
            )
        if normalized.order_event_candidate is None:
            return None

        state.order_event_candidates.append(normalized.order_event_candidate)
        oms_result = self._oms_event_application.apply_candidate(
            OMSEventApplyContext(
                order_event_candidate=normalized.order_event_candidate,
                current_order_state=state.current_order_state,
                allow_live_apply=state.context.apply_oms_events,
                source="sim_trading",
            )
        )
        state.oms_results.append(oms_result)
        if oms_result.status is OMSEventApplyResultStatus.DRY_RUN:
            return None
        if oms_result.status is OMSEventApplyResultStatus.DUPLICATE:
            state.duplicate = True
            return state.result(status=SimRunStatus.DUPLICATE)
        if oms_result.status is OMSEventApplyResultStatus.APPLIED:
            if oms_result.order_event is not None:
                state.applied_order_events.append(oms_result.order_event)
            if oms_result.order_state is not None:
                state.current_order_state = oms_result.order_state
        elif oms_result.status in {
            OMSEventApplyResultStatus.NO_OP,
            OMSEventApplyResultStatus.REJECTED_NO_EVENT,
        }:
            return None
        elif oms_result.status is OMSEventApplyResultStatus.CONFLICT:
            return state.result(
                status=SimRunStatus.CONFLICT,
                reason=oms_result.reason,
                conflict=True,
            )
        else:
            return state.result(
                status=SimRunStatus.ERROR,
                reason=oms_result.reason or oms_result.status.value,
            )

        report = normalized.normalized_report
        if report is None or report.execution_status is not ExecutionReportStatus.FILLED:
            return None
        if oms_result.order_event is None:
            return state.result(
                status=SimRunStatus.ERROR,
                reason="applied OMS event proof is required for sim trade creation",
            )
        return self._apply_trade(report, oms_result.order_event, state)

    def _apply_trade(
        self,
        report: NormalizedExecutionReport,
        applied_event: OrderEvent,
        state: _RunState,
    ) -> SimRunResult | None:
        bridge_result = self._oms_to_trade.create_trade(
            TradeBridgeContext(
                normalized_report=report,
                order_state=state.current_order_state,
                symbol=state.context.symbol,
                trade_instrument_id=state.context.trade_instrument_id,
                applied_order_event=applied_event,
                source_order_event_id=applied_event.external_event_id,
                trading_day=state.context.trading_day,
            )
        )
        state.trade_results.append(bridge_result)
        if bridge_result.status is TradeBridgeResultStatus.CONFLICT:
            return state.result(
                status=SimRunStatus.CONFLICT,
                reason=bridge_result.reason,
                conflict=True,
            )
        if bridge_result.status is TradeBridgeResultStatus.ERROR:
            return state.result(status=SimRunStatus.ERROR, reason=bridge_result.reason)
        if bridge_result.status is TradeBridgeResultStatus.DUPLICATE:
            state.duplicate = True
            return state.result(status=SimRunStatus.DUPLICATE)
        if bridge_result.trade is None:
            return state.result(
                status=SimRunStatus.ERROR,
                reason=bridge_result.reason or bridge_result.status.value,
            )

        state.trades.append(bridge_result.trade)
        position_result = self._position_manager.apply_trade(bridge_result.trade)
        state.position_results.append(position_result)
        if position_result.status is PositionManagerResultStatus.CONFLICT:
            return state.result(
                status=SimRunStatus.CONFLICT,
                reason=position_result.reason,
                conflict=True,
            )
        if position_result.status is PositionManagerResultStatus.ERROR:
            return state.result(status=SimRunStatus.ERROR, reason=position_result.reason)
        if position_result.status is PositionManagerResultStatus.DUPLICATE_IGNORED:
            state.duplicate = True
        if position_result.position is not None:
            return self._apply_accounting(
                bridge_result.trade,
                position_result.position,
                state,
            )
        return None

    def _apply_accounting(
        self,
        trade: Trade,
        position: Position,
        state: _RunState,
    ) -> SimRunResult | None:
        accounting = state.context.accounting
        if accounting is None:
            return None
        calculated_at = accounting.calculated_at or trade.trade_time
        margin_snapshot_id = None
        if self._margin_engine is not None:
            margin_result = self._margin_engine.calculate_margin(
                position,
                accounting.margin_rule,
                accounting.account,
                calculation_key=_calculation_key("sim_margin", state.context, trade),
                calculated_at=calculated_at,
                trading_day=state.context.trading_day,
                config_hash=state.context.config_hash,
                latest_price=accounting.latest_price,
                settlement_price=accounting.settlement_price,
            )
            state.margin_results.append(margin_result)
            if margin_result.status is MarginResultStatus.CONFLICT:
                return state.result(
                    status=SimRunStatus.CONFLICT,
                    reason=margin_result.reason,
                    conflict=True,
                )
            if margin_result.status is MarginResultStatus.ERROR:
                return state.result(status=SimRunStatus.ERROR, reason=margin_result.reason)
            if margin_result.snapshot is not None:
                margin_snapshot_id = margin_result.snapshot.id

        if self._pnl_engine is not None:
            pnl_result = self._pnl_engine.calculate_pnl(
                position,
                price_basis=accounting.pnl_price_basis,
                mark_price=accounting.mark_price,
                contract_multiplier=accounting.contract_multiplier,
                calculation_key=_calculation_key("sim_pnl", state.context, trade),
                calculated_at=calculated_at,
                trading_day=state.context.trading_day,
                config_hash=state.context.config_hash,
                trade=trade if trade.offset is not Offset.OPEN else None,
                close_context=None,
                margin_snapshot_id=margin_snapshot_id,
            )
            state.pnl_results.append(pnl_result)
            if pnl_result.status is PnLResultStatus.CONFLICT:
                return state.result(
                    status=SimRunStatus.CONFLICT,
                    reason=pnl_result.reason,
                    conflict=True,
                )
            if pnl_result.status is PnLResultStatus.ERROR:
                return state.result(status=SimRunStatus.ERROR, reason=pnl_result.reason)

        if self._settlement_engine is not None and accounting.settlement_context is not None:
            settlement_context = _sim_settlement_context(
                accounting.settlement_context,
                position=position,
                margin_results=state.margin_results,
                pnl_results=state.pnl_results,
            )
            settlement_result = self._settlement_engine.settle(
                settlement_context,
                calendar=accounting.settlement_calendar,
            )
            state.settlement_results.append(settlement_result)
            if settlement_result.status is SettlementResultStatus.CONFLICT:
                return state.result(
                    status=SimRunStatus.CONFLICT,
                    reason=settlement_result.reason,
                    conflict=True,
                )
            if settlement_result.status is SettlementResultStatus.ERROR:
                return state.result(
                    status=SimRunStatus.ERROR,
                    reason=settlement_result.reason,
                )
        return None


@dataclass
class _RunState:
    context: SimRunContext
    command_result: ExecutionCommandResult
    raw_reports: list[RawExecutionReport]
    current_order_state: OrderState
    normalized_reports: list[NormalizedExecutionReport] = field(default_factory=list)
    order_event_candidates: list[OrderEventCandidate] = field(default_factory=list)
    oms_results: list[OMSEventApplyResult] = field(default_factory=list)
    applied_order_events: list[OrderEvent] = field(default_factory=list)
    trade_results: list[TradeBridgeResult] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    position_results: list[PositionManagerResult] = field(default_factory=list)
    margin_results: list[MarginResult] = field(default_factory=list)
    pnl_results: list[PnLResult] = field(default_factory=list)
    settlement_results: list[SettlementResult] = field(default_factory=list)
    duplicate: bool = False
    dry_run: bool = False

    def result(
        self,
        *,
        status: SimRunStatus | None = None,
        reason: str | None = None,
        conflict: bool = False,
    ) -> SimRunResult:
        if status is None:
            if self.duplicate and not self.trades and not self.applied_order_events:
                status = SimRunStatus.DUPLICATE
            elif self.trades and self.position_results:
                status = SimRunStatus.COMPLETED
            elif self.applied_order_events:
                status = SimRunStatus.APPLIED
            else:
                status = SimRunStatus.CREATED
        return SimRunResult(
            status=status,
            reason=reason,
            command_result=self.command_result,
            raw_reports=tuple(self.raw_reports),
            normalized_reports=tuple(self.normalized_reports),
            order_event_candidates=tuple(self.order_event_candidates),
            oms_results=tuple(self.oms_results),
            applied_order_events=tuple(self.applied_order_events),
            trade_results=tuple(self.trade_results),
            trades=tuple(self.trades),
            position_results=tuple(self.position_results),
            margin_results=tuple(self.margin_results),
            pnl_results=tuple(self.pnl_results),
            settlement_results=tuple(self.settlement_results),
            duplicate=self.duplicate,
            conflict=conflict,
            dry_run=self.dry_run,
            applied=bool(self.applied_order_events),
        )


def _preflight(context: SimRunContext) -> SimRunResult | None:
    if context.rollout_mode is not RolloutMode.SIM:
        return SimRunResult(
            status=SimRunStatus.REJECTED_NON_SIM_MODE,
            reason="sim run requires RolloutMode.SIM",
        )
    if context.safety_config.rollout.mode is not RolloutMode.SIM:
        return SimRunResult(
            status=SimRunStatus.REJECTED_NON_SIM_MODE,
            reason="SafetyConfig rollout mode must be SIM",
        )
    if context.command.execution_target is not ExecutionTarget.MOCK:
        return SimRunResult(
            status=SimRunStatus.REJECTED_UNSUPPORTED_TARGET,
            reason="sim run supports ExecutionTarget.MOCK only",
        )
    if context.operator_approval is None:
        return SimRunResult(
            status=SimRunStatus.REJECTED_SAFETY_GATE,
            reason="operator approval is required",
        )
    if not context.runtime_ready:
        return SimRunResult(
            status=SimRunStatus.REJECTED_SAFETY_GATE,
            reason="runtime is not READY",
        )
    if not context.migration.compatible:
        return SimRunResult(
            status=SimRunStatus.REJECTED_SAFETY_GATE,
            reason=context.migration.reason or "migration readiness is incompatible",
        )
    if _has_live_gate_enabled(context.safety_config):
        return SimRunResult(
            status=SimRunStatus.REJECTED_SAFETY_GATE,
            reason="SIM E2E forbids live credentials and live apply",
        )
    if context.unresolved_critical_incidents:
        return SimRunResult(
            status=SimRunStatus.REJECTED_SAFETY_GATE,
            reason="unresolved critical incidents are present",
        )
    scheduler_gate = evaluate_scheduler_gate(context.safety_config)
    if not scheduler_gate.allowed:
        return SimRunResult(
            status=SimRunStatus.REJECTED_SAFETY_GATE,
            reason=scheduler_gate.reason,
        )
    replay_gate = evaluate_replay_gate(context.safety_config)
    if not replay_gate.allowed:
        return SimRunResult(
            status=SimRunStatus.REJECTED_SAFETY_GATE,
            reason=replay_gate.reason,
        )
    capital_decision = evaluate_capital_controls(
        context.safety_config,
        context.capital_control_context,
    )
    if not capital_decision.passed:
        return SimRunResult(
            status=SimRunStatus.REJECTED_CAPITAL_CONTROL,
            reason=capital_decision.reason,
            capital_control_decision=capital_decision,
        )
    return None


def _has_live_gate_enabled(config: SafetyConfig) -> bool:
    return (
        config.live_gate.broker_enabled
        or config.live_gate.live_submit_enabled
        or config.live_gate.explicit_live_flag
        or config.live_gate.broker_credentials_handle is not None
    )


def _calculation_key(prefix: str, context: SimRunContext, trade: Trade) -> str:
    return f"{prefix}:{context.config_hash}:{trade.exchange_trade_id}"


def _sim_settlement_context(
    context: object,
    *,
    position: Position,
    margin_results: list[MarginResult],
    pnl_results: list[PnLResult],
) -> object:
    if not isinstance(context, SettlementContext):
        return context
    margin_snapshot = _latest_margin_snapshot(margin_results)
    pnl_snapshot = _latest_pnl_snapshot(pnl_results)
    if margin_snapshot is None or pnl_snapshot is None:
        return context
    settlement_position = position.model_copy(
        update={
            "margin_used": margin_snapshot.margin_used,
            "realized_pnl": pnl_snapshot.realized_pnl,
            "unrealized_pnl": pnl_snapshot.unrealized_pnl,
        }
    )
    return context.model_copy(
        update={
            "positions": (settlement_position,),
            "margin_snapshots": (margin_snapshot,),
            "pnl_snapshots": (pnl_snapshot,),
        }
    )


def _latest_margin_snapshot(results: list[MarginResult]) -> MarginSnapshot | None:
    for result in reversed(results):
        if result.snapshot is not None:
            return result.snapshot
    return None


def _latest_pnl_snapshot(results: list[PnLResult]) -> PnLSnapshot | None:
    for result in reversed(results):
        if result.snapshot is not None:
            return result.snapshot
    return None
