"""trust signals: farmer badges + anti-gaming flags

Revision ID: 0010
Revises: 0009

Design §3.7. Badges are computed by code from confirmed events only (no learned
score, no public numbers). `farmer_badges` keeps award / revoke history so an
admin revoke sticks and every badge is auditable. `trust_flags` holds
suspected rating rings for admin review.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels = None
depends_on = None

ADMIN = "current_setting('app.is_platform_admin', true) = 'true'"
ME = "current_setting('app.current_farmer', true)"
BADGES = ("trusted_renter", "helpful_neighbour")


def upgrade() -> None:
    op.create_table(
        "farmer_badges",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "farmer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("farmers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("badge", sa.String(30), nullable=False),
        sa.Column("awarded_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("awarded_by", sa.String(60), nullable=False),  # 'system' or admin user id
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(60), nullable=True),  # 'system' or admin user id
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("evidence", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint(
            "badge IN (" + ",".join(f"'{b}'" for b in BADGES) + ")",
            name="farmer_badges_badge_check",
        ),
    )
    # one live badge of each kind per farmer
    op.create_index(
        "farmer_badges_live",
        "farmer_badges",
        ["farmer_id", "badge"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.execute("ALTER TABLE farmer_badges ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE farmer_badges FORCE ROW LEVEL SECURITY")
    # Live badges are public to farmers (that's the point); history is admin-only.
    op.execute(f"""CREATE POLICY farmer_badges_read ON farmer_badges FOR SELECT
                   USING ((revoked_at IS NULL AND {ME} <> '') OR {ADMIN})""")
    op.execute(f"""CREATE POLICY farmer_badges_write ON farmer_badges FOR ALL
                   USING ({ADMIN}) WITH CHECK ({ADMIN})""")

    op.create_table(
        "trust_flags",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("farmer_ids", ARRAY(UUID(as_uuid=True)), nullable=False),
        sa.Column("detail", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("closed_by", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('open','closed')", name="trust_flags_status_check"),
    )
    # one open flag per (kind, sorted pair)
    op.create_index(
        "trust_flags_open",
        "trust_flags",
        ["kind", "farmer_ids"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.execute("ALTER TABLE trust_flags ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE trust_flags FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY trust_flags_admin ON trust_flags FOR ALL "
        f"USING ({ADMIN}) WITH CHECK ({ADMIN})"
    )


def downgrade() -> None:
    op.drop_table("trust_flags")
    op.drop_table("farmer_badges")
