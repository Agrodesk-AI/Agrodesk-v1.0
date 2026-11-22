import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user, require_role
from app.deps.db import get_session_tenant
from app.schemas.kb import DocumentCreateIn, DocumentOut, SearchHit, SearchOut, UploadResult
from app.services import kb_service

router = APIRouter(prefix="/v1/kb", tags=["kb"])


def _doc_out(d) -> DocumentOut:
    return DocumentOut(
        id=d.id, dealer_id=d.dealer_id, title=d.title, source=d.source,
        language=d.language, tags=d.tags or [], last_verified_at=d.last_verified_at,
        created_at=d.created_at,
    )


@router.post("/documents", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
async def create_from_json(
    body: DocumentCreateIn,
    principal: dict = Depends(require_role("owner", "platform_admin")),
    session: AsyncSession = Depends(get_session_tenant),
) -> UploadResult:
    if body.shared and principal["role"] != "platform_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "platform_admin_only")
    dealer_id = None if body.shared else (UUID(principal["dealer_id"]) if principal["dealer_id"] else None)
    try:
        doc, chunks = await kb_service.upload_document(
            session, dealer_id=dealer_id, title=body.title, source=body.source,
            language=body.language, tags=body.tags, body=body.body,
        )
    except kb_service.EmptyContent:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "empty_content") from None
    except kb_service.KbError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return UploadResult(document=_doc_out(doc), chunks=chunks)


@router.post("/documents/upload", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
async def upload_pdf(
    file: UploadFile = File(...),
    meta: str = Form(...),
    principal: dict = Depends(require_role("owner", "platform_admin")),
    session: AsyncSession = Depends(get_session_tenant),
) -> UploadResult:
    try:
        metadata = DocumentCreateIn(**json.loads(meta))
    except Exception:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad_meta") from None
    data = await file.read()
    if metadata.shared and principal["role"] != "platform_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "platform_admin_only")
    dealer_id = None if metadata.shared else (
        UUID(principal["dealer_id"]) if principal["dealer_id"] else None
    )
    try:
        doc, chunks = await kb_service.upload_document(
            session, dealer_id=dealer_id, title=metadata.title, source=metadata.source,
            language=metadata.language, tags=metadata.tags, pdf_bytes=data,
        )
    except kb_service.PdfScanned:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "pdf_scanned") from None
    except kb_service.KbError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return UploadResult(document=_doc_out(doc), chunks=chunks)


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> list[DocumentOut]:
    rows = await kb_service.list_documents(session)
    return [_doc_out(r) for r in rows]


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: UUID,
    principal: dict = Depends(require_role("owner", "platform_admin")),
    session: AsyncSession = Depends(get_session_tenant),
) -> None:
    ok = await kb_service.delete_document(session, doc_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")


@router.get("/search", response_model=SearchOut)
async def search(
    q: str = Query(..., min_length=1),
    k: int = Query(5, ge=1, le=20),
    principal: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_tenant),
) -> SearchOut:
    hits = await kb_service.search(session, query=q, k=k)
    return SearchOut(query=q, hits=[SearchHit(**h) for h in hits])
