"""consented lead routing: dealer verification, farmer consents, buying interests, routes

Revision ID: 0007
Revises: 0006

Design §3.3. A farmer's buying interest (with a stored consent) is routed to the
best verified dealer near them; if the dealer doesn't act within the SLA the
interest moves to the next candidate (max 3 re-routes), then to a wait list.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels = None
depends_on = None

_OLD_SOURCES = ("facebook", "walk_in", "referral", "oem", "other")
_NEW_SOURCES = _OLD_SOURCES + ("agrodesk_guide",)
_OLD_EVENTS = (
    "created",
    "stage_changed",
    "assigned",
    "next_action_scheduled",
    "note",
    "call_made",
    "task_completed",
    "opted_out",
)
_NEW_EVENTS = _OLD_EVENTS + ("routed", "re_routed", "farmer_cancelled")


def _in(values: tuple[str, ...]) -> str:
    return ",".join(f"'{v}'" for v in values)


def _ts(name: str, nullable: bool = True, now: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.TIMESTAMP(timezone=True),
        nullable=nullable,
        server_default=sa.text("now()") if now else None,
    )


def _farmer_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY {table}_farmer ON {table} FOR ALL
        USING (
            farmer_id::text = current_setting('app.current_farmer', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
        WITH CHECK (
            farmer_id::text = current_setting('app.current_farmer', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
    """)


def upgrade() -> None:
    # --- dealers: verification + routing capacity ---
    op.add_column("dealers", _ts("verified_at"))
    op.add_column("dealers", sa.Column("verified_by", UUID(as_uuid=True), nullable=True))
    op.add_column(
        "dealers", sa.Column("routing_daily_cap", sa.Integer(), nullable=False, server_default="20")
    )

    # --- leads: new source + link back to the interest ---
    op.drop_constraint("leads_source_check", "leads", type_="check")
    op.create_check_constraint("leads_source_check", "leads", f"source IN ({_in(_NEW_SOURCES)})")
    op.drop_constraint("lead_events_type_check", "lead_events", type_="check")
    op.create_check_constraint(
        "lead_events_type_check", "lead_events", f"type IN ({_in(_NEW_EVENTS)})"
    )

    # --- farmer consents (farmer-scoped; dealer `consents` stay dealer-scoped) ---
    op.create_table(
        "farmer_consents",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "farmer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("farmers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("text_version", sa.String(20), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("text_shown", sa.Text(), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        _ts("recorded_at", nullable=False, now=True),
    )
    op.create_index("farmer_consents_farmer_idx", "farmer_consents", ["farmer_id"])
    _farmer_rls("farmer_consents")

    # --- buying interests (farmer-scoped) ---
    op.create_table(
        "buying_interests",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "farmer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("farmers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "consent_id", UUID(as_uuid=True), sa.ForeignKey("farmer_consents.id"), nullable=False
        ),
        sa.Column("tehsil_id", sa.Integer(), sa.ForeignKey("tehsils.id"), nullable=False),
        sa.Column("brand_hint", sa.String(100), nullable=True),
        sa.Column("hp_min", sa.SmallInteger(), nullable=True),
        sa.Column("hp_max", sa.SmallInteger(), nullable=True),
        sa.Column("timeline", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="routing"),
        sa.Column(
            "candidate_dealer_ids", ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"
        ),
        sa.Column("reroute_count", sa.SmallInteger(), nullable=False, server_default="0"),
        # snapshot of the current dealer so the farmer can see it without reading
        # dealer-scoped tables (dealer business name + number are public info)
        sa.Column("current_dealer_id", UUID(as_uuid=True), nullable=True),
        sa.Column("current_dealer_name", sa.String(200), nullable=True),
        sa.Column("current_dealer_phone", sa.String(20), nullable=True),
        _ts("created_at", nullable=False, now=True),
        _ts("updated_at", nullable=False, now=True),
        sa.CheckConstraint(
            "status IN ('routing','assigned','waitlist','cancelled','closed')",
            name="buying_interests_status_check",
        ),
        sa.CheckConstraint(
            "timeline IN ('now','1_3_months','3_6_months','later')",
            name="buying_interests_timeline_check",
        ),
    )
    op.create_index("buying_interests_farmer_idx", "buying_interests", ["farmer_id", "created_at"])
    _farmer_rls("buying_interests")

    # --- one row per dealer attempt (dealer-scoped) ---
    op.create_table(
        "lead_routes",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "interest_id",
            UUID(as_uuid=True),
            sa.ForeignKey("buying_interests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dealer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("dealers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lead_id",
            UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("rank_reason", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        _ts("sla_due_at", nullable=False),
        _ts("responded_at"),
        _ts("closed_at"),
        _ts("created_at", nullable=False, now=True),
        sa.CheckConstraint(
            "status IN ('pending','responded','re_routed','closed')",
            name="lead_routes_status_check",
        ),
        sa.UniqueConstraint("lead_id", name="lead_routes_lead_key"),
    )
    op.create_index(
        "lead_routes_due_idx",
        "lead_routes",
        ["sla_due_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("lead_routes_dealer_idx", "lead_routes", ["dealer_id", "created_at"])
    op.execute("ALTER TABLE lead_routes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE lead_routes FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY lead_routes_dealer ON lead_routes FOR ALL
        USING (
            dealer_id::text = current_setting('app.current_dealer', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
        WITH CHECK (
            dealer_id::text = current_setting('app.current_dealer', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS lead_routes_dealer ON lead_routes")
    op.drop_table("lead_routes")
    op.execute("DROP POLICY IF EXISTS buying_interests_farmer ON buying_interests")
    op.drop_table("buying_interests")
    op.execute("DROP POLICY IF EXISTS farmer_consents_farmer ON farmer_consents")
    op.drop_table("farmer_consents")
    op.execute("DELETE FROM lead_events WHERE type IN ('routed','re_routed','farmer_cancelled')")
    op.drop_constraint("lead_events_type_check", "lead_events", type_="check")
    op.create_check_constraint(
        "lead_events_type_check", "lead_events", f"type IN ({_in(_OLD_EVENTS)})"
    )
    op.execute("DELETE FROM leads WHERE source = 'agrodesk_guide'")
    op.drop_constraint("leads_source_check", "leads", type_="check")
    op.create_check_constraint("leads_source_check", "leads", f"source IN ({_in(_OLD_SOURCES)})")
    op.drop_column("dealers", "routing_daily_cap")
    op.drop_column("dealers", "verified_by")
    op.drop_column("dealers", "verified_at")
