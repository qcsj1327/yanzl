import ast
from pathlib import Path

RUNTIME_DIR = Path("src/futures_mvp/modules/runtime")
MODULES_DIR = Path("src/futures_mvp/modules")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_runtime_has_no_broker_or_hard_runtime_framework_dependency() -> None:
    forbidden = {
        "broker",
        "ctp",
        "simnow",
        "fastapi",
        "celery",
        "kafka",
    }
    imported = set()
    for path in RUNTIME_DIR.glob("*.py"):
        imported.update(name.lower() for name in _imports(path))

    assert all(not any(fragment in name for fragment in forbidden) for name in imported)


def test_business_services_do_not_import_runtime_package() -> None:
    runtime_import = "futures_mvp.modules.runtime"
    imported = set()
    for path in MODULES_DIR.glob("*/*.py"):
        if RUNTIME_DIR in path.parents:
            continue
        imported.update(_imports(path))

    assert runtime_import not in imported


def test_scheduler_and_replay_do_not_import_repositories_or_db() -> None:
    for path in (RUNTIME_DIR / "scheduler.py", RUNTIME_DIR / "replay.py"):
        imported = _imports(path)
        assert "futures_mvp.db" not in imported
        assert "futures_mvp.interfaces.repositories" not in imported


def test_runtime_does_not_define_business_fact_mutation_calls() -> None:
    forbidden_calls = {
        "append_margin_snapshot",
        "append_pnl_snapshot",
        "append_settlement_snapshot",
        "append_position_event",
        "update_position",
        "apply_order_event(",
        "create_order(",
    }
    service_graph_text = (RUNTIME_DIR / "service_graph.py").read_text()
    text = "\n".join(path.read_text() for path in RUNTIME_DIR.glob("*.py"))
    text_without_wiring = text.replace(service_graph_text, "")

    assert all(call not in text_without_wiring for call in forbidden_calls)
