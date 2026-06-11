import ast
from pathlib import Path

from futures_mvp.modules.operator_console.diagnostics import (
    read_only_diagnostics_placeholder,
)

ROOT = Path(__file__).resolve().parents[3]
DIAGNOSTICS_PATH = ROOT / "src" / "futures_mvp" / "modules" / "operator_console" / "diagnostics.py"


def test_read_only_diagnostics_provider_returns_unknown_values() -> None:
    diagnostics = read_only_diagnostics_placeholder()

    assert dict(diagnostics.items) == {
        "pytest status": "unknown/not run",
        "ruff status": "unknown/not run",
        "mypy status": "unknown/not run",
        "alembic current": "unknown/not checked",
        "git commit/tag": "unknown/not checked",
        "worktree": "unknown/not checked",
        "DB health": "unknown/not checked",
        "Redis health": "unknown/not checked",
        "last error": "none",
    }


def test_diagnostics_provider_does_not_execute_commands() -> None:
    tree = ast.parse(DIAGNOSTICS_PATH.read_text(), filename=str(DIAGNOSTICS_PATH))
    forbidden_imports = {"subprocess", "os", "shlex"}
    forbidden_calls = {"run", "Popen", "check_call", "check_output", "system"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name not in forbidden_imports for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in forbidden_imports
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_calls
