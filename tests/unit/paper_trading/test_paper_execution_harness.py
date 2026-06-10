from datetime import UTC, datetime
from decimal import Decimal

from futures_mvp.domain.enums import (
    Direction,
    ExecutionCommandResultStatus,
    ExecutionCommandType,
    ExecutionReportNormalizeResultStatus,
    ExecutionReportStatus,
    ExecutionTarget,
    Offset,
    OrderType,
)
from futures_mvp.domain.models import ExecutionCommand, NormalizedExecutionReport
from futures_mvp.interfaces.repositories import ExecutionReportConflictError
from futures_mvp.modules.broker_adapter import MockBrokerAdapter
from futures_mvp.modules.execution_gateway import build_execution_command_payload_hash
from futures_mvp.modules.execution_reports import (
    ExecutionReportNormalizer,
    build_order_event_candidate,
    canonical_normalized_execution_report_payload,
)
from futures_mvp.modules.paper_trading import (
    PaperExecutionHarness,
    PaperExecutionStatus,
    PaperFillPolicy,
)

NOW = datetime(2026, 6, 9, 9, tzinfo=UTC)


class InMemoryExecutionReportRepository:
    def __init__(self) -> None:
        self.reports: dict[str, NormalizedExecutionReport] = {}

    def append_normalized_report(
        self,
        report: NormalizedExecutionReport,
    ) -> NormalizedExecutionReport:
        existing = self.reports.get(report.report_id)
        if existing is not None:
            if canonical_normalized_execution_report_payload(
                existing
            ) != canonical_normalized_execution_report_payload(report):
                raise ExecutionReportConflictError("conflict")
            return existing
        self.reports[report.report_id] = report
        return report

    def get_by_report_id(self, report_id: str) -> NormalizedExecutionReport | None:
        return self.reports.get(report_id)

    def get_by_raw_report_id(self, raw_report_id: str) -> NormalizedExecutionReport | None:
        return next(
            (
                report
                for report in self.reports.values()
                if report.raw_report_id == raw_report_id
            ),
            None,
        )

    def list_by_order_id(self, order_id: str) -> list[NormalizedExecutionReport]:
        return [report for report in self.reports.values() if report.order_id == order_id]

    def list_by_command_id(self, command_id: str) -> list[NormalizedExecutionReport]:
        return [report for report in self.reports.values() if report.command_id == command_id]

    def list_by_status(
        self,
        execution_status: str,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
    ) -> list[NormalizedExecutionReport]:
        del start_ts, end_ts
        return [
            report
            for report in self.reports.values()
            if report.execution_status.value == execution_status
        ]


class FakeExecutionReportUnitOfWork:
    def __init__(self, repository: InMemoryExecutionReportRepository) -> None:
        self.execution_reports = repository

    def __enter__(self) -> "FakeExecutionReportUnitOfWork":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> bool | None:
        del exc_type, exc, tb
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def _command(
    *,
    command_id: str = "command-1",
    execution_target: ExecutionTarget = ExecutionTarget.MOCK,
) -> ExecutionCommand:
    command = ExecutionCommand(
        command_id=command_id,
        order_id="order-1",
        client_order_id="client-1",
        account_id="account-1",
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        side=Direction.BUY,
        offset=Offset.OPEN,
        quantity=Decimal("2"),
        price=Decimal("500"),
        order_type=OrderType.LIMIT,
        tif="GFD",
        command_type=ExecutionCommandType.SUBMIT_ORDER,
        execution_target=execution_target,
        command_payload_hash="pending",
        created_at=NOW,
    )
    return command.model_copy(
        update={"command_payload_hash": build_execution_command_payload_hash(command)}
    )


def _normalizer(repository: InMemoryExecutionReportRepository) -> ExecutionReportNormalizer:
    return ExecutionReportNormalizer(
        lambda: FakeExecutionReportUnitOfWork(repository),
        clock=lambda: NOW,
    )


def test_full_fill_returns_command_result_and_raw_execution_report() -> None:
    result = PaperExecutionHarness(
        fill_policy=PaperFillPolicy.IMMEDIATE_FULL_FILL,
    ).execute(_command())

    assert result.status is PaperExecutionStatus.EXECUTED
    assert result.command_result.status is ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER
    assert len(result.raw_reports) == 1
    raw = result.raw_reports[0]
    assert raw.execution_target is ExecutionTarget.MOCK
    assert raw.adapter_name == "paper_harness"
    assert raw.report_type == "filled"
    assert raw.filled_qty == Decimal("2")
    assert raw.fill_price == Decimal("500")
    assert raw.cumulative_filled_qty == Decimal("2")
    assert raw.remaining_qty == Decimal("0")


def test_reject_returns_rejected_raw_report_without_trade_fact() -> None:
    result = PaperExecutionHarness(
        fill_policy=PaperFillPolicy.IMMEDIATE_REJECT,
    ).execute(_command())

    assert result.status is PaperExecutionStatus.REJECTED
    assert len(result.raw_reports) == 1
    raw = result.raw_reports[0]
    assert raw.report_type == "rejected"
    assert raw.filled_qty == Decimal("0")
    assert raw.fill_price is None
    assert raw.exchange_trade_id is None
    assert raw.fill_id is None
    assert "trade" not in result.__class__.__dataclass_fields__


def test_pre_send_timeout_returns_failure_and_no_report() -> None:
    result = PaperExecutionHarness(
        fill_policy=PaperFillPolicy.PRE_SEND_TIMEOUT,
    ).execute(_command())

    assert result.status is PaperExecutionStatus.FAILED
    assert result.command_result.status is ExecutionCommandResultStatus.ERROR
    assert result.command_result.reason == "pre_send_timeout"
    assert result.command_result.adapter_order_ref is None
    assert result.raw_reports == ()


def test_post_send_uncertain_returns_uncertain_and_no_report() -> None:
    result = PaperExecutionHarness(
        fill_policy=PaperFillPolicy.POST_SEND_UNCERTAIN,
    ).execute(_command())

    assert result.status is PaperExecutionStatus.UNCERTAIN
    assert result.command_result.status is ExecutionCommandResultStatus.ERROR
    assert result.command_result.reason == "post_send_uncertain"
    assert result.command_result.adapter_order_ref is not None
    assert result.raw_reports == ()


def test_identities_are_deterministic_and_not_timestamp_now_or_random() -> None:
    command = _command()
    first = PaperExecutionHarness().execute(command)
    second = PaperExecutionHarness().execute(command)

    assert len(first.raw_reports) == 1
    assert len(second.raw_reports) == 1
    first_raw = first.raw_reports[0]
    second_raw = second.raw_reports[0]

    assert first.command_result.adapter_order_ref == second.command_result.adapter_order_ref
    assert first_raw.raw_report_id == second_raw.raw_report_id
    assert first_raw.fill_id == second_raw.fill_id
    assert first_raw.exchange_trade_id == second_raw.exchange_trade_id
    assert first_raw.raw_report_id.startswith("paper_raw_")
    assert first_raw.fill_id is not None
    assert first_raw.fill_id.startswith("paper_fill_")
    assert first_raw.raw_payload is None


def test_duplicate_same_command_uses_mock_submit_duplicate_without_new_identity() -> None:
    adapter = MockBrokerAdapter(clock=lambda: NOW)
    harness = PaperExecutionHarness(adapter=adapter)
    command = _command()

    first = harness.execute(command)
    duplicate = harness.execute(command)

    assert first.command_result.status is ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER
    assert duplicate.command_result.status is ExecutionCommandResultStatus.DUPLICATE
    assert duplicate.raw_reports == ()
    assert len(adapter.submitted_commands) == 1


def test_full_fill_raw_report_enters_normalizer_and_duplicates_noop() -> None:
    repository = InMemoryExecutionReportRepository()
    normalizer = _normalizer(repository)
    raw = PaperExecutionHarness().execute(_command()).raw_reports[0]

    first = normalizer.normalize(raw)
    duplicate = normalizer.normalize(raw)

    assert first.status is ExecutionReportNormalizeResultStatus.NORMALIZED
    assert first.normalized_report is not None
    assert first.normalized_report.execution_status is ExecutionReportStatus.FILLED
    assert first.order_event_candidate is not None
    assert duplicate.status is ExecutionReportNormalizeResultStatus.DUPLICATE
    assert len(repository.reports) == 1


def test_reject_report_normalizes_to_order_event_candidate_but_no_trade() -> None:
    repository = InMemoryExecutionReportRepository()
    normalizer = _normalizer(repository)
    raw = PaperExecutionHarness(
        fill_policy=PaperFillPolicy.IMMEDIATE_REJECT,
    ).execute(_command()).raw_reports[0]

    normalized = normalizer.normalize(raw)

    assert normalized.status is ExecutionReportNormalizeResultStatus.NORMALIZED
    assert normalized.normalized_report is not None
    assert normalized.normalized_report.execution_status is ExecutionReportStatus.REJECTED
    assert build_order_event_candidate(normalized.normalized_report) is not None
    assert raw.exchange_trade_id is None
    assert raw.fill_id is None


def test_non_mock_target_rejected_without_enabling_paper_target() -> None:
    for target in [ExecutionTarget.PAPER, ExecutionTarget.SIM, ExecutionTarget.LIVE]:
        result = PaperExecutionHarness().execute(
            _command(command_id=f"command-{target.value}", execution_target=target)
        )

        assert result.status is PaperExecutionStatus.REJECTED
        assert result.command_result.status is ExecutionCommandResultStatus.REJECTED_BY_ADAPTER
        assert result.raw_reports == ()

