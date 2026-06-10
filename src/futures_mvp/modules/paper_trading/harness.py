from dataclasses import dataclass
from enum import StrEnum

from futures_mvp.domain.enums import ExecutionCommandResultStatus, ExecutionTarget
from futures_mvp.domain.models import ExecutionCommand, ExecutionCommandResult, RawExecutionReport
from futures_mvp.modules.broker_adapter import (
    BrokerCallbackTranslationResult,
    BrokerCallbackTranslationStatus,
    MockBrokerAdapter,
    MockBrokerSubmitMode,
    translate_callback_to_raw_execution_report,
)
from futures_mvp.modules.execution_gateway.protocols import ExecutionAdapter
from futures_mvp.modules.paper_trading.policy import PaperFillPolicy
from futures_mvp.modules.paper_trading.reports import build_paper_broker_callback_evidences


class PaperExecutionStatus(StrEnum):
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True)
class PaperExecutionResult:
    status: PaperExecutionStatus
    command_result: ExecutionCommandResult
    raw_reports: tuple[RawExecutionReport, ...] = ()
    translation_result: BrokerCallbackTranslationResult | None = None
    reason: str | None = None


class PaperExecutionHarness:
    """Local deterministic paper evidence generator for Stage P.1."""

    def __init__(
        self,
        *,
        fill_policy: PaperFillPolicy = PaperFillPolicy.IMMEDIATE_FULL_FILL,
        adapter: ExecutionAdapter | None = None,
    ) -> None:
        self._fill_policy = fill_policy
        self._adapter = adapter

    def execute(self, command: ExecutionCommand) -> PaperExecutionResult:
        if command.execution_target is not ExecutionTarget.MOCK:
            command_result = ExecutionCommandResult(
                command_id=command.command_id,
                order_id=command.order_id,
                status=ExecutionCommandResultStatus.REJECTED_BY_ADAPTER,
                reason=f"unsupported execution_target: {command.execution_target.value}",
            )
            return PaperExecutionResult(
                status=PaperExecutionStatus.REJECTED,
                command_result=command_result,
                reason="paper harness supports ExecutionTarget.MOCK only",
            )

        command_result = self._submit(command)
        if self._fill_policy is PaperFillPolicy.PRE_SEND_TIMEOUT:
            return PaperExecutionResult(
                status=PaperExecutionStatus.FAILED,
                command_result=command_result,
                reason="pre_send_timeout",
            )
        if self._fill_policy is PaperFillPolicy.POST_SEND_UNCERTAIN:
            return PaperExecutionResult(
                status=PaperExecutionStatus.UNCERTAIN,
                command_result=command_result,
                reason="post_send_uncertain",
            )
        if command_result.status is not ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER:
            return PaperExecutionResult(
                status=PaperExecutionStatus.FAILED,
                command_result=command_result,
                reason=command_result.reason,
            )
        if command_result.adapter_order_ref is None:
            return PaperExecutionResult(
                status=PaperExecutionStatus.FAILED,
                command_result=command_result,
                reason="adapter_order_ref is required",
            )

        evidences = build_paper_broker_callback_evidences(
            command,
            adapter_order_ref=command_result.adapter_order_ref,
            policy=self._fill_policy,
        )
        raw_reports: list[RawExecutionReport] = []
        translation_result = None
        for evidence in evidences:
            translated = translate_callback_to_raw_execution_report(evidence)
            translation_result = translated
            if translated.status is not BrokerCallbackTranslationStatus.TRANSLATED:
                return PaperExecutionResult(
                    status=PaperExecutionStatus.FAILED,
                    command_result=command_result,
                    translation_result=translated,
                    reason=translated.reason,
                )
            assert translated.raw_report is not None
            raw_reports.append(translated.raw_report)
        status = (
            PaperExecutionStatus.EXECUTED
            if self._fill_policy is PaperFillPolicy.IMMEDIATE_FULL_FILL
            else PaperExecutionStatus.REJECTED
        )
        return PaperExecutionResult(
            status=status,
            command_result=command_result,
            raw_reports=tuple(raw_reports),
            translation_result=translation_result,
        )

    def _submit(self, command: ExecutionCommand) -> ExecutionCommandResult:
        adapter = self._adapter or MockBrokerAdapter(
            submit_modes=[_submit_mode_for_policy(self._fill_policy)],
            clock=lambda: command.created_at,
        )
        return adapter.submit(command)


def _submit_mode_for_policy(policy: PaperFillPolicy) -> MockBrokerSubmitMode:
    if policy is PaperFillPolicy.PRE_SEND_TIMEOUT:
        return MockBrokerSubmitMode.PRE_SEND_TIMEOUT
    if policy is PaperFillPolicy.POST_SEND_UNCERTAIN:
        return MockBrokerSubmitMode.POST_SEND_UNCERTAIN
    return MockBrokerSubmitMode.ACCEPT
