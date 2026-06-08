from datetime import datetime

from futures_mvp.domain.models import NormalizedExecutionReport
from futures_mvp.interfaces.repositories import (
    ExecutionReportRepository,
    ExecutionReportUnitOfWork,
)


class FakeExecutionReportRepository:
    def append_normalized_report(
        self,
        report: NormalizedExecutionReport,
    ) -> NormalizedExecutionReport:
        return report

    def get_by_report_id(self, report_id: str) -> NormalizedExecutionReport | None:
        del report_id
        return None

    def list_by_order_id(self, order_id: str) -> list[NormalizedExecutionReport]:
        del order_id
        return []

    def list_by_command_id(self, command_id: str) -> list[NormalizedExecutionReport]:
        del command_id
        return []

    def list_by_status(
        self,
        execution_status: str,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
    ) -> list[NormalizedExecutionReport]:
        del execution_status, start_ts, end_ts
        return []


class FakeExecutionReportUnitOfWork:
    def __init__(self) -> None:
        self.execution_reports = FakeExecutionReportRepository()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

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


def test_execution_report_repository_protocol() -> None:
    assert isinstance(FakeExecutionReportRepository(), ExecutionReportRepository)


def test_execution_report_unit_of_work_protocol_exposes_reports() -> None:
    uow = FakeExecutionReportUnitOfWork()

    assert isinstance(uow, ExecutionReportUnitOfWork)
    assert isinstance(uow.execution_reports, ExecutionReportRepository)
