from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dealer, User
from app.schemas.dealer import DealerCreateIn
from app.security.phone import normalize_phone


async def create_dealer_with_owner(session: AsyncSession, data: DealerCreateIn) -> tuple[Dealer, User]:
    dealer = Dealer(
        name=data.name,
        brands=data.brands,
        city=data.city,
        district=data.district,
        state=data.state,
        default_language=data.default_language,
        whatsapp_number=data.whatsapp_number,
    )
    session.add(dealer)
    await session.flush()

    owner = User(
        dealer_id=dealer.id,
        name=data.owner_name,
        phone=normalize_phone(data.owner_phone),
        role="owner",
    )
    session.add(owner)
    await session.flush()
    return dealer, owner
