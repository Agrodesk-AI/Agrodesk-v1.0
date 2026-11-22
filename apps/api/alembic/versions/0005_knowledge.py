"""knowledge base: pgvector + shared catalogue

Revision ID: 0005
Revises: 0004

Requires the `vector` extension (ships with the pgvector/pgvector:pg16 image
used by docker-compose). Install on managed Postgres: `CREATE EXTENSION vector`.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels = None
depends_on = None


def _apply_rls(table: str, allow_shared_read: bool = False) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    read_clause = (
        "dealer_id::text = current_setting('app.current_dealer', true) "
        "OR current_setting('app.is_platform_admin', true) = 'true'"
    )
    if allow_shared_read:
        read_clause = f"dealer_id IS NULL OR {read_clause}"
    op.execute(f"CREATE POLICY {table}_tenant_read ON {table} FOR SELECT USING ({read_clause})")
    op.execute(f"""
        CREATE POLICY {table}_tenant_write ON {table} FOR ALL
        USING (
            dealer_id::text = current_setting('app.current_dealer', true)
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
        WITH CHECK (
            current_setting('app.is_platform_admin', true) = 'true'
            OR (
                dealer_id IS NOT NULL
                AND dealer_id::text = current_setting('app.current_dealer', true)
            )
        )
    """)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "tractor_catalogue",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("brand", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("hp", sa.Integer()),
        sa.Column("specs", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source", sa.String(200)),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("brand", "model", name="tractor_catalogue_brand_model_key"),
    )
    op.execute("ALTER TABLE tractor_catalogue ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tractor_catalogue FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY tractor_catalogue_read ON tractor_catalogue FOR SELECT USING (true)")
    op.execute("""
        CREATE POLICY tractor_catalogue_write ON tractor_catalogue FOR ALL
        USING (current_setting('app.is_platform_admin', true) = 'true')
        WITH CHECK (current_setting('app.is_platform_admin', true) = 'true')
    """)

    op.create_table(
        "dealer_models",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dealer_id", UUID(as_uuid=True),
                  sa.ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("catalogue_id", UUID(as_uuid=True),
                  sa.ForeignKey("tractor_catalogue.id", ondelete="CASCADE"), nullable=False),
        sa.Column("price_min", sa.Numeric(12, 2)),
        sa.Column("price_max", sa.Numeric(12, 2)),
        sa.Column("offers", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("valid_till", sa.Date()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("dealer_id", "catalogue_id", name="dealer_models_tenant_cat_key"),
    )
    _apply_rls("dealer_models", allow_shared_read=False)

    op.create_table(
        "kb_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dealer_id", UUID(as_uuid=True),
                  sa.ForeignKey("dealers.id", ondelete="CASCADE")),
        sa.Column("title", sa.String(400), nullable=False),
        sa.Column("source", sa.String(400)),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("tags", ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("last_verified_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    _apply_rls("kb_documents", allow_shared_read=True)

    op.execute("""
        CREATE TABLE kb_chunks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            dealer_id uuid REFERENCES dealers(id) ON DELETE CASCADE,
            document_id uuid NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
            text text NOT NULL,
            embedding vector(384) NOT NULL,
            meta jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.create_index("kb_chunks_document_idx", "kb_chunks", ["document_id"])
    op.create_index("kb_chunks_dealer_idx", "kb_chunks", ["dealer_id"])
    _apply_rls("kb_chunks", allow_shared_read=True)
    # IVFFlat index is added later when there are > ~10k rows:
    #   CREATE INDEX kb_chunks_embedding_idx ON kb_chunks
    #     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);


def downgrade() -> None:
    op.execute("DROP TABLE kb_chunks")
    op.drop_table("kb_documents")
    op.drop_table("dealer_models")
    op.drop_table("tractor_catalogue")
