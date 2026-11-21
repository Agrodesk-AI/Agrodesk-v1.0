from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer
from app.schemas.customer import CustomerCreateIn, CustomerUpdateIn
from app.security.phone import normalize_phone


async def create_or_get_by_phone(
    session: AsyncSession, dealer_id: UUID, data: CustomerCreateIn
) -> tuple[Customer, bool]:
    """Returns (customer, created). Dedupe on (dealer_id, phone)."""
    phone = normalize_phone(data.phone)
    existing = await session.scalar(
        select(Customer).where(Customer.dealer_id == dealer_id, Customer.phone == phone)
    )
    if existing is not None:
        return existing, False
    cust = Customer(
        dealer_id=dealer_id,
        name=data.name,
        phone=phone,
        language=data.language,
        village=data.village,
        farm_size_acres=data.farm_size_acres,
        crop=data.crop,
        notes=data.notes,
        consent_whatsapp=data.consent_whatsapp,
        consent_call=data.consent_call,
    )
    session.add(cust)
    await session.flush()
    return cust, True


async def get(session: AsyncSession, customer_id: UUID) -> Customer | None:
    return await session.scalar(select(Customer).where(Customer.id == customer_id))


async def update(session: AsyncSession, customer: Customer, data: CustomerUpdateIn) -> Customer:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    await session.flush()
    return customer


async def opt_out(session: AsyncSession, customer: Customer) -> Customer:
    customer.opted_out_at = datetime.now(UTC)
    customer.consent_whatsapp = False
    customer.consent_call = False
    await session.flush()
    return customer
