"""customers, consents, leads, lead_events, tasks with RLS

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels = None
depends_on = None


_STAGES = ("new", "contacted", "qualified", "visit_planned", "negotiation", "won", "lost")
_SOURCES = ("facebook", "walk_in", "referral", "oem", "other")
_SCORES = ("hot", "warm", "dead")
_EVENT_TYPES = (
    "created", "stage_changed", "assigned", "next_action_scheduled",
    "note", "call_made", "task_completed", "opted_out",
)
_TASK_STATUSES = ("pending", "done", "skipped")


def _apply_rls(table: str, write_check_platform_only: bool = False) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY {table}_tenant_read ON {table} FOR SELECT
        USING (
            dealer_id::text = current_setting('app.current_dealer', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
    """)
    if write_check_platform_only:
        write_clause = "current_setting('app.is_platform_admin', true) = 'true'"
    else:
        write_clause = (
            "dealer_id::text = current_setting('app.current_dealer', true) "
            "OR current_setting('app.is_platform_admin', true) = 'true'"
        )
    op.execute(f"""
        CREATE POLICY {table}_tenant_write ON {table} FOR ALL
        USING ({write_clause})
        WITH CHECK ({write_clause})
    """)


def upgrade() -> None:
    # --- customers ---
    op.create_table(
        "customers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dealer_id", UUID(as_uuid=True),
                  sa.ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="mr"),
        sa.Column("village", sa.String(200)),
        sa.Column("farm_size_acres", sa.Numeric(8, 2)),
        sa.Column("crop", sa.String(100)),
        sa.Column("notes", sa.Text),
        sa.Column("consent_whatsapp", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("consent_call", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("opted_out_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("dealer_id", "phone", name="customers_dealer_phone_key"),
    )
    _apply_rls("customers")

    # --- consents ---
    op.create_table(
        "consents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dealer_id", UUID(as_uuid=True),
                  sa.ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True),
                  sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(100), nullable=False),
        sa.Column("text_shown", sa.Text, nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("consents_dealer_customer_idx", "consents",
                    ["dealer_id", "customer_id", "recorded_at"])
    _apply_rls("consents")

    # --- leads ---
    stages_list = ",".join(f"'{s}'" for s in _STAGES)
    sources_list = ",".join(f"'{s}'" for s in _SOURCES)
    scores_list = ",".join(f"'{s}'" for s in _SCORES)
    op.create_table(
        "leads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dealer_id", UUID(as_uuid=True),
                  sa.ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True),
                  sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("referrer_customer_id", UUID(as_uuid=True),
                  sa.ForeignKey("customers.id", ondelete="SET NULL")),
        sa.Column("model_interest", sa.String(200)),
        sa.Column("stage", sa.String(20), nullable=False, server_default="new"),
        sa.Column("score", sa.String(10)),
        sa.Column("owner_user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("next_action_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("lost_reason", sa.Text),
        sa.Column("won_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("campaign", sa.String(200)),
        sa.Column("ad_name", sa.String(200)),
        sa.Column("created_via", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(f"stage IN ({stages_list})", name="leads_stage_check"),
        sa.CheckConstraint(f"source IN ({sources_list})", name="leads_source_check"),
        sa.CheckConstraint(f"score IS NULL OR score IN ({scores_list})",
                           name="leads_score_check"),
        sa.CheckConstraint("stage <> 'lost' OR lost_reason IS NOT NULL",
                           name="leads_lost_requires_reason"),
        sa.CheckConstraint("stage <> 'won' OR won_at IS NOT NULL",
                           name="leads_won_requires_won_at"),
    )
    op.create_index("leads_dealer_next_action_idx", "leads", ["dealer_id", "next_action_at"])
    op.create_index("leads_dealer_stage_idx", "leads", ["dealer_id", "stage"])
    op.create_index("leads_dealer_owner_next_idx", "leads",
                    ["dealer_id", "owner_user_id", "next_action_at"])
    op.create_index("leads_dealer_customer_idx", "leads", ["dealer_id", "customer_id"])
    _apply_rls("leads")

    # --- lead_events ---
    event_types_list = ",".join(f"'{t}'" for t in _EVENT_TYPES)
    op.create_table(
        "lead_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dealer_id", UUID(as_uuid=True),
                  sa.ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", UUID(as_uuid=True),
                  sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True)),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(f"type IN ({event_types_list})", name="lead_events_type_check"),
        sa.CheckConstraint("actor_type IN ('user','agent','system')",
                           name="lead_events_actor_type_check"),
    )
    op.create_index("lead_events_dealer_lead_time_idx", "lead_events",
                    ["dealer_id", "lead_id", "occurred_at"])
    _apply_rls("lead_events")

    # --- tasks ---
    task_statuses_list = ",".join(f"'{s}'" for s in _TASK_STATUSES)
    op.create_table(
        "tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dealer_id", UUID(as_uuid=True),
                  sa.ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", UUID(as_uuid=True),
                  sa.ForeignKey("leads.id", ondelete="CASCADE")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("due_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("type", sa.String(30), nullable=False, server_default="follow_up"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("outcome", sa.String(30)),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(f"status IN ({task_statuses_list})", name="tasks_status_check"),
    )
    op.create_index("tasks_dealer_user_due_idx", "tasks", ["dealer_id", "user_id", "due_at"])
    op.create_index("tasks_dealer_lead_idx", "tasks", ["dealer_id", "lead_id"])
    _apply_rls("tasks")


def downgrade() -> None:
    for t in ("tasks", "lead_events", "leads", "consents", "customers"):
        op.execute(f"DROP POLICY IF EXISTS {t}_tenant_read ON {t}")
        op.execute(f"DROP POLICY IF EXISTS {t}_tenant_write ON {t}")
        op.drop_table(t)
