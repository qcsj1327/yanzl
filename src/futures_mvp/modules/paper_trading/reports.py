from futures_mvp.domain.models import ExecutionCommand
from futures_mvp.modules.broker_adapter import BrokerCallbackEvidence
from futures_mvp.modules.execution_evidence import SharedExecutionEvidenceBuilder
from futures_mvp.modules.paper_trading.policy import PaperFillPolicy

_PAPER_EVIDENCE_BUILDER = SharedExecutionEvidenceBuilder(
    namespace="paper",
    adapter_name="paper_harness",
)


def build_paper_broker_callback_evidence(
    command: ExecutionCommand,
    *,
    adapter_order_ref: str,
    policy: PaperFillPolicy,
) -> BrokerCallbackEvidence:
    return build_paper_broker_callback_evidences(
        command,
        adapter_order_ref=adapter_order_ref,
        policy=policy,
    )[0]


def build_paper_broker_callback_evidences(
    command: ExecutionCommand,
    *,
    adapter_order_ref: str,
    policy: PaperFillPolicy,
) -> tuple[BrokerCallbackEvidence, ...]:
    if policy is PaperFillPolicy.IMMEDIATE_FULL_FILL:
        return (
            _acked_evidence(command, adapter_order_ref=adapter_order_ref),
            _filled_evidence(command, adapter_order_ref=adapter_order_ref),
        )
    if policy is PaperFillPolicy.IMMEDIATE_REJECT:
        return (_rejected_evidence(command, adapter_order_ref=adapter_order_ref),)
    raise ValueError(f"{policy.value} does not produce a paper execution report")


def _acked_evidence(
    command: ExecutionCommand,
    *,
    adapter_order_ref: str,
) -> BrokerCallbackEvidence:
    return _PAPER_EVIDENCE_BUILDER.build_acknowledged(
        command,
        adapter_order_ref=adapter_order_ref,
    )


def _filled_evidence(
    command: ExecutionCommand,
    *,
    adapter_order_ref: str,
) -> BrokerCallbackEvidence:
    return _PAPER_EVIDENCE_BUILDER.build_filled(
        command,
        adapter_order_ref=adapter_order_ref,
    )


def _rejected_evidence(
    command: ExecutionCommand,
    *,
    adapter_order_ref: str,
) -> BrokerCallbackEvidence:
    return _PAPER_EVIDENCE_BUILDER.build_rejected(
        command,
        adapter_order_ref=adapter_order_ref,
    )
