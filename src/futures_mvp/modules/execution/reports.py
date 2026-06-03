from collections.abc import Callable

from futures_mvp.modules.execution.mapper import map_exchange_report
from futures_mvp.modules.execution.models import ExchangeReport, MappingContext, MappingResult


class InMemoryExecutionReportSink:
    """Local in-memory report surface for tests and the current runtime layer."""

    def __init__(self) -> None:
        self._reports: list[ExchangeReport] = []

    def append(self, report: ExchangeReport) -> None:
        self._reports.append(report)

    def list_reports(self) -> list[ExchangeReport]:
        return list(self._reports)

    def drain_reports(self) -> list[ExchangeReport]:
        reports = list(self._reports)
        self._reports.clear()
        return reports


class ExecutionReportHandler:
    def __init__(
        self,
        mapper: Callable[[ExchangeReport, MappingContext], MappingResult] = map_exchange_report,
    ) -> None:
        self._mapper = mapper

    def handle(self, report: ExchangeReport, context: MappingContext) -> MappingResult:
        return self._mapper(report, context)
