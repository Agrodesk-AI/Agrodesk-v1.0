"""conversations, messages, outbox with RLS

Revision ID: 0004
Revises: 0003
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels = None
depends_on = None


_CHANNELS = ("whatsapp", "voice", "sms", "app")
_DIRECTIONS = ("inbound", "outbound")
_MESSAGE_STATUSES = ("queued", "sent", "delivered", "read", "failed", "rejected")
_OUTBOX_STATUSES = ("pending", "sent", "failed", "rejected")
_OUTBOX_KINDS = ("wa_session", "wa_template")


def _apply_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY {table}_tenant_read ON {table} FOR SELECT
        USING (
            dealer_id::text = current_setting('app.current_dealer', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
    """)
    op.execute(f"""
        CREATE POLICY {table}_tenant_write ON {table} FOR ALL
        USING (
            dealer_id::text = current_setting('app.current_dealer', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
        WITH CHECK (
            dealer_id::text = current_setting('app.current_dealer', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
    """)


def upgrade() -> None:
    chans = ",".join(f"'{c}'" for c in _CHANNELS)
    op.create_table(
        "conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dealer_id", UUID(as_uuid=True),
                  sa.ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True),
                  sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("thread_id", sa.String(100)),
        sa.Column("summary", sa.Text()),
        sa.Column("last_message_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_customer_message_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("dealer_id", "customer_id", "channel",
                            name="conversations_tenant_channel_key"),
        sa.CheckConstraint(f"channel IN ({chans})", name="conversations_channel_check"),
    )
    _apply_rls("conversations")

    dirs = ",".join(f"'{d}'" for d in _DIRECTIONS)
    statuses = ",".join(f"'{s}'" for s in _MESSAGE_STATUSES)
    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dealer_id", UUID(as_uuid=True),
                  sa.ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True),
                  sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("content", sa.Text()),
        sa.Column("media_url", sa.Text()),
        sa.Column("transcript", sa.Text()),
        sa.Column("template_name", sa.String(100)),
        sa.Column("template_vars", JSONB()),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("provider_message_id", sa.String(200)),
        sa.Column("idempotency_key", sa.String(200)),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(f"direction IN ({dirs})", name="messages_direction_check"),
        sa.CheckConstraint(f"status IN ({statuses})", name="messages_status_check"),
    )
    # Unique on provider_message_id globally (BSP-wide) to guarantee webhook idempotency
    op.execute("""
        CREATE UNIQUE INDEX messages_provider_message_id_key
        ON messages (provider_message_id) WHERE provider_message_id IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX messages_idempotency_key_key
        ON messages (idempotency_key) WHERE idempotency_key IS NOT NULL
    """)
    op.create_index("messages_conversation_time_idx", "messages",
                    ["conversation_id", "occurred_at"])
    _apply_rls("messages")

    kinds = ",".join(f"'{k}'" for k in _OUTBOX_KINDS)
    obstatus = ",".join(f"'{s}'" for s in _OUTBOX_STATUSES)
    op.create_table(
        "outbox",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dealer_id", UUID(as_uuid=True),
                  sa.ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", UUID(as_uuid=True),
                  sa.ForeignKey("leads.id", ondelete="SET NULL")),
        sa.Column("customer_id", UUID(as_uuid=True),
                  sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_attempt_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("last_error", sa.Text()),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("message_id", UUID(as_uuid=True),
                  sa.ForeignKey("messages.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("idempotency_key", name="outbox_idempotency_key_key"),
        sa.CheckConstraint(f"kind IN ({kinds})", name="outbox_kind_check"),
        sa.CheckConstraint(f"status IN ({obstatus})", name="outbox_status_check"),
    )
    op.create_index("outbox_poll_idx", "outbox", ["status", "next_attempt_at"])
    _apply_rls("outbox")


def downgrade() -> None:
    op.drop_table("outbox")
    op.drop_table("messages")
    op.drop_table("conversations")
