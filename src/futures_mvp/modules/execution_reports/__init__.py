"""Stage L Execution Report Normalization core."""

from futures_mvp.modules.execution_reports.canonical import (
    build_source_report_hash,
    canonical_normalized_execution_report_payload,
    canonical_raw_execution_report_payload,
)
from futures_mvp.modules.execution_reports.ids import build_normalized_report_id
from futures_mvp.modules.execution_reports.mapping import (
    build_order_event_candidate,
    map_report_type_to_execution_status,
)
from futures_mvp.modules.execution_reports.replay import replay_execution_reports
from futures_mvp.modules.execution_reports.service import ExecutionReportNormalizer

__all__ = [
    "ExecutionReportNormalizer",
    "build_normalized_report_id",
    "build_order_event_candidate",
    "build_source_report_hash",
    "canonical_normalized_execution_report_payload",
    "canonical_raw_execution_report_payload",
    "map_report_type_to_execution_status",
    "replay_execution_reports",
]
