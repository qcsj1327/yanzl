from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from futures_mvp.db.models import Base
from futures_mvp.db.models import NormalizedExecutionReport as NormalizedExecutionReportOrm
from futures_mvp.db.repositories import SQLAlchemyExecutionReportRepository
from futures_mvp.db.unit_of_work import SQLAlchemyExecutionReportUnitOfWork, SQLAlchemyUnitOfWork
from futures_mvp.domain.enums import ExecutionReportStatus, ExecutionTarget
from futures_mvp.domain.models import NormalizedExecutionReport, RawExecutionReport
from futures_mvp.interfaces.repositories import ExecutionReportConflictError
from futures_mvp.modules.execution_reports import (
    ExecutionReportNormalizer,
    build_normalized_report_id,
    build_source_report_hash,
    canonical_normalized_execution_report_payload,
)

NOW = datetime(2026, 6, 8, 9, tzinfo=UTC)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


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


def _normalized(raw: RawExecutionReport | None = None):
    raw = raw or _raw()
    source_hash = build_source_report_hash(raw)
    return NormalizedExecutionReport(
        report_id=build_normalized_report_id(raw, source_hash),
        raw_report_id=raw.raw_report_id,
        adapter_name=raw.adapter_name,
        execution_target=raw.execution_target,
        command_id=raw.command_id,
        order_id=raw.order_id,
        client_order_id=raw.client_order_id,
        adapter_order_ref=raw.adapter_order_ref,
        exchange_order_id=raw.exchange_order_id,
        execution_status=ExecutionReportStatus.ACKED,
        filled_qty=raw.filled_qty,
        fill_price=raw.fill_price,
        cumulative_filled_qty=raw.cumulative_filled_qty,
        remaining_qty=raw.remaining_qty,
        report_ts=raw.report_ts,
        normalized_at=NOW + timedelta(seconds=2),
        reason=None,
        source_report_hash=source_hash,
        raw_payload=raw.raw_payload,
    )


def test_normalized_execution_reports_schema_contract(session: Session) -> None:
    inspector = inspect(session.bind)

    assert "normalized_execution_reports" in inspector.get_table_names()
    assert "raw_execution_reports" not in inspector.get_table_names()
    assert "trades" in inspector.get_table_names()
    assert "fills" not in inspector.get_table_names()
    assert "report_id" in NormalizedExecutionReportOrm.__table__.columns
    assert "source_report_hash" in NormalizedExecutionReportOrm.__table__.columns
    assert "raw_payload" in NormalizedExecutionReportOrm.__table__.columns
    assert {
        "ix_normalized_execution_reports_order_id",
        "ix_normalized_execution_reports_command_id",
        "ix_normalized_execution_reports_client_order_id",
        "ix_normalized_execution_reports_execution_status",
        "ix_normalized_execution_reports_report_ts",
    }.issubset({index.name for index in NormalizedExecutionReportOrm.__table__.indexes})


def test_repository_round_trip_duplicate_conflict_and_queries(session: Session) -> None:
    repository = SQLAlchemyExecutionReportRepository(session)
    report = _normalized()

    first = repository.append_normalized_report(report)
    duplicate = repository.append_normalized_report(
        report.model_copy(
            update={
                "raw_payload": {"diagnostic": "changed"},
                "normalized_at": NOW + timedelta(minutes=1),
            }
        )
    )

    assert canonical_normalized_execution_report_payload(
        first
    ) == canonical_normalized_execution_report_payload(duplicate)
    assert first.raw_payload == {"diagnostic": "only"}
    assert repository.get_by_report_id(report.report_id) is not None
    assert [item.report_id for item in repository.list_by_order_id("order-1")] == [
        report.report_id
    ]
    assert [item.report_id for item in repository.list_by_command_id("command-1")] == [
        report.report_id
    ]
    assert [
        item.report_id
        for item in repository.list_by_status(ExecutionReportStatus.ACKED, NOW, NOW)
    ] == [report.report_id]

    with pytest.raises(ExecutionReportConflictError):
        repository.append_normalized_report(report.model_copy(update={"reason": "changed"}))


def test_unit_of_work_exposes_execution_reports(session: Session) -> None:
    with SQLAlchemyUnitOfWork(session=session) as uow:
        report = uow.execution_reports.append_normalized_report(_normalized())
        uow.commit()

    assert report.report_id == _normalized().report_id

    with SQLAlchemyExecutionReportUnitOfWork(session=session) as uow:
        assert uow.execution_reports.get_by_report_id(report.report_id) is not None


def test_no_stage_l_forbidden_tables_created_by_metadata(session: Session) -> None:
    table_names = set(inspect(session.bind).get_table_names())

    assert "raw_execution_reports" not in table_names
    assert "fills" not in table_names
    assert "broker_orders" not in table_names
    assert "broker_reports" not in table_names


def test_normalizer_db_round_trip_duplicate_and_conflict(session: Session) -> None:
    normalizer = ExecutionReportNormalizer(
        lambda: SQLAlchemyExecutionReportUnitOfWork(session=session),
        clock=lambda: NOW + timedelta(seconds=2),
    )
    raw = _raw()

    first = normalizer.normalize(raw)
    duplicate = normalizer.normalize(
        raw.model_copy(update={"raw_payload": {"diagnostic": "changed"}})
    )

    assert first.normalized_report is not None
    assert duplicate.normalized_report is not None
    assert first.normalized_report.report_id == duplicate.normalized_report.report_id
    assert duplicate.order_event_candidate is None

    source_hash = build_source_report_hash(raw)
    report_id = build_normalized_report_id(raw, source_hash)
    session.execute(
        text(
            "update normalized_execution_reports set reason = 'changed' "
            "where report_id = :report_id"
        ),
        {"report_id": report_id},
    )
    session.commit()

    conflict = normalizer.normalize(raw)
    assert conflict.status.name == "CONFLICT"
