from datetime import UTC, datetime, timedelta
from decimal import Decimal

from futures_mvp.domain.enums import ExecutionReportNormalizeResultStatus, ExecutionTarget
from futures_mvp.domain.models import NormalizedExecutionReport
from futures_mvp.interfaces.repositories import ExecutionReportConflictError
from futures_mvp.modules.broker_adapter import (
    BrokerCallbackEvidence,
    BrokerCallbackTranslationStatus,
    InMemoryUnresolvedBrokerCallbackQuarantine,
    translate_callback_to_raw_execution_report,
)
from futures_mvp.modules.execution_reports import (
    ExecutionReportNormalizer,
    canonical_normalized_execution_report_payload,
)

NOW = datetime(2026, 6, 8, 9, tzinfo=UTC)


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
    ) -> None:
        del exc_type, exc, tb

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def _evidence(**updates: object) -> BrokerCallbackEvidence:
    values = {
        "adapter_name": "mock_broker",
        "execution_target": ExecutionTarget.MOCK,
        "command_id": "command-1",
        "order_id": "order-1",
        "client_order_id": "client-1",
        "adapter_order_ref": "broker-ref-1",
        "exchange_order_id": "exchange-order-1",
        "exchange_trade_id": None,
        "report_type": "acked",
        "filled_qty": Decimal("0"),
        "fill_price": None,
        "cumulative_filled_qty": Decimal("0"),
        "remaining_qty": Decimal("2"),
        "report_ts": NOW,
        "received_at": NOW + timedelta(seconds=1),
        "raw_payload": {"diagnostic": "only"},
    }
    values.update(updates)
    return BrokerCallbackEvidence(**values)


def _normalizer(repository: InMemoryExecutionReportRepository) -> ExecutionReportNormalizer:
    return ExecutionReportNormalizer(
        lambda: FakeExecutionReportUnitOfWork(repository),
        clock=lambda: NOW + timedelta(seconds=2),
    )


def test_valid_callback_translates_to_raw_execution_report() -> None:
    evidence = _evidence()
    quarantine = InMemoryUnresolvedBrokerCallbackQuarantine()

    result = translate_callback_to_raw_execution_report(evidence, quarantine=quarantine)

    assert result.status is BrokerCallbackTranslationStatus.TRANSLATED
    assert result.raw_report is not None
    assert result.raw_report.command_id == "command-1"
    assert result.raw_report.order_id == "order-1"
    assert result.raw_report.client_order_id == "client-1"
    assert result.raw_report.adapter_order_ref == "broker-ref-1"
    assert result.raw_report.raw_report_id.startswith("raw_broker_")
    assert quarantine.list_items() == []


def test_missing_lineage_is_quarantined_without_raw_report() -> None:
    for field_name in [
        "command_id",
        "order_id",
        "client_order_id",
        "adapter_order_ref",
    ]:
        quarantine = InMemoryUnresolvedBrokerCallbackQuarantine()
        result = translate_callback_to_raw_execution_report(
            _evidence(**{field_name: None}),
            quarantine=quarantine,
        )

        assert result.status is BrokerCallbackTranslationStatus.QUARANTINED_UNRESOLVED_LINEAGE
        assert result.raw_report is None
        assert result.reason == f"{field_name} is required"
        assert len(quarantine.list_items()) == 1
        assert quarantine.list_items()[0].reason == result.reason


def test_missing_stable_raw_report_id_is_quarantined_for_non_mock_target() -> None:
    quarantine = InMemoryUnresolvedBrokerCallbackQuarantine()

    result = translate_callback_to_raw_execution_report(
        _evidence(execution_target=ExecutionTarget.PAPER, raw_report_id=None),
        quarantine=quarantine,
    )

    assert result.status is BrokerCallbackTranslationStatus.QUARANTINED_UNRESOLVED_LINEAGE
    assert result.raw_report is None
    assert result.reason == "raw_report_id is required"
    assert len(quarantine.list_items()) == 1


def test_decimal_fields_are_preserved_and_raw_payload_is_diagnostic_only() -> None:
    evidence = _evidence(
        report_type="partial_fill",
        filled_qty=Decimal("1.25"),
        fill_price=Decimal("501.20"),
        cumulative_filled_qty=Decimal("1.25"),
        remaining_qty=Decimal("0.75"),
        raw_payload={
            "command_id": "raw-command-should-not-be-used",
            "order_id": "raw-order-should-not-be-used",
        },
    )

    result = translate_callback_to_raw_execution_report(evidence)

    assert result.raw_report is not None
    assert result.raw_report.command_id == "command-1"
    assert result.raw_report.order_id == "order-1"
    assert result.raw_report.filled_qty == Decimal("1.25")
    assert result.raw_report.fill_price == Decimal("501.20")
    assert result.raw_report.raw_payload is not None
    assert result.raw_report.raw_payload["command_id"] == "raw-command-should-not-be-used"


def test_translated_report_enters_existing_normalizer_pipeline_and_duplicates_noop() -> None:
    repository = InMemoryExecutionReportRepository()
    normalizer = _normalizer(repository)
    translated = translate_callback_to_raw_execution_report(_evidence())
    assert translated.raw_report is not None

    first = normalizer.normalize(translated.raw_report)
    duplicate = normalizer.normalize(
        translated.raw_report.model_copy(
            update={
                "received_at": NOW + timedelta(minutes=1),
                "raw_payload": {"diagnostic": "changed"},
            }
        )
    )

    assert first.status is ExecutionReportNormalizeResultStatus.NORMALIZED
    assert duplicate.status is ExecutionReportNormalizeResultStatus.DUPLICATE
    assert len(repository.reports) == 1


def test_duplicate_callback_same_raw_identity_different_facts_conflicts() -> None:
    repository = InMemoryExecutionReportRepository()
    normalizer = _normalizer(repository)
    first = translate_callback_to_raw_execution_report(
        _evidence(raw_report_id="raw-callback-1", report_type="acked")
    )
    changed = translate_callback_to_raw_execution_report(
        _evidence(raw_report_id="raw-callback-1", report_type="rejected")
    )
    assert first.raw_report is not None
    assert changed.raw_report is not None

    first_result = normalizer.normalize(first.raw_report)
    conflict = normalizer.normalize(changed.raw_report)

    assert first_result.status is ExecutionReportNormalizeResultStatus.NORMALIZED
    assert conflict.status is ExecutionReportNormalizeResultStatus.CONFLICT
    assert conflict.reason == "normalized_execution_report_raw_identity_conflict"
    assert len(repository.reports) == 1


def test_out_of_order_reports_remain_typed_reports_without_oms_patch() -> None:
    repository = InMemoryExecutionReportRepository()
    normalizer = _normalizer(repository)
    filled = translate_callback_to_raw_execution_report(
        _evidence(
            raw_report_id="raw-filled",
            report_type="filled",
            filled_qty=Decimal("2"),
            fill_price=Decimal("501"),
            cumulative_filled_qty=Decimal("2"),
            remaining_qty=Decimal("0"),
        )
    )
    acked = translate_callback_to_raw_execution_report(
        _evidence(raw_report_id="raw-acked", report_type="acked")
    )
    assert filled.raw_report is not None
    assert acked.raw_report is not None

    filled_result = normalizer.normalize(filled.raw_report)
    acked_result = normalizer.normalize(acked.raw_report)

    assert filled_result.status is ExecutionReportNormalizeResultStatus.NORMALIZED
    assert acked_result.status is ExecutionReportNormalizeResultStatus.NORMALIZED
    assert len(repository.reports) == 2
