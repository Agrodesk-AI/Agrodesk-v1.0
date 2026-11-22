"""Shared tractor catalogue + per-dealer price/offer overlay."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DealerModel, TractorCatalogue


async def list_for_dealer(session: AsyncSession, dealer_id: UUID) -> list[dict]:
    """Returns shared catalogue rows joined with this dealer's overlay.
    Expired offers (valid_till < today) are filtered out of the overlay but
    the shared row is still returned (price falls back to None)."""
    today = date.today()
    catalogue_rows = (await session.scalars(
        select(TractorCatalogue).order_by(TractorCatalogue.brand, TractorCatalogue.model)
    )).all()
    overlay_rows = (await session.scalars(
        select(DealerModel).where(DealerModel.dealer_id == dealer_id)
    )).all()
    by_cat = {str(o.catalogue_id): o for o in overlay_rows}
    out: list[dict] = []
    for c in catalogue_rows:
        o = by_cat.get(str(c.id))
        expired = o is not None and o.valid_till is not None and o.valid_till < today
        out.append({
            "catalogue_id": str(c.id),
            "brand": c.brand,
            "model": c.model,
            "hp": c.hp,
            "specs": c.specs,
            "price_min": float(o.price_min) if (o and o.price_min and not expired) else None,
            "price_max": float(o.price_max) if (o and o.price_max and not expired) else None,
            "offers": {} if (o is None or expired) else (o.offers or {}),
            "valid_till": (
                o.valid_till.isoformat()
                if (o is not None and not expired and o.valid_till is not None)
                else None
            ),
            "overlay_expired": bool(expired),
        })
    return out


async def upsert_dealer_overlay(
    session: AsyncSession,
    *,
    dealer_id: UUID,
    catalogue_id: UUID,
    price_min: Decimal | None,
    price_max: Decimal | None,
    offers: dict,
    valid_till: date | None,
) -> DealerModel:
    existing = await session.scalar(
        select(DealerModel).where(
            DealerModel.dealer_id == dealer_id,
            DealerModel.catalogue_id == catalogue_id,
        )
    )
    if existing is not None:
        existing.price_min = price_min
        existing.price_max = price_max
        existing.offers = offers or {}
        existing.valid_till = valid_till
        await session.flush()
        return existing
    row = DealerModel(
        dealer_id=dealer_id, catalogue_id=catalogue_id,
        price_min=price_min, price_max=price_max,
        offers=offers or {}, valid_till=valid_till,
    )
    session.add(row)
    await session.flush()
    return row
