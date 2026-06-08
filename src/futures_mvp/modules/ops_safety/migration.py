from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import text


class SupportsExecute(Protocol):
    def execute(self, statement: Any) -> Any: ...


@dataclass(frozen=True)
class MigrationReadinessReport:
    compatible: bool
    current_revision: str | None
    expected_revision: str | None
    reason: str | None = None


class MigrationReadinessChecker:
    def __init__(
        self,
        connection_provider: Callable[[], SupportsExecute],
        *,
        expected_revision: str | None,
        compatible_revisions: tuple[str, ...] = (),
    ) -> None:
        self._connection_provider = connection_provider
        self._expected_revision = expected_revision
        self._compatible_revisions = compatible_revisions

    def check(self) -> MigrationReadinessReport:
        try:
            connection = self._connection_provider()
            result = connection.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
        except Exception as exc:
            return MigrationReadinessReport(
                compatible=False,
                current_revision=None,
                expected_revision=self._expected_revision,
                reason=f"migration readiness check failed: {exc}",
            )
        current_revision = None if row is None else str(row[0])
        compatible = _is_compatible(
            current_revision,
            self._expected_revision,
            self._compatible_revisions,
        )
        return MigrationReadinessReport(
            compatible=compatible,
            current_revision=current_revision,
            expected_revision=self._expected_revision,
            reason=None if compatible else "db migration revision is incompatible",
        )


def disabled_migration_readiness_report() -> MigrationReadinessReport:
    return MigrationReadinessReport(
        compatible=True,
        current_revision=None,
        expected_revision=None,
        reason="migration readiness check disabled",
    )


def _is_compatible(
    current_revision: str | None,
    expected_revision: str | None,
    compatible_revisions: tuple[str, ...],
) -> bool:
    if current_revision is None:
        return False
    if expected_revision is not None and current_revision == expected_revision:
        return True
    return current_revision in compatible_revisions

