from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from futures_mvp.db.models import Base, ExecutionCommand
from futures_mvp.db.repositories import SQLAlchemyExecutionCommandRepository
from futures_mvp.db.unit_of_work import SQLAlchemyUnitOfWork
from futures_mvp.domain.enums import (
    Direction,
    ExecutionCommandType,
    ExecutionTarget,
    Offset,
    OrderType,
)
from futures_mvp.domain.models import ExecutionCommand as DomainExecutionCommand
from futures_mvp.interfaces.repositories import ExecutionCommandConflictError
from futures_mvp.modules.execution_gateway import (
    build_execution_command_id,
    build_execution_command_payload_hash,
    canonical_execution_command_payload,
)

NOW = datetime(2026, 6, 8, 9, tzinfo=UTC)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _command(**updates: object) -> DomainExecutionCommand:
    values = {
        "command_id": build_execution_command_id(
            "order-1",
            ExecutionCommandType.SUBMIT_ORDER,
            ExecutionTarget.MOCK,
        ),
        "order_id": "order-1",
        "client_order_id": "client-1",
        "account_id": "account-1",
        "symbol": "au",
        "instrument_id": "au2606",
        "trade_instrument_id": "au2606",
        "exchange": "SHFE",
        "side": Direction.BUY,
        "offset": Offset.OPEN,
        "quantity": Decimal("2"),
        "price": Decimal("500"),
        "order_type": OrderType.LIMIT,
        "tif": "GFD",
        "command_type": ExecutionCommandType.SUBMIT_ORDER,
        "execution_target": ExecutionTarget.MOCK,
        "command_payload_hash": "pending",
        "created_at": NOW,
        "raw_payload": {"diagnostic": "original"},
    }
    values.update(updates)
    command = DomainExecutionCommand(**values)
    if command.command_payload_hash == "pending":
        command = command.model_copy(
            update={"command_payload_hash": build_execution_command_payload_hash(command)}
        )
    return command


def test_execution_commands_schema_contract(session: Session) -> None:
    inspector = inspect(session.bind)
    assert "execution_commands" in inspector.get_table_names()
    assert "command_id" in ExecutionCommand.__table__.columns
    assert "command_payload_hash" in ExecutionCommand.__table__.columns
    assert "raw_payload" in ExecutionCommand.__table__.columns
    assert "ix_execution_commands_order_id" in {
        index.name for index in ExecutionCommand.__table__.indexes
    }
    assert "ix_execution_commands_client_order_id" in {
        index.name for index in ExecutionCommand.__table__.indexes
    }
    assert "ix_execution_commands_execution_target" in {
        index.name for index in ExecutionCommand.__table__.indexes
    }
    assert "ix_execution_commands_created_at" in {
        index.name for index in ExecutionCommand.__table__.indexes
    }


def test_repository_round_trip_duplicate_and_conflict(session: Session) -> None:
    repository = SQLAlchemyExecutionCommandRepository(session)
    command = _command()

    first = repository.append_execution_command(command)
    second = repository.append_execution_command(
        command.model_copy(
            update={
                "raw_payload": {"diagnostic": "changed"},
                "created_at": datetime(2026, 6, 8, 10, tzinfo=UTC),
            }
        )
    )

    assert canonical_execution_command_payload(first) == canonical_execution_command_payload(
        second
    )
    assert first.raw_payload == {"diagnostic": "original"}
    assert repository.get_by_command_id(command.command_id) is not None
    assert [item.command_id for item in repository.list_by_order_id("order-1")] == [
        command.command_id
    ]
    assert [item.command_id for item in repository.list_by_target(ExecutionTarget.MOCK)] == [
        command.command_id
    ]

    with pytest.raises(ExecutionCommandConflictError):
        repository.append_execution_command(
            command.model_copy(update={"symbol": "ag", "command_payload_hash": "different"})
        )


def test_unit_of_work_exposes_execution_commands(session: Session) -> None:
    with SQLAlchemyUnitOfWork(session=session) as uow:
        command = uow.execution_commands.append_execution_command(_command())
        uow.commit()

    assert command.command_id == _command().command_id
