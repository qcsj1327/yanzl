from datetime import UTC, datetime, timedelta
from decimal import Decimal

from futures_mvp.domain.enums import (
    ExecutionReportNormalizeResultStatus,
    ExecutionReportStatus,
    ExecutionTarget,
    OrderStatus,
)
from futures_mvp.domain.models import NormalizedExecutionReport, RawExecutionReport
from futures_mvp.interfaces.repositories import ExecutionReportConflictError
from futures_mvp.modules.execution_reports import (
    ExecutionReportNormalizer,
    build_order_event_candidate,
    build_source_report_hash,
    canonical_normalized_execution_report_payload,
    map_report_type_to_execution_status,
    replay_execution_reports,
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
        self.commits = 0
        self.rollbacks = 0

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
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _raw(**updates: object) -> RawExecutionReport:
    values = {
        "raw_report_id": "raw-1",
        "adapter_name": "mock",
        "execution_target": ExecutionTarget.MOCK,
        "command_id": "command-1",
        "order_id": "order-1",
        "client_order_id": "client-1",
        "adapter_order_ref": "adapter-order-1",
        "exchange_order_id": "exchange-order-1",
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
    return RawExecutionReport(**values)


def _service(
    repository: InMemoryExecutionReportRepository,
) -> ExecutionReportNormalizer:
    return ExecutionReportNormalizer(
        lambda: FakeExecutionReportUnitOfWork(repository),
        clock=lambda: NOW + timedelta(seconds=2),
    )


def test_status_mapping_all_statuses() -> None:
    assert map_report_type_to_execution_status("submitted") is ExecutionReportStatus.SUBMITTED
    assert map_report_type_to_execution_status("accepted") is ExecutionReportStatus.ACKED
    assert map_report_type_to_execution_status("acked") is ExecutionReportStatus.ACKED
    assert (
        map_report_type_to_execution_status("partial_fill")
        is ExecutionReportStatus.PARTIALLY_FILLED
    )
    assert (
        map_report_type_to_execution_status("partially_filled")
        is ExecutionReportStatus.PARTIALLY_FILLED
    )
    assert map_report_type_to_execution_status("full_fill") is ExecutionReportStatus.FILLED
    assert map_report_type_to_execution_status("filled") is ExecutionReportStatus.FILLED
    assert map_report_type_to_execution_status("rejected") is ExecutionReportStatus.REJECTED
    assert map_report_type_to_execution_status("canceled") is ExecutionReportStatus.CANCELED
    assert map_report_type_to_execution_status("cancelled") is ExecutionReportStatus.CANCELED
    assert map_report_type_to_execution_status("unknown") is ExecutionReportStatus.ERROR
    assert map_report_type_to_execution_status("anything_else") is ExecutionReportStatus.ERROR


def test_order_event_candidate_mapping_and_non_event_statuses() -> None:
    repository = InMemoryExecutionReportRepository()
    service = _service(repository)

    expected = {
        "acked": OrderStatus.ACKED,
        "partial_fill": OrderStatus.PARTIALLY_FILLED,
        "filled": OrderStatus.FILLED,
        "rejected": OrderStatus.REJECTED_BY_EXCHANGE,
        "canceled": OrderStatus.CANCELED,
    }
    for report_type, order_status in expected.items():
        raw = _raw(
            raw_report_id=f"raw-{report_type}",
            report_type=report_type,
            filled_qty=Decimal("1") if report_type in {"partial_fill", "filled"} else Decimal("0"),
            fill_price=Decimal("500") if report_type in {"partial_fill", "filled"} else None,
            cumulative_filled_qty=Decimal("1")
            if report_type in {"partial_fill", "filled"}
            else Decimal("0"),
        )
        normalized = service.build_normalized_report(raw)
        candidate = build_order_event_candidate(normalized)

        assert candidate is not None
        assert candidate.new_status is order_status
        assert candidate.to_order_event().new_status is order_status

    assert build_order_event_candidate(
        service.build_normalized_report(_raw(report_type="submitted"))
    ) is None
    assert build_order_event_candidate(
        service.build_normalized_report(_raw(report_type="error"))
    ) is None


def test_normalized_report_to_order_event_candidate_full_status_coverage() -> None:
    expected_candidates = {
        ExecutionReportStatus.ACKED: OrderStatus.ACKED,
        ExecutionReportStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
        ExecutionReportStatus.FILLED: OrderStatus.FILLED,
        ExecutionReportStatus.REJECTED: OrderStatus.REJECTED_BY_EXCHANGE,
        ExecutionReportStatus.CANCELED: OrderStatus.CANCELED,
    }
    for execution_status, order_status in expected_candidates.items():
        normalized = NormalizedExecutionReport(
            report_id=f"er-{execution_status.value}",
            raw_report_id=f"raw-{execution_status.value}",
            adapter_name="mock",
            execution_target=ExecutionTarget.MOCK,
            command_id="command-1",
            order_id="order-1",
            client_order_id="client-1",
            adapter_order_ref="adapter-order-1",
            exchange_order_id="exchange-order-1",
            execution_status=execution_status,
            filled_qty=Decimal("1")
            if execution_status
            in {ExecutionReportStatus.PARTIALLY_FILLED, ExecutionReportStatus.FILLED}
            else Decimal("0"),
            fill_price=Decimal("500")
            if execution_status
            in {ExecutionReportStatus.PARTIALLY_FILLED, ExecutionReportStatus.FILLED}
            else None,
            cumulative_filled_qty=Decimal("1")
            if execution_status
            in {ExecutionReportStatus.PARTIALLY_FILLED, ExecutionReportStatus.FILLED}
            else Decimal("0"),
            remaining_qty=Decimal("1"),
            report_ts=NOW,
            normalized_at=NOW + timedelta(seconds=1),
            source_report_hash="hash-1",
        )

        candidate = build_order_event_candidate(normalized)

        assert candidate is not None
        assert candidate.execution_status is execution_status
        assert candidate.new_status is order_status

    for execution_status in {ExecutionReportStatus.SUBMITTED, ExecutionReportStatus.ERROR}:
        normalized = NormalizedExecutionReport(
            report_id=f"er-{execution_status.value}",
            raw_report_id=f"raw-{execution_status.value}",
            adapter_name="mock",
            execution_target=ExecutionTarget.MOCK,
            command_id="command-1",
            order_id="order-1",
            client_order_id="client-1",
            adapter_order_ref="adapter-order-1",
            exchange_order_id="exchange-order-1",
            execution_status=execution_status,
            filled_qty=Decimal("0"),
            fill_price=None,
            cumulative_filled_qty=Decimal("0"),
            remaining_qty=Decimal("2"),
            report_ts=NOW,
            normalized_at=NOW + timedelta(seconds=1),
            source_report_hash="hash-1",
        )

        assert build_order_event_candidate(normalized) is None


def test_normalizer_persists_duplicate_noops_and_conflicts_without_oms_apply() -> None:
    repository = InMemoryExecutionReportRepository()
    service = _service(repository)
    raw = _raw(report_type="partial_fill", filled_qty=Decimal("1"), fill_price=Decimal("500"))

    first = service.normalize(raw)
    duplicate = service.normalize(
        raw.model_copy(
            update={
                "raw_payload": {"diagnostic": "changed"},
                "received_at": NOW + timedelta(minutes=1),
            }
        )
    )

    assert first.status is ExecutionReportNormalizeResultStatus.NORMALIZED
    assert first.order_event_candidate is not None
    assert duplicate.status is ExecutionReportNormalizeResultStatus.DUPLICATE
    assert duplicate.order_event_candidate is None
    assert len(repository.reports) == 1
    assert not hasattr(service, "apply_order_event")

    existing = next(iter(repository.reports.values()))
    repository.reports[existing.report_id] = existing.model_copy(update={"reason": "changed"})
    conflict = service.normalize(raw)
    assert conflict.status is ExecutionReportNormalizeResultStatus.CONFLICT


def test_same_raw_report_id_same_canonical_duplicates_before_second_persist() -> None:
    repository = InMemoryExecutionReportRepository()
    service = _service(repository)
    raw = _raw(report_type="partial_fill", filled_qty=Decimal("1"), fill_price=Decimal("500"))

    first = service.normalize(raw)
    duplicate = service.normalize(
        raw.model_copy(
            update={
                "raw_payload": {"diagnostic": "changed"},
                "received_at": NOW + timedelta(minutes=1),
            }
        )
    )

    assert first.status is ExecutionReportNormalizeResultStatus.NORMALIZED
    assert duplicate.status is ExecutionReportNormalizeResultStatus.DUPLICATE
    assert duplicate.normalized_report == first.normalized_report
    assert len(repository.reports) == 1


def test_same_raw_report_id_different_quantity_conflicts_before_second_persist() -> None:
    repository = InMemoryExecutionReportRepository()
    service = _service(repository)

    first = service.normalize(_raw(raw_report_id="raw-same", filled_qty=Decimal("0")))
    conflict = service.normalize(_raw(raw_report_id="raw-same", filled_qty=Decimal("1")))

    assert first.status is ExecutionReportNormalizeResultStatus.NORMALIZED
    assert conflict.status is ExecutionReportNormalizeResultStatus.CONFLICT
    assert conflict.reason == "normalized_execution_report_raw_identity_conflict"
    assert len(repository.reports) == 1


def test_same_raw_report_id_different_report_type_conflicts_before_second_persist() -> None:
    repository = InMemoryExecutionReportRepository()
    service = _service(repository)

    first = service.normalize(_raw(raw_report_id="raw-same", report_type="acked"))
    conflict = service.normalize(_raw(raw_report_id="raw-same", report_type="rejected"))

    assert first.status is ExecutionReportNormalizeResultStatus.NORMALIZED
    assert conflict.status is ExecutionReportNormalizeResultStatus.CONFLICT
    assert len(repository.reports) == 1


def test_same_raw_report_id_different_report_ts_conflicts_when_canonical() -> None:
    repository = InMemoryExecutionReportRepository()
    service = _service(repository)

    first = service.normalize(_raw(raw_report_id="raw-same", report_ts=NOW))
    conflict = service.normalize(
        _raw(raw_report_id="raw-same", report_ts=NOW + timedelta(seconds=1))
    )

    assert first.status is ExecutionReportNormalizeResultStatus.NORMALIZED
    assert conflict.status is ExecutionReportNormalizeResultStatus.CONFLICT
    assert len(repository.reports) == 1


def test_different_raw_report_id_same_facts_are_independent_reports() -> None:
    repository = InMemoryExecutionReportRepository()
    service = _service(repository)

    first = service.normalize(_raw(raw_report_id="raw-1"))
    second = service.normalize(_raw(raw_report_id="raw-2"))

    assert first.status is ExecutionReportNormalizeResultStatus.NORMALIZED
    assert second.status is ExecutionReportNormalizeResultStatus.NORMALIZED
    assert first.normalized_report is not None
    assert second.normalized_report is not None
    assert first.normalized_report.report_id != second.normalized_report.report_id
    assert len(repository.reports) == 2


def test_replay_execution_reports_is_deterministic_and_uses_normalizer_path() -> None:
    repository = InMemoryExecutionReportRepository()
    service = _service(repository)
    later = _raw(raw_report_id="raw-2", report_ts=NOW + timedelta(seconds=5))
    earlier = _raw(raw_report_id="raw-1", report_ts=NOW)

    results = replay_execution_reports(service, [later, earlier])
    duplicate_results = replay_execution_reports(service, [earlier, later])

    replayed_raw_ids = [
        result.normalized_report.raw_report_id
        for result in results
        if result.normalized_report
    ]
    assert replayed_raw_ids == ["raw-1", "raw-2"]
    assert [result.status for result in duplicate_results] == [
        ExecutionReportNormalizeResultStatus.DUPLICATE,
        ExecutionReportNormalizeResultStatus.DUPLICATE,
    ]
    assert build_source_report_hash(earlier) == results[0].normalized_report.source_report_hash
