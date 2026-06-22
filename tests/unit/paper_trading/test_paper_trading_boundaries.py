import ast
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PAPER_TRADING_DIR = ROOT / "src" / "futures_mvp" / "modules" / "paper_trading"
RESEARCH_MVP = PAPER_TRADING_DIR / "research_mvp.py"
EXECUTION_GATEWAY_SERVICE = (
    ROOT / "src" / "futures_mvp" / "modules" / "execution_gateway" / "service.py"
)
ALEMBIC_DIR = ROOT / "alembic" / "versions"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _research_mvp_source() -> str:
    return RESEARCH_MVP.read_text()


def test_paper_trading_root_import_does_not_load_legacy_boundaries() -> None:
    forbidden = {
        "futures_mvp.modules.broker_adapter",
        "futures_mvp.modules.oms",
        "futures_mvp.modules.oms_to_trade",
        "futures_mvp.modules.position",
        "futures_mvp.modules.margin",
        "futures_mvp.modules.pnl",
        "futures_mvp.modules.settlement",
        "futures_mvp.modules.accounting",
        "futures_mvp.db",
    }
    for name in list(sys.modules):
        if name == "futures_mvp.modules.paper_trading" or name.startswith(
            "futures_mvp.modules.paper_trading."
        ):
            sys.modules.pop(name)

    before = set(sys.modules)
    importlib.import_module("futures_mvp.modules.paper_trading")
    loaded_by_root_import = set(sys.modules) - before

    assert all(
        not (
            module in loaded_by_root_import
            or any(name.startswith(module + ".") for name in loaded_by_root_import)
        )
        for module in forbidden
    )


def test_paper_trading_root_exports_research_mvp_only() -> None:
    module = importlib.import_module("futures_mvp.modules.paper_trading")

    assert "PaperResearchRuntime" in module.__all__
    assert "PaperResearchSession" in module.__all__
    assert "PaperExecutionHarness" not in module.__all__
    assert "PaperTradingCoordinator" not in module.__all__
    assert "BrokerCallbackEvidence" not in module.__all__
    assert "PaperExecutionHarness" not in vars(module)
    assert "PaperTradingCoordinator" not in vars(module)


def test_paper_trading_root_rejects_legacy_coordinator_access() -> None:
    module = importlib.import_module("futures_mvp.modules.paper_trading")

    with pytest.raises(ImportError):
        exec(
            "from futures_mvp.modules.paper_trading import PaperTradingCoordinator",
            {},
        )
    assert not hasattr(module, "PaperTradingCoordinator")


def test_research_mvp_has_no_legacy_or_live_dependencies() -> None:
    forbidden = {
        "futures_mvp.modules.broker_adapter",
        "futures_mvp.modules.paper_trading.coordinator",
        "futures_mvp.modules.paper_trading.harness",
        "futures_mvp.modules.paper_trading.reports",
        "futures_mvp.modules.oms",
        "futures_mvp.modules.oms_to_trade",
        "futures_mvp.modules.position",
        "futures_mvp.modules.margin",
        "futures_mvp.modules.pnl",
        "futures_mvp.modules.settlement",
        "futures_mvp.modules.accounting",
        "futures_mvp.db",
        "socket",
        "requests",
        "httpx",
        "urllib",
    }
    imported = _imports(RESEARCH_MVP)

    assert forbidden.isdisjoint(imported)
    source = _research_mvp_source()
    forbidden_fragments = (
        "ExecutionTarget.PAPER",
        "ExecutionTarget.SIM",
        "ExecutionTarget.LIVE",
        "apply_candidate(",
        "create_trade(",
        ".apply_trade(",
        ".settle(",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)


def test_paper_trading_does_not_add_schema_or_alembic_revision() -> None:
    stage_p1_migrations = [
        path
        for path in ALEMBIC_DIR.glob("*.py")
        if "paper" in path.name.lower() or "stage_p1" in path.name.lower()
    ]

    assert stage_p1_migrations == []


def test_execution_gateway_still_rejects_non_mock_targets() -> None:
    source = EXECUTION_GATEWAY_SERVICE.read_text()

    assert "if execution_target is not ExecutionTarget.MOCK" in source
    assert "REJECTED_UNSUPPORTED_TARGET" in source
    assert "ExecutionTarget.PAPER" not in source
