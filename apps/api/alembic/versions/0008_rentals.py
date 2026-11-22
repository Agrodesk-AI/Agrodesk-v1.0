"""rental exchange: listings, needs, bookings (state machine), events, ratings

Revision ID: 0008
Revises: 0007

Design §3.5. Farmer-to-farmer equipment rental.
- Listings and open needs are visible to every farmer (that is the marketplace);
  writes only by the owner. Bookings, their history and contact are party-only.
- No double booking: exclusion constraint on (listing, date range) for
  agreed / in_progress bookings.
- No rating without both-side completion: enforced in the service and by a trigger.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels = None
depends_on = None

KINDS = (
    "tractor",
    "rotavator",
    "cultivator",
    "plough",
    "seed_drill",
    "harvester",
    "sprayer",
    "thresher",
    "trolley",
    "baler",
    "other",
)
STATES = (
    "requested",
    "agreed",
    "declined",
    "cancelled",
    "in_progress",
    "completed_by_both",
    "rated",
    "disputed",
    "resolved",
)


def _in(values) -> str:
    return ",".join(f"'{v}'" for v in values)


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def _farmer_fk(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name, UUID(as_uuid=True), sa.ForeignKey("farmers.id", ondelete="CASCADE"), nullable=nullable
    )


def _ts(name: str, nullable: bool = True, now: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.TIMESTAMP(timezone=True),
        nullable=nullable,
        server_default=sa.text("now()") if now else None,
    )


def _rls(table: str, read: str, write: str) -> None:
    admin = "current_setting('app.is_platform_admin', true) = 'true'"
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING (({read}) OR {admin})")
    for cmd in ("INSERT", "UPDATE", "DELETE"):
        using = "" if cmd == "INSERT" else f"USING (({write}) OR {admin})"
        check = "" if cmd == "DELETE" else f"WITH CHECK (({write}) OR {admin})"
        op.execute(f"CREATE POLICY {table}_{cmd.lower()} ON {table} FOR {cmd} {using} {check}")


ME = "current_setting('app.current_farmer', true)"
ANY_FARMER = f"{ME} <> ''"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "equipment_listings",
        _uuid_pk(),
        _farmer_fk("owner_farmer_id"),
        sa.Column("owner_name", sa.String(200), nullable=False),
        sa.Column("tehsil_id", sa.Integer(), sa.ForeignKey("tehsils.id"), nullable=False),
        sa.Column("village_id", sa.Integer(), sa.ForeignKey("villages.id"), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("hp", sa.SmallInteger(), nullable=True),
        sa.Column("rate_paise", sa.Integer(), nullable=False),
        sa.Column("rate_unit", sa.String(10), nullable=False),
        sa.Column("operator_included", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("fuel_included", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        _ts("created_at", nullable=False, now=True),
        _ts("updated_at", nullable=False, now=True),
        sa.CheckConstraint(f"kind IN ({_in(KINDS)})", name="equipment_listings_kind_check"),
        sa.CheckConstraint(
            "rate_unit IN ('hour','day','acre')", name="equipment_listings_unit_check"
        ),
        sa.CheckConstraint("rate_paise > 0", name="equipment_listings_rate_check"),
        sa.CheckConstraint(
            "status IN ('active','paused','removed')", name="equipment_listings_status_check"
        ),
    )
    op.create_index(
        "equipment_listings_area_idx",
        "equipment_listings",
        ["tehsil_id", "kind"],
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index("equipment_listings_owner_idx", "equipment_listings", ["owner_farmer_id"])
    _rls(
        "equipment_listings",
        read=f"(status = 'active' AND {ANY_FARMER}) OR owner_farmer_id::text = {ME}",
        write=f"owner_farmer_id::text = {ME}",
    )

    op.create_table(
        "rental_needs",
        _uuid_pk(),
        _farmer_fk("renter_farmer_id"),
        sa.Column("renter_name", sa.String(200), nullable=False),
        sa.Column("tehsil_id", sa.Integer(), sa.ForeignKey("tehsils.id"), nullable=False),
        sa.Column("village_id", sa.Integer(), sa.ForeignKey("villages.id"), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("acreage", sa.Numeric(7, 2), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("budget_paise", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        _ts("created_at", nullable=False, now=True),
        _ts("updated_at", nullable=False, now=True),
        sa.CheckConstraint(f"kind IN ({_in(KINDS)})", name="rental_needs_kind_check"),
        sa.CheckConstraint("end_date >= start_date", name="rental_needs_dates_check"),
        sa.CheckConstraint(
            "status IN ('open','matched','closed','cancelled')", name="rental_needs_status_check"
        ),
    )
    op.create_index(
        "rental_needs_area_idx",
        "rental_needs",
        ["tehsil_id", "kind"],
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index("rental_needs_renter_idx", "rental_needs", ["renter_farmer_id"])
    _rls(
        "rental_needs",
        read=f"(status = 'open' AND {ANY_FARMER}) OR renter_farmer_id::text = {ME}",
        write=f"renter_farmer_id::text = {ME}",
    )

    op.create_table(
        "rental_bookings",
        _uuid_pk(),
        sa.Column(
            "listing_id",
            UUID(as_uuid=True),
            sa.ForeignKey("equipment_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "need_id",
            UUID(as_uuid=True),
            sa.ForeignKey("rental_needs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _farmer_fk("owner_farmer_id"),
        _farmer_fk("renter_farmer_id"),
        sa.Column("owner_name", sa.String(200), nullable=False),
        sa.Column("renter_name", sa.String(200), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="requested"),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("owner_completed_at"),
        _ts("renter_completed_at"),
        _ts("owner_shared_contact_at"),
        _ts("renter_shared_contact_at"),
        sa.Column("dispute_reason", sa.Text(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        _ts("created_at", nullable=False, now=True),
        _ts("updated_at", nullable=False, now=True),
        sa.CheckConstraint(f"state IN ({_in(STATES)})", name="rental_bookings_state_check"),
        sa.CheckConstraint("end_date >= start_date", name="rental_bookings_dates_check"),
        sa.CheckConstraint("owner_farmer_id <> renter_farmer_id", name="rental_bookings_not_self"),
    )
    op.execute("""
        ALTER TABLE rental_bookings ADD CONSTRAINT rental_bookings_no_overlap
        EXCLUDE USING gist (
            listing_id WITH =,
            daterange(start_date, end_date, '[]') WITH &&
        ) WHERE (state IN ('agreed', 'in_progress'))
    """)
    # Browsing needs "is this listing free on these dates?" without exposing other
    # farmers' bookings (party-only RLS). Returns only a boolean.
    op.execute("""
        CREATE FUNCTION rental_listing_busy(p_listing uuid, p_start date, p_end date)
        RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
            SELECT EXISTS (
                SELECT 1 FROM rental_bookings
                WHERE listing_id = p_listing
                  AND state IN ('agreed', 'in_progress')
                  AND daterange(start_date, end_date, '[]') && daterange(p_start, p_end, '[]')
            )
        $$
    """)
    op.create_index("rental_bookings_owner_idx", "rental_bookings", ["owner_farmer_id"])
    op.create_index("rental_bookings_renter_idx", "rental_bookings", ["renter_farmer_id"])
    party = f"owner_farmer_id::text = {ME} OR renter_farmer_id::text = {ME}"
    _rls("rental_bookings", read=party, write=party)

    op.create_table(
        "rental_booking_events",
        _uuid_pk(),
        sa.Column(
            "booking_id",
            UUID(as_uuid=True),
            sa.ForeignKey("rental_bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _farmer_fk("owner_farmer_id"),
        _farmer_fk("renter_farmer_id"),
        sa.Column("from_state", sa.String(20), nullable=True),
        sa.Column("to_state", sa.String(20), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("actor_farmer_id", UUID(as_uuid=True), nullable=True),  # null = admin/system
        sa.Column("note", sa.Text(), nullable=True),
        _ts("at", nullable=False, now=True),
    )
    op.create_index(
        "rental_booking_events_booking_idx", "rental_booking_events", ["booking_id", "at"]
    )
    _rls("rental_booking_events", read=party, write=party)

    op.create_table(
        "rental_ratings",
        _uuid_pk(),
        sa.Column(
            "booking_id",
            UUID(as_uuid=True),
            sa.ForeignKey("rental_bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _farmer_fk("from_farmer_id"),
        _farmer_fk("to_farmer_id"),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        _ts("created_at", nullable=False, now=True),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="rental_ratings_score_check"),
        sa.UniqueConstraint("booking_id", "from_farmer_id", name="rental_ratings_once"),
    )
    op.create_index("rental_ratings_to_idx", "rental_ratings", ["to_farmer_id"])
    # Ratings are a public trust signal for farmers; only the rater writes.
    _rls("rental_ratings", read=ANY_FARMER, write=f"from_farmer_id::text = {ME}")

    # Trust gate (design §3.5): rating only after both-side completion, only by a
    # party, only about the other party.
    op.execute("""
        CREATE FUNCTION rental_ratings_gate() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
        DECLARE b rental_bookings%ROWTYPE;
        BEGIN
            SELECT * INTO b FROM rental_bookings WHERE id = NEW.booking_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'rating_without_booking' USING ERRCODE = 'check_violation';
            END IF;
            IF b.state NOT IN ('completed_by_both', 'rated') THEN
                RAISE EXCEPTION 'rating_before_completion' USING ERRCODE = 'check_violation';
            END IF;
            IF NOT (
                (NEW.from_farmer_id = b.owner_farmer_id
                    AND NEW.to_farmer_id = b.renter_farmer_id)
                OR (NEW.from_farmer_id = b.renter_farmer_id
                    AND NEW.to_farmer_id = b.owner_farmer_id)
            ) THEN
                RAISE EXCEPTION 'rating_wrong_parties' USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER rental_ratings_gate BEFORE INSERT OR UPDATE ON rental_ratings
        FOR EACH ROW EXECUTE FUNCTION rental_ratings_gate()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS rental_ratings_gate ON rental_ratings")
    op.execute("DROP FUNCTION IF EXISTS rental_ratings_gate()")
    op.execute("DROP FUNCTION IF EXISTS rental_listing_busy(uuid, date, date)")
    for t in (
        "rental_ratings",
        "rental_booking_events",
        "rental_bookings",
        "rental_needs",
        "equipment_listings",
    ):
        op.drop_table(t)  # policies drop with the table
