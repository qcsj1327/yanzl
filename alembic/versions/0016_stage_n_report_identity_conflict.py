"""stage n report identity conflict

Revision ID: 0016_stage_n_report_identity
Revises: 0015_stage_l5_accounting
Create Date: 2026-06-08 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016_stage_n_report_identity"
down_revision: str | None = "0015_stage_l5_accounting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_normalized_execution_reports_raw_report_id",
        "normalized_execution_reports",
        ["raw_report_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_normalized_execution_reports_raw_report_id",
        "normalized_execution_reports",
        type_="unique",
    )
