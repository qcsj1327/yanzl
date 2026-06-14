from pathlib import Path

STRATEGY_RUNTIME_ROOT = Path("src/futures_mvp/modules/strategy_runtime")


def test_strategy_runtime_has_no_db_live_broker_or_target_imports() -> None:
    forbidden = (
        "futures_mvp.db",
        "sqlalchemy",
        "alembic",
        "repository",
        "UnitOfWork",
        "modules.oms",
        "modules.position",
        "modules.execution",
        "modules.execution_gateway",
        "modules.broker_adapter",
        "ExecutionTarget",
        "PAPER",
        "SIM",
        "LIVE",
        "ctp",
        "simnow",
        "socket",
        "requests",
        "urllib",
    )

    for path in STRATEGY_RUNTIME_ROOT.glob("*.py"):
        content = path.read_text()
        for token in forbidden:
            assert token not in content, f"{path} must not reference {token}"


def test_stage_v4_does_not_add_schema_or_alembic_files() -> None:
    assert all(
        "strategy_runtime" not in path.name
        for path in Path("alembic/versions").glob("*.py")
    )
    assert not Path("src/futures_mvp/db").joinpath("strategy_runtime.py").exists()
