"""job_runs for planner idempotency

Revision ID: 0003
Revises: 0002
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_name", sa.String(100), nullable=False),
        sa.Column("logical_date", sa.Date(), nullable=False),
        sa.Column("scope_id", UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("payload", JSONB(), nullable=True),
    )
    # NULL scope_id is coalesced to a fixed sentinel so the unique index also
    # catches the ran-once-per-day case (no per-lead scope).
    op.execute("""
        CREATE UNIQUE INDEX job_runs_unique ON job_runs (
            job_name,
            logical_date,
            COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid)
        )
    """)


def downgrade() -> None:
    op.drop_table("job_runs")
