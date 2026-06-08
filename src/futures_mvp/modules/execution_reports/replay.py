from collections.abc import Iterable

from futures_mvp.domain.models import ExecutionReportNormalizeResult, RawExecutionReport
from futures_mvp.modules.execution_reports.service import ExecutionReportNormalizer


def replay_execution_reports(
    normalizer: ExecutionReportNormalizer,
    raw_reports: Iterable[RawExecutionReport],
) -> list[ExecutionReportNormalizeResult]:
    ordered = sorted(
        raw_reports,
        key=lambda report: (
            report.report_ts,
            report.adapter_name,
            report.command_id,
            report.raw_report_id,
        ),
    )
    return [normalizer.normalize(raw_report) for raw_report in ordered]
