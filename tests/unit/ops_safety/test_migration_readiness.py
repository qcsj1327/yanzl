from __future__ import annotations

from typing import Any

from futures_mvp.modules.ops_safety import MigrationReadinessChecker


class FakeResult:
    def __init__(self, revision: str | None) -> None:
        self._revision = revision

    def fetchone(self) -> tuple[str] | None:
        if self._revision is None:
            return None
        return (self._revision,)


class FakeConnection:
    def __init__(self, revision: str | None) -> None:
        self.revision = revision
        self.statements: list[str] = []

    def execute(self, statement: Any) -> FakeResult:
        text = str(statement)
        self.statements.append(text)
        return FakeResult(self.revision)


def test_migration_checker_compatible() -> None:
    connection = FakeConnection("head")
    checker = MigrationReadinessChecker(lambda: connection, expected_revision="head")

    report = checker.check()

    assert report.compatible is True
    assert report.current_revision == "head"


def test_migration_checker_mismatch_failed() -> None:
    checker = MigrationReadinessChecker(lambda: FakeConnection("old"), expected_revision="head")

    report = checker.check()

    assert report.compatible is False
    assert report.current_revision == "old"
    assert report.reason == "db migration revision is incompatible"


def test_migration_checker_is_read_only() -> None:
    connection = FakeConnection("head")
    checker = MigrationReadinessChecker(lambda: connection, expected_revision="head")

    checker.check()

    assert connection.statements == ["SELECT version_num FROM alembic_version"]
    assert all("upgrade" not in statement.lower() for statement in connection.statements)
    assert all("insert" not in statement.lower() for statement in connection.statements)
    assert all("update" not in statement.lower() for statement in connection.statements)

