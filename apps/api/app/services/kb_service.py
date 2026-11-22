"""Knowledge base: chunking, embedding, pgvector cosine retrieval."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import KbChunk, KbDocument
from packages.channels.embeddings import get_embedding_provider


class KbError(Exception):
    pass


class EmptyContent(KbError):
    pass


class PdfScanned(KbError):
    pass


def chunk_text(body: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    size = size or settings.kb_chunk_size
    overlap = overlap or settings.kb_chunk_overlap
    body = body.strip()
    if not body:
        return []
    if len(body) <= size:
        return [body]
    chunks: list[str] = []
    step = max(1, size - overlap)
    for start in range(0, len(body), step):
        piece = body[start : start + size]
        if piece:
            chunks.append(piece)
        if start + size >= len(body):
            break
    return chunks


def extract_pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n\n".join(p for p in parts if p.strip())


async def upload_document(
    session: AsyncSession,
    *,
    dealer_id: UUID | None,
    title: str,
    source: str | None,
    language: str,
    tags: list[str],
    body: str | None = None,
    pdf_bytes: bytes | None = None,
) -> tuple[KbDocument, int]:
    if pdf_bytes is not None:
        if len(pdf_bytes) > settings.kb_max_upload_bytes:
            raise KbError("pdf_too_large")
        try:
            extracted = extract_pdf_text(pdf_bytes)
        except Exception as e:
            raise KbError(f"pdf_parse_error:{e}") from None
        if not extracted.strip():
            raise PdfScanned("pdf_scanned")
        body = extracted
    if not body or not body.strip():
        raise EmptyContent("empty_content")

    doc = KbDocument(
        dealer_id=dealer_id,
        title=title,
        source=source,
        language=language,
        tags=tags,
        last_verified_at=datetime.now(UTC),
    )
    session.add(doc)
    await session.flush()

    chunks = chunk_text(body)
    if not chunks:
        raise EmptyContent("no_chunks")
    provider = get_embedding_provider()
    vectors = await provider.embed(chunks)
    for text_piece, vec in zip(chunks, vectors, strict=True):
        session.add(
            KbChunk(
                dealer_id=dealer_id,
                document_id=doc.id,
                text=text_piece,
                embedding=vec,
                meta={},
            )
        )
    await session.flush()
    return doc, len(chunks)


async def search(session: AsyncSession, *, query: str, k: int = 5) -> list[dict]:
    """Hybrid: 0.7*(1 - cosine_distance) + 0.3*keyword_boost via pgvector's
    `<=>` operator. RLS enforces tenant scoping; shared rows (dealer_id IS NULL)
    are visible to every tenant."""
    query = query.strip()
    if not query:
        return []
    provider = get_embedding_provider()
    [vec] = await provider.embed([query])
    like = f"%{query}%"
    vec_literal = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
    sql = text("""
        SELECT c.id, c.document_id, c.dealer_id, c.text,
               d.title, d.source, d.language,
               (1 - (c.embedding <=> CAST(:vec AS vector))) AS vec_sim,
               CASE WHEN c.text ILIKE :like THEN 1.0 ELSE 0.0 END AS kw
        FROM kb_chunks c
        JOIN kb_documents d ON d.id = c.document_id
        ORDER BY (0.7 * (1 - (c.embedding <=> CAST(:vec AS vector)))
                 + 0.3 * (CASE WHEN c.text ILIKE :like THEN 1.0 ELSE 0.0 END)) DESC
        LIMIT :k
    """)
    result = await session.execute(sql, {"vec": vec_literal, "like": like, "k": k})
    rows = result.mappings().all()
    return [
        {
            "chunk_id": str(r["id"]),
            "document_id": str(r["document_id"]),
            "title": r["title"],
            "source": r["source"],
            "language": r["language"],
            "text": r["text"],
            "score": float(0.7 * r["vec_sim"] + 0.3 * r["kw"]),
            "dealer_id": str(r["dealer_id"]) if r["dealer_id"] else None,
        }
        for r in rows
    ]


async def list_documents(session: AsyncSession) -> list[KbDocument]:
    rows = await session.scalars(
        select(KbDocument).order_by(KbDocument.created_at.desc())
    )
    return list(rows)


async def delete_document(session: AsyncSession, doc_id: UUID) -> bool:
    doc = await session.scalar(select(KbDocument).where(KbDocument.id == doc_id))
    if doc is None:
        return False
    await session.delete(doc)
    await session.flush()
    return True
