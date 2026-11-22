from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Farmer, Village
from app.schemas.farmer import MIN_AGE_YEARS, FarmerOnboardIn, FarmerOut, FarmerUpdateIn
from app.schemas.location import PlaceOut
from app.services import location_service


class FarmerError(Exception):
    def __init__(self, code: str, status: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def age_on(dob: date, today: date) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


async def _check_location(session: AsyncSession, tehsil_id: int, village_id: int | None) -> None:
    if await location_service.get_tehsil_chain(session, tehsil_id) is None:
        raise FarmerError("unknown_tehsil")
    if village_id is not None:
        village = await session.get(Village, village_id)
        if village is None or village.tehsil_id != tehsil_id:
            raise FarmerError("village_not_in_tehsil")


async def onboard(
    session: AsyncSession, account_id: UUID, data: FarmerOnboardIn, *, today: date | None = None
) -> Farmer:
    """Create the farmer profile for an account. Runs in platform context (it is part
    of sign-up, like OTP verify), so every ownership check here is explicit."""
    account = await session.get(Account, account_id)
    if account is None or account.locked:
        raise FarmerError("no_such_account", 401)
    existing = await session.scalar(select(Farmer).where(Farmer.account_id == account_id))
    if existing is not None:
        raise FarmerError("already_onboarded", 409)

    if account.dob is not None and account.dob != data.dob:
        raise FarmerError("dob_mismatch", 409)
    today = today or datetime.now(UTC).date()
    if age_on(data.dob, today) < MIN_AGE_YEARS:
        # Self-declared DOB + OTP; legal review on stronger checks is open (design §3.1).
        raise FarmerError("age_gate", 403)
    account.dob = data.dob

    await _check_location(session, data.tehsil_id, data.village_id)
    farmer = Farmer(
        account_id=account_id,
        display_name=data.display_name.strip(),
        language=data.language,
        tehsil_id=data.tehsil_id,
        village_id=data.village_id,
        status="active",
    )
    session.add(farmer)
    await session.flush()
    return farmer


async def update(session: AsyncSession, farmer: Farmer, data: FarmerUpdateIn) -> Farmer:
    fields = data.model_dump(exclude_unset=True)
    tehsil_id = fields.get("tehsil_id", farmer.tehsil_id)
    if "tehsil_id" in fields and "village_id" not in fields and tehsil_id != farmer.tehsil_id:
        fields["village_id"] = None  # moving tehsil drops the old village
    village_id = fields.get("village_id", farmer.village_id)
    if "tehsil_id" in fields or "village_id" in fields:
        await _check_location(session, tehsil_id, village_id)
    for k, v in fields.items():
        if k == "display_name" and v is not None:
            v = v.strip()
        if v is None and k in ("display_name", "language", "tehsil_id"):
            continue  # not nullable; ignore explicit nulls
        setattr(farmer, k, v)
    await session.flush()
    return farmer


async def to_out(session: AsyncSession, farmer: Farmer, phone: str, lang: str) -> FarmerOut:
    chain = await location_service.get_tehsil_chain(session, farmer.tehsil_id)
    tehsil, district, state = chain

    def place(p) -> PlaceOut:
        return PlaceOut(id=p.id, name=p.name_in(lang), name_en=p.name_en)

    village = await session.get(Village, farmer.village_id) if farmer.village_id else None
    return FarmerOut(
        id=farmer.id,
        display_name=farmer.display_name,
        language=farmer.language,
        phone=phone,
        status=farmer.status,
        state=place(state),
        district=place(district),
        tehsil=place(tehsil),
        village=place(village) if village else None,
    )
