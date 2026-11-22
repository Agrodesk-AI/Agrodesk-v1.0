"""community feed: typed posts, replies, helpful marks, reports, moderation queue

Revision ID: 0009
Revises: 0008

Design §3.4 + §3.8.
- Posts / replies: published rows readable by every farmer, own rows always.
  Writes go through the service (platform context) because every write also
  touches the moderation queue, which farmers can't read.
- helpful_count / reply_count are kept by triggers so readers never need
  write access to someone else's post.
- moderation_queue: platform admins only. Audit lives on the row.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels = None
depends_on = None

KINDS = ("ask", "need_equipment", "offer_equipment", "price_report", "scheme_alert", "experience")
ME = "current_setting('app.current_farmer', true)"
ADMIN = "current_setting('app.is_platform_admin', true) = 'true'"


def _in(values) -> str:
    return ",".join(f"'{v}'" for v in values)


def _pk() -> sa.Column:
    return sa.Column(
        "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def _farmer(name: str = "farmer_id") -> sa.Column:
    return sa.Column(
        name, UUID(as_uuid=True), sa.ForeignKey("farmers.id", ondelete="CASCADE"), nullable=False
    )


def _ts(name: str, nullable: bool = True, now: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.TIMESTAMP(timezone=True),
        nullable=nullable,
        server_default=sa.text("now()") if now else None,
    )


def _rls(table: str, read: str, write: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING (({read}) OR {ADMIN})")
    op.execute(f"""CREATE POLICY {table}_write ON {table} FOR ALL
                   USING (({write}) OR {ADMIN}) WITH CHECK (({write}) OR {ADMIN})""")


def upgrade() -> None:
    op.create_table(
        "posts",
        _pk(),
        _farmer(),
        sa.Column("author_name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("tehsil_id", sa.Integer(), sa.ForeignKey("tehsils.id"), nullable=False),
        sa.Column("village_id", sa.Integer(), sa.ForeignKey("villages.id"), nullable=True),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("tags", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(12), nullable=False, server_default="published"),
        sa.Column("moderation", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("helpful_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reply_count", sa.Integer(), nullable=False, server_default="0"),
        _ts("expires_at"),
        _ts("created_at", nullable=False, now=True),
        _ts("updated_at", nullable=False, now=True),
        sa.CheckConstraint(f"kind IN ({_in(KINDS)})", name="posts_kind_check"),
        sa.CheckConstraint(
            "status IN ('published','in_review','removed','archived')", name="posts_status_check"
        ),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 2000", name="posts_body_len"),
    )
    op.create_index(
        "posts_feed_idx",
        "posts",
        ["tehsil_id", "created_at"],
        postgresql_where=sa.text("status = 'published'"),
    )
    op.create_index("posts_author_idx", "posts", ["farmer_id", "created_at"])
    _rls(
        "posts",
        read=f"(status = 'published' AND {ME} <> '') OR farmer_id::text = {ME}",
        write=f"farmer_id::text = {ME}",
    )

    op.create_table(
        "post_replies",
        _pk(),
        sa.Column(
            "post_id",
            UUID(as_uuid=True),
            sa.ForeignKey("posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _farmer(),
        sa.Column("author_name", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="published"),
        sa.Column("moderation", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        _ts("created_at", nullable=False, now=True),
        sa.CheckConstraint(
            "status IN ('published','in_review','removed')", name="post_replies_status_check"
        ),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 1000", name="post_replies_body_len"),
    )
    op.create_index("post_replies_post_idx", "post_replies", ["post_id", "created_at"])
    _rls(
        "post_replies",
        read=f"(status = 'published' AND {ME} <> '') OR farmer_id::text = {ME}",
        write=f"farmer_id::text = {ME}",
    )

    op.create_table(
        "post_helpful",
        sa.Column(
            "post_id",
            UUID(as_uuid=True),
            sa.ForeignKey("posts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "farmer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("farmers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        _ts("created_at", nullable=False, now=True),
    )
    _rls("post_helpful", read=f"farmer_id::text = {ME}", write=f"farmer_id::text = {ME}")

    op.create_table(
        "content_reports",
        _pk(),
        sa.Column("target_type", sa.String(10), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=False),
        _farmer("reporter_farmer_id"),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("created_at", nullable=False, now=True),
        sa.CheckConstraint("target_type IN ('post','reply')", name="content_reports_type_check"),
        sa.CheckConstraint(
            "reason IN ('spam','scam','abuse','wrong_info','other')",
            name="content_reports_reason_check",
        ),
        sa.UniqueConstraint(
            "target_type", "target_id", "reporter_farmer_id", name="content_reports_once"
        ),
    )
    _rls(
        "content_reports",
        read=f"reporter_farmer_id::text = {ME}",
        write=f"reporter_farmer_id::text = {ME}",
    )

    op.create_table(
        "moderation_queue",
        _pk(),
        sa.Column("target_type", sa.String(10), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("reasons", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        _ts("sla_due_at", nullable=False),
        sa.Column("decision", sa.String(10), nullable=True),
        sa.Column("decided_by", UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("decided_at"),
        _ts("created_at", nullable=False, now=True),
        sa.CheckConstraint("status IN ('open','closed')", name="moderation_queue_status_check"),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('approve','remove')",
            name="moderation_queue_decision_check",
        ),
    )
    # at most one open item per piece of content
    op.create_index(
        "moderation_queue_open_target",
        "moderation_queue",
        ["target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        "moderation_queue_due_idx",
        "moderation_queue",
        ["sla_due_at"],
        postgresql_where=sa.text("status = 'open'"),
    )
    _rls("moderation_queue", read="false", write="false")  # admin only

    # Counters maintained by triggers (SECURITY DEFINER: the marker can't write the post).
    op.execute("""
        CREATE FUNCTION posts_bump_counter() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
        DECLARE col text := TG_ARGV[0]; pid uuid; delta int;
        BEGIN
            IF TG_OP = 'INSERT' THEN pid := NEW.post_id; delta := 1;
            ELSE pid := OLD.post_id; delta := -1; END IF;
            EXECUTE format('UPDATE posts SET %I = GREATEST(%I + $1, 0) WHERE id = $2', col, col)
                USING delta, pid;
            RETURN NULL;
        END $$
    """)
    op.execute("""CREATE TRIGGER post_helpful_count AFTER INSERT OR DELETE ON post_helpful
                  FOR EACH ROW EXECUTE FUNCTION posts_bump_counter('helpful_count')""")
    op.execute("""CREATE TRIGGER post_reply_count AFTER INSERT OR DELETE ON post_replies
                  FOR EACH ROW EXECUTE FUNCTION posts_bump_counter('reply_count')""")


def downgrade() -> None:
    for t in ("moderation_queue", "content_reports", "post_helpful", "post_replies", "posts"):
        op.drop_table(t)
    op.execute("DROP FUNCTION IF EXISTS posts_bump_counter()")
