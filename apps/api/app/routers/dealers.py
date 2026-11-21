from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import require_role
from app.deps.db import get_session_platform
from app.schemas.dealer import DealerCreateIn, DealerOut, DealerWithOwner
from app.services import dealer_service

router = APIRouter(prefix="/v1/admin/dealers", tags=["admin"])


@router.post("", response_model=DealerWithOwner, status_code=status.HTTP_201_CREATED)
async def create_dealer(
    body: DealerCreateIn,
    _: dict = Depends(require_role("platform_admin")),
    session: AsyncSession = Depends(get_session_platform),
) -> DealerWithOwner:
    try:
        dealer, owner = await dealer_service.create_dealer_with_owner(session, body)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad_phone") from None
    return DealerWithOwner(
        dealer=DealerOut(
            id=dealer.id,
            name=dealer.name,
            brands=dealer.brands,
            city=dealer.city,
            district=dealer.district,
            state=dealer.state,
            default_language=dealer.default_language,
            status=dealer.status,
        ),
        owner_id=owner.id,
    )
