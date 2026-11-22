"""Reads over the location hierarchy + the "nearby" rule.

"Nearby" is administrative, not Euclidean (SYSTEM_DESIGN_v2 §3.2):
    rank 0  -> the tehsil itself
    rank N  -> curated neighbours from tehsil_neighbours (rank >= 1)
    rank 99 -> fallback: other tehsils in the same district, used only when
               no neighbour rows exist yet for this tehsil. Lets every tehsil
               in India work on day one while ops curate neighbour maps.
"""

from sqlalchemy import Text, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import District, State, Tehsil, TehsilNeighbour, Village

FALLBACK_RANK = 99


async def list_states(session: AsyncSession) -> list[State]:
    return list((await session.scalars(select(State).order_by(State.name_en))).all())


async def list_districts(session: AsyncSession, state_id: int) -> list[District]:
    q = select(District).where(District.state_id == state_id).order_by(District.name_en)
    return list((await session.scalars(q)).all())


async def list_tehsils(session: AsyncSession, district_id: int) -> list[Tehsil]:
    q = select(Tehsil).where(Tehsil.district_id == district_id).order_by(Tehsil.name_en)
    return list((await session.scalars(q)).all())


async def search_villages(
    session: AsyncSession,
    *,
    q: str | None,
    tehsil_id: int | None,
    district_id: int | None,
    limit: int = 20,
) -> list[Village]:
    stmt = select(Village)
    if tehsil_id is not None:
        stmt = stmt.where(Village.tehsil_id == tehsil_id)
    elif district_id is not None:
        stmt = stmt.join(Tehsil, Tehsil.id == Village.tehsil_id).where(
            Tehsil.district_id == district_id
        )
    if q:
        needle = q.strip().lower()
        pattern = "%" + _like_escape(needle) + "%"
        # English name (trigram index) or any local-language name. jsonb::text keeps
        # non-ASCII as-is, so Devanagari / Tamil / etc. match directly.
        stmt = stmt.where(
            or_(
                func.lower(Village.name_en).like(pattern, escape="\\"),
                Village.names.cast(Text).ilike(pattern, escape="\\"),
            )
        )
        # Prefix matches first, then alphabetical.
        stmt = stmt.order_by(
            func.lower(Village.name_en).startswith(needle, autoescape=True).desc(),
            Village.name_en,
        )
    else:
        stmt = stmt.order_by(Village.name_en)
    return list((await session.scalars(stmt.limit(limit))).all())


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def get_tehsil_chain(session: AsyncSession, tehsil_id: int):
    row = (
        await session.execute(
            select(Tehsil, District, State)
            .join(District, District.id == Tehsil.district_id)
            .join(State, State.id == District.state_id)
            .where(Tehsil.id == tehsil_id)
        )
    ).first()
    return row  # (Tehsil, District, State) or None


async def nearby_tehsils(session: AsyncSession, tehsil_id: int) -> list[tuple[Tehsil, int]]:
    """[(tehsil, rank)] ordered by rank, self first. Empty if tehsil unknown."""
    me = await session.get(Tehsil, tehsil_id)
    if me is None:
        return []
    curated = (
        await session.execute(
            select(Tehsil, TehsilNeighbour.rank)
            .join(TehsilNeighbour, TehsilNeighbour.neighbour_tehsil_id == Tehsil.id)
            .where(TehsilNeighbour.tehsil_id == tehsil_id)
            .order_by(TehsilNeighbour.rank, Tehsil.name_en)
        )
    ).all()
    result: list[tuple[Tehsil, int]] = [(me, 0)]
    if curated:
        result += [(t, r) for t, r in curated]
        return result
    same_district = (
        await session.scalars(
            select(Tehsil)
            .where(Tehsil.district_id == me.district_id, Tehsil.id != tehsil_id)
            .order_by(Tehsil.name_en)
        )
    ).all()
    result += [(t, FALLBACK_RANK) for t in same_district]
    return result


async def set_neighbours(
    session: AsyncSession, tehsil_id: int, neighbours: list[tuple[int, int]]
) -> None:
    """Replace this tehsil's neighbour set (both directions). neighbours = [(id, rank)]."""
    await session.execute(
        delete(TehsilNeighbour).where(
            or_(
                TehsilNeighbour.tehsil_id == tehsil_id,
                TehsilNeighbour.neighbour_tehsil_id == tehsil_id,
            )
        )
    )
    rows = []
    for nid, rank in neighbours:
        if nid == tehsil_id:
            continue
        rows.append(
            {"tehsil_id": tehsil_id, "neighbour_tehsil_id": nid, "rank": rank, "source": "admin"}
        )
        rows.append(
            {"tehsil_id": nid, "neighbour_tehsil_id": tehsil_id, "rank": rank, "source": "admin"}
        )
    if rows:
        await session.execute(
            insert(TehsilNeighbour.__table__).values(rows).on_conflict_do_nothing()
        )
