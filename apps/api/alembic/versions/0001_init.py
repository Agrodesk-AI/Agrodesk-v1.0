"""init: dealers, users, otp_codes with RLS

Revision ID: 0001
Revises:
Create Date: 2026-11-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "dealers",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("brands", sa.dialects.postgresql.ARRAY(sa.String(100)),
                  nullable=False, server_default="{}"),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("district", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("default_language", sa.String(10), nullable=False, server_default="mr"),
        sa.Column("whatsapp_number", sa.String(20), nullable=True),
        sa.Column("business_hours", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dealer_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("dealers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("phone", name="users_phone_key"),
        sa.CheckConstraint(
            "role IN ('owner','sales','recovery','service','platform_admin')",
            name="users_role_check",
        ),
        sa.CheckConstraint(
            "(role = 'platform_admin' AND dealer_id IS NULL) "
            "OR (role <> 'platform_admin' AND dealer_id IS NOT NULL)",
            name="users_dealer_role_check",
        ),
    )
    op.create_index("users_dealer_id_idx", "users", ["dealer_id"])

    op.create_table(
        "otp_codes",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("code_hash", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("otp_phone_created_idx", "otp_codes", ["phone", "created_at"])

    # --- RLS on tenant tables ---
    for tbl in ("users",):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {tbl}_tenant_read ON {tbl} FOR SELECT
            USING (
                dealer_id::text = current_setting('app.current_dealer', true)
                OR current_setting('app.is_platform_admin', true) = 'true'
            )
        """)
        op.execute(f"""
            CREATE POLICY {tbl}_tenant_write ON {tbl} FOR ALL
            USING (
                dealer_id::text = current_setting('app.current_dealer', true)
                OR current_setting('app.is_platform_admin', true) = 'true'
            )
            WITH CHECK (
                dealer_id::text = current_setting('app.current_dealer', true)
                OR current_setting('app.is_platform_admin', true) = 'true'
            )
        """)

    # dealers: only platform admin can read/write for now (scoped via is_platform_admin
    # OR by owning user when we add a self-read route; for E1 platform admin suffices)
    op.execute("ALTER TABLE dealers ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE dealers FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY dealers_tenant_read ON dealers FOR SELECT
        USING (
            id::text = current_setting('app.current_dealer', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
    """)
    op.execute("""
        CREATE POLICY dealers_tenant_write ON dealers FOR ALL
        USING (current_setting('app.is_platform_admin', true) = 'true')
        WITH CHECK (current_setting('app.is_platform_admin', true) = 'true')
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS users_tenant_read ON users")
    op.execute("DROP POLICY IF EXISTS users_tenant_write ON users")
    op.execute("DROP POLICY IF EXISTS dealers_tenant_read ON dealers")
    op.execute("DROP POLICY IF EXISTS dealers_tenant_write ON dealers")
    op.drop_table("otp_codes")
    op.drop_table("users")
    op.drop_table("dealers")
