import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.db import get_session_tenant
from app.schemas.import_ import ImportMapping, ImportResult
from app.services import import_service

router = APIRouter(prefix="/v1/leads", tags=["imports"])


@router.post("/import", response_model=ImportResult)
async def import_leads(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    default_source: str = Form("other"),
    duplicate_policy: str = Form("create_lead_only"),
    dry_run: bool = Form(False),
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> ImportResult:
    if not principal["dealer_id"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no_dealer_scope")
    try:
        mapping_obj = ImportMapping(**json.loads(mapping))
    except Exception:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad_mapping") from None

    data = await file.read()
    try:
        result = await import_service.run_import(
            session,
            dealer_id=UUID(principal["dealer_id"]),
            actor_user_id=UUID(principal["user_id"]),
            filename=file.filename or "upload",
            data=data,
            mapping=mapping_obj,
            default_source=default_source,
            duplicate_policy=duplicate_policy,
            dry_run=dry_run,
        )
    except import_service.ImportError_ as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return result
