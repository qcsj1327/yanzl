from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from futures_mvp.domain.enums import (
    ExecutionReportNormalizeResultStatus,
    ExecutionReportStatus,
    MarginResultStatus,
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
    NormalizedExecutionReport,
    OMSEventApplyContext,
    OMSEventApplyResult,
    OrderEvent,
    OrderEventCandidate,
    OrderState,
    PnLResult,
    PositionManagerResult,
    RawExecutionReport,
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
from futures_mvp.modules.paper_trading.harness import (
    PaperExecutionHarness,
    PaperExecutionResult,
)


class PaperRunStatus(StrEnum):
    CREATED = "CREATED"
    APPLIED = "APPLIED"
    COMPLETED = "COMPLETED"
    REJECTED_SAFETY_GATE = "REJECTED_SAFETY_GATE"
    REJECTED_NON_PAPER_MODE = "REJECTED_NON_PAPER_MODE"
    REJECTED_CAPITAL_CONTROL = "REJECTED_CAPITAL_CONTROL"
    REJECTED_NO_REPORT = "REJECTED_NO_REPORT"
    DUPLICATE = "DUPLICATE"
    CONFLICT = "CONFLICT"
    ERROR = "ERROR"


class _Harness(Protocol):
    def execute(self, command: ExecutionCommand) -> PaperExecutionResult: ...


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
        position: object,
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
class PaperAccountingContext:
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
class PaperRunContext:
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
    operator_approval: OperatorApproval | None = None
    apply_oms_events: bool = True
    accounting: PaperAccountingContext | None = None


@dataclass(frozen=True)
class PaperRunResult:
    status: PaperRunStatus
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


class PaperTradingCoordinator:
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
        self._harness = harness or PaperExecutionHarness()
        self._normalizer = normalizer
        self._oms_event_application = oms_event_application
        self._oms_to_trade = oms_to_trade
        self._position_manager = position_manager
        self._margin_engine = margin_engine
        self._pnl_engine = pnl_engine
        self._settlement_engine = settlement_engine

    def run(self, context: PaperRunContext) -> PaperRunResult:
        preflight = _preflight(context)
        if preflight is not None:
            return preflight

        harness_result = self._harness.execute(context.command)
        if not harness_result.raw_reports:
            return PaperRunResult(
                status=PaperRunStatus.REJECTED_NO_REPORT,
                reason=harness_result.reason or "paper execution produced no report",
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
    ) -> PaperRunResult | None:
        normalized = self._normalizer.normalize(raw_report)
        if normalized.normalized_report is not None:
            state.normalized_reports.append(normalized.normalized_report)

        if normalized.status is ExecutionReportNormalizeResultStatus.DUPLICATE:
            state.duplicate = True
            return None
        if normalized.status is ExecutionReportNormalizeResultStatus.CONFLICT:
            return state.result(
                status=PaperRunStatus.CONFLICT,
                reason=normalized.reason,
                conflict=True,
            )
        if normalized.status is not ExecutionReportNormalizeResultStatus.NORMALIZED:
            return state.result(
                status=PaperRunStatus.ERROR,
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
                source="paper_trading",
            )
        )
        state.oms_results.append(oms_result)
        if oms_result.status is OMSEventApplyResultStatus.DRY_RUN:
            return None
        if oms_result.status is OMSEventApplyResultStatus.DUPLICATE:
            state.duplicate = True
            return state.result(status=PaperRunStatus.DUPLICATE)
        elif oms_result.status is OMSEventApplyResultStatus.APPLIED:
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
                status=PaperRunStatus.CONFLICT,
                reason=oms_result.reason,
                conflict=True,
            )
        else:
            return state.result(
                status=PaperRunStatus.ERROR,
                reason=oms_result.reason or oms_result.status.value,
            )

        report = normalized.normalized_report
        if report is None or report.execution_status not in {
            ExecutionReportStatus.PARTIALLY_FILLED,
            ExecutionReportStatus.FILLED,
        }:
            return None
        if oms_result.order_event is None:
            return state.result(
                status=PaperRunStatus.ERROR,
                reason="applied OMS event proof is required for paper trade creation",
            )

        trade_stop = self._apply_trade(report, oms_result.order_event, state)
        if trade_stop is not None:
            return trade_stop
        return None

    def _apply_trade(
        self,
        report: NormalizedExecutionReport,
        applied_event: OrderEvent,
        state: _RunState,
    ) -> PaperRunResult | None:
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
                status=PaperRunStatus.CONFLICT,
                reason=bridge_result.reason,
                conflict=True,
            )
        if bridge_result.status is TradeBridgeResultStatus.ERROR:
            return state.result(status=PaperRunStatus.ERROR, reason=bridge_result.reason)
        if bridge_result.status is TradeBridgeResultStatus.DUPLICATE:
            state.duplicate = True
            return state.result(status=PaperRunStatus.DUPLICATE)
        if bridge_result.trade is None:
            return state.result(
                status=PaperRunStatus.ERROR,
                reason=bridge_result.reason or bridge_result.status.value,
            )

        state.trades.append(bridge_result.trade)
        position_result = self._position_manager.apply_trade(bridge_result.trade)
        state.position_results.append(position_result)
        if position_result.status is PositionManagerResultStatus.CONFLICT:
            return state.result(
                status=PaperRunStatus.CONFLICT,
                reason=position_result.reason,
                conflict=True,
            )
        if position_result.status is PositionManagerResultStatus.ERROR:
            return state.result(status=PaperRunStatus.ERROR, reason=position_result.reason)
        if position_result.status is PositionManagerResultStatus.DUPLICATE_IGNORED:
            state.duplicate = True
        if position_result.position is not None:
            accounting_stop = self._apply_accounting(
                bridge_result.trade,
                position_result.position,
                state,
            )
            if accounting_stop is not None:
                return accounting_stop
        return None

    def _apply_accounting(
        self,
        trade: Trade,
        position: object,
        state: _RunState,
    ) -> PaperRunResult | None:
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
                calculation_key=_calculation_key("paper_margin", state.context, trade),
                calculated_at=calculated_at,
                trading_day=state.context.trading_day,
                config_hash=state.context.config_hash,
                latest_price=accounting.latest_price,
                settlement_price=accounting.settlement_price,
            )
            state.margin_results.append(margin_result)
            if margin_result.status is MarginResultStatus.CONFLICT:
                return state.result(
                    status=PaperRunStatus.CONFLICT,
                    reason=margin_result.reason,
                    conflict=True,
                )
            if margin_result.status is MarginResultStatus.ERROR:
                return state.result(status=PaperRunStatus.ERROR, reason=margin_result.reason)
            if margin_result.snapshot is not None:
                margin_snapshot_id = margin_result.snapshot.id

        if self._pnl_engine is not None:
            pnl_result = self._pnl_engine.calculate_pnl(
                position,
                price_basis=accounting.pnl_price_basis,
                mark_price=accounting.mark_price,
                contract_multiplier=accounting.contract_multiplier,
                calculation_key=_calculation_key("paper_pnl", state.context, trade),
                calculated_at=calculated_at,
                trading_day=state.context.trading_day,
                config_hash=state.context.config_hash,
                trade=trade,
                close_context=None,
                margin_snapshot_id=margin_snapshot_id,
            )
            state.pnl_results.append(pnl_result)
            if pnl_result.status is PnLResultStatus.CONFLICT:
                return state.result(
                    status=PaperRunStatus.CONFLICT,
                    reason=pnl_result.reason,
                    conflict=True,
                )
            if pnl_result.status is PnLResultStatus.ERROR:
                return state.result(status=PaperRunStatus.ERROR, reason=pnl_result.reason)

        if self._settlement_engine is not None and accounting.settlement_context is not None:
            settlement_result = self._settlement_engine.settle(
                accounting.settlement_context,
                calendar=accounting.settlement_calendar,
            )
            state.settlement_results.append(settlement_result)
            if settlement_result.status is SettlementResultStatus.CONFLICT:
                return state.result(
                    status=PaperRunStatus.CONFLICT,
                    reason=settlement_result.reason,
                    conflict=True,
                )
            if settlement_result.status is SettlementResultStatus.ERROR:
                return state.result(
                    status=PaperRunStatus.ERROR,
                    reason=settlement_result.reason,
                )
        return None


@dataclass
class _RunState:
    context: PaperRunContext
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
        status: PaperRunStatus | None = None,
        reason: str | None = None,
        conflict: bool = False,
    ) -> PaperRunResult:
        if status is None:
            if self.duplicate and not self.trades and not self.applied_order_events:
                status = PaperRunStatus.DUPLICATE
            elif self.trades and self.position_results:
                status = PaperRunStatus.COMPLETED
            elif self.applied_order_events:
                status = PaperRunStatus.APPLIED
            else:
                status = PaperRunStatus.CREATED
        return PaperRunResult(
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


def _preflight(context: PaperRunContext) -> PaperRunResult | None:
    if context.rollout_mode is not RolloutMode.PAPER:
        return PaperRunResult(
            status=PaperRunStatus.REJECTED_NON_PAPER_MODE,
            reason="paper run requires RolloutMode.PAPER",
        )
    if context.safety_config.rollout.mode is not RolloutMode.PAPER:
        return PaperRunResult(
            status=PaperRunStatus.REJECTED_NON_PAPER_MODE,
            reason="SafetyConfig rollout mode must be PAPER",
        )
    if not context.migration.compatible:
        return PaperRunResult(
            status=PaperRunStatus.REJECTED_SAFETY_GATE,
            reason=context.migration.reason or "migration readiness is incompatible",
        )
    scheduler_gate = evaluate_scheduler_gate(context.safety_config)
    if not scheduler_gate.allowed:
        return PaperRunResult(
            status=PaperRunStatus.REJECTED_SAFETY_GATE,
            reason=scheduler_gate.reason,
        )
    replay_gate = evaluate_replay_gate(context.safety_config)
    if not replay_gate.allowed:
        return PaperRunResult(
            status=PaperRunStatus.REJECTED_SAFETY_GATE,
            reason=replay_gate.reason,
        )
    capital_decision = evaluate_capital_controls(
        context.safety_config,
        context.capital_control_context,
    )
    if not capital_decision.passed:
        return PaperRunResult(
            status=PaperRunStatus.REJECTED_CAPITAL_CONTROL,
            reason=capital_decision.reason,
            capital_control_decision=capital_decision,
        )
    return None


def _calculation_key(prefix: str, context: PaperRunContext, trade: Trade) -> str:
    return f"{prefix}:{context.config_hash}:{trade.exchange_trade_id}"
