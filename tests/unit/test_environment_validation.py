import sys
from pathlib import Path


def test_environment_validation_uses_project_venv_python() -> None:
    project_root = Path(__file__).resolve().parents[2]
    expected = project_root / ".venv" / "bin" / "python"

    assert Path(sys.executable).resolve() == expected.resolve()


def test_environment_validation_python_version_is_312() -> None:
    assert sys.version_info.major == 3
    assert sys.version_info.minor == 12
