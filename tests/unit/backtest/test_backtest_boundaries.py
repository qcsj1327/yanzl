from pathlib import Path

BACKTEST_ROOT = Path("src/futures_mvp/modules/backtest")


def test_backtest_module_does_not_import_mutation_or_live_boundaries() -> None:
    forbidden = (
        "futures_mvp.db",
        "modules.oms",
        "modules.trade",
        "modules.position",
        "modules.accounting",
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

    for path in BACKTEST_ROOT.glob("*.py"):
        content = path.read_text()
        for token in forbidden:
            assert token not in content, f"{path} must not reference {token}"


def test_stage_v2_does_not_add_schema_or_alembic_files() -> None:
    assert not Path("tests/unit/backtest").joinpath("alembic").exists()
    assert all("backtest" not in path.name for path in Path("alembic/versions").glob("*.py"))
    assert not Path("src/futures_mvp/db").joinpath("backtest.py").exists()
