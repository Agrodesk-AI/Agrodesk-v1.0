"""farmer foundation: all-India location hierarchy, accounts, farmer profiles

Revision ID: 0006
Revises: 0005

Location tables use the official LGD (Local Government Directory) codes as
primary keys, so the importer can upsert by code and every downstream FK is a
stable government identifier. No rows are seeded here: data comes from
`scripts/import_lgd.py` run against LGD CSV exports (all states / UTs).

`names` is JSONB keyed by language code (`{"mr": "...", "hi": "..."}`), so any
Indian language fits without schema changes. `name_en` is always present.

Location tables are public reference data: no RLS. `farmers` and `accounts`
get RLS keyed on the new `app.current_farmer` / `app.current_account` GUCs.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels = None
depends_on = None


def _names_cols() -> list[sa.Column]:
    return [
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("names", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    ]


def _ts_cols() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- location hierarchy (PK = LGD code) ---
    op.create_table(
        "states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        *_names_cols(),
        sa.Column("default_language", sa.String(10), nullable=True),
        *_ts_cols(),
    )
    op.create_table(
        "districts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("state_id", sa.Integer(), sa.ForeignKey("states.id"), nullable=False),
        *_names_cols(),
        *_ts_cols(),
    )
    op.create_index("districts_state_idx", "districts", ["state_id"])
    op.create_table(
        "tehsils",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("district_id", sa.Integer(), sa.ForeignKey("districts.id"), nullable=False),
        *_names_cols(),
        *_ts_cols(),
    )
    op.create_index("tehsils_district_idx", "tehsils", ["district_id"])
    op.create_table(
        "villages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("tehsil_id", sa.Integer(), sa.ForeignKey("tehsils.id"), nullable=False),
        *_names_cols(),
        *_ts_cols(),
    )
    op.create_index("villages_tehsil_idx", "villages", ["tehsil_id"])
    op.execute(
        "CREATE INDEX villages_name_trgm_idx ON villages USING gin (lower(name_en) gin_trgm_ops)"
    )
    op.create_table(
        "tehsil_neighbours",
        sa.Column(
            "tehsil_id",
            sa.Integer(),
            sa.ForeignKey("tehsils.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "neighbour_tehsil_id",
            sa.Integer(),
            sa.ForeignKey("tehsils.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("rank", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("source", sa.String(40), nullable=False, server_default="import"),
        sa.CheckConstraint("tehsil_id <> neighbour_tehsil_id", name="tehsil_neighbours_not_self"),
    )

    # --- dealer service areas (dealer-scoped, RLS) ---
    op.create_table(
        "dealer_service_areas",
        sa.Column(
            "dealer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("dealers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tehsil_id", sa.Integer(), sa.ForeignKey("tehsils.id"), primary_key=True),
        sa.Column("is_home", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("dealer_service_areas_tehsil_idx", "dealer_service_areas", ["tehsil_id"])
    op.execute("ALTER TABLE dealer_service_areas ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE dealer_service_areas FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY dealer_service_areas_tenant ON dealer_service_areas FOR ALL
        USING (
            dealer_id::text = current_setting('app.current_dealer', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
        WITH CHECK (
            dealer_id::text = current_setting('app.current_dealer', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
    """)

    # --- accounts: one per phone ---
    op.create_table(
        "accounts",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("dob", sa.Date(), nullable=True),
        sa.Column("age_verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_ts_cols(),
        sa.UniqueConstraint("phone", name="accounts_phone_key"),
    )
    op.execute("ALTER TABLE accounts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE accounts FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY accounts_self ON accounts FOR ALL
        USING (
            id::text = current_setting('app.current_account', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
        WITH CHECK (
            id::text = current_setting('app.current_account', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
    """)

    # users become dealer/admin profiles of an account
    op.add_column(
        "users",
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("users_account_idx", "users", ["account_id"])
    op.execute("""
        INSERT INTO accounts (phone)
        SELECT DISTINCT phone FROM users
        ON CONFLICT (phone) DO NOTHING
    """)
    op.execute("""
        UPDATE users u SET account_id = a.id FROM accounts a WHERE a.phone = u.phone
    """)

    # --- farmer profiles ---
    op.create_table(
        "farmers",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("tehsil_id", sa.Integer(), sa.ForeignKey("tehsils.id"), nullable=False),
        sa.Column("village_id", sa.Integer(), sa.ForeignKey("villages.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        *_ts_cols(),
        sa.UniqueConstraint("account_id", name="farmers_account_key"),
        sa.CheckConstraint(
            "status IN ('active','suspended','deleted')", name="farmers_status_check"
        ),
    )
    op.create_index("farmers_tehsil_idx", "farmers", ["tehsil_id"])
    op.execute("ALTER TABLE farmers ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE farmers FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY farmers_self ON farmers FOR ALL
        USING (
            id::text = current_setting('app.current_farmer', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
        WITH CHECK (
            id::text = current_setting('app.current_farmer', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS farmers_self ON farmers")
    op.drop_table("farmers")
    op.drop_index("users_account_idx", table_name="users")
    op.drop_column("users", "account_id")
    op.execute("DROP POLICY IF EXISTS accounts_self ON accounts")
    op.drop_table("accounts")
    op.execute("DROP POLICY IF EXISTS dealer_service_areas_tenant ON dealer_service_areas")
    op.drop_table("dealer_service_areas")
    op.drop_table("tehsil_neighbours")
    op.drop_table("villages")
    op.drop_table("tehsils")
    op.drop_table("districts")
    op.drop_table("states")
