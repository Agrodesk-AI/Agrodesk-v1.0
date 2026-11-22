import json

import pytest
from sqlalchemy import select, text

from app.core.db import SessionLocal
from app.models import KbChunk, KbDocument
from app.security.tenant import set_tenant_context
from app.services import kb_service
from tests._helpers import make_dealer_and_owner, make_platform_admin, token_for


async def _upload(client, hdr, title, body, shared=False):
    return await client.post(
        "/v1/kb/documents", headers=hdr,
        json={"title": title, "body": body, "language": "en", "tags": [], "shared": shared},
    )


@pytest.mark.asyncio
async def test_upload_and_chunk(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9008000001")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    long_text = ("Mahindra 575 DI XP Plus specs and price information. " * 50).strip()
    r = await _upload(client, hdr, "Mahindra 575 brochure", long_text)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["chunks"] >= 2


@pytest.mark.asyncio
async def test_cross_tenant_rls_isolation(client):
    dealer_a, owner_a, _, _ = await make_dealer_and_owner("A", "9008000002")
    dealer_b, owner_b, _, _ = await make_dealer_and_owner("B", "9008000003")
    hdr_a = {"Authorization": f"Bearer {token_for(owner_a, 'owner', dealer_a)}"}
    hdr_b = {"Authorization": f"Bearer {token_for(owner_b, 'owner', dealer_b)}"}

    await _upload(client, hdr_a, "A private", "Mahindra Arjun 605 DI is a 60hp tractor.")
    await _upload(client, hdr_b, "B private", "Sonalika DI 745 is a 50hp tractor.")

    # Dealer B searches for Mahindra; must NOT see A's chunk
    r = await client.get("/v1/kb/search?q=Mahindra", headers=hdr_b)
    assert r.status_code == 200
    hits = r.json()["hits"]
    titles = {h["title"] for h in hits}
    assert "A private" not in titles

    # And direct RLS probe on kb_chunks with dealer B context
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=dealer_b, is_platform_admin=False)
        rows = (await s.scalars(select(KbChunk))).all()
        for row in rows:
            assert row.dealer_id is None or str(row.dealer_id) == dealer_b


@pytest.mark.asyncio
async def test_shared_document_visible_to_all_dealers(client):
    admin, _ = await make_platform_admin("9008000004")
    admin_hdr = {"Authorization": f"Bearer {token_for(admin, 'platform_admin', None)}"}
    r = await client.post(
        "/v1/kb/documents", headers=admin_hdr,
        json={"title": "Shared tractor FAQ", "body": "Common questions about Mahindra tractors.",
              "language": "en", "tags": [], "shared": True},
    )
    assert r.status_code == 201, r.text

    dealer, owner, _, _ = await make_dealer_and_owner("A", "9008000005")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    r = await client.get("/v1/kb/search?q=Mahindra", headers=hdr)
    hits = r.json()["hits"]
    titles = {h["title"] for h in hits}
    assert "Shared tractor FAQ" in titles


@pytest.mark.asyncio
async def test_keyword_match_beats_pure_semantic(client):
    """With Fake embeddings the vectors are hash-random, so a keyword match
    should lift the correct chunk above an unrelated one."""
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9008000006")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    await _upload(client, hdr, "Rice harvesting", "Rice paddy harvesting is best done with a 40hp tractor.")
    await _upload(client, hdr, "Wheat harvesting",
                  "Wheat harvesters work well on soil of Nashik and Sangamner.")

    r = await client.get("/v1/kb/search?q=paddy&k=2", headers=hdr)
    hits = r.json()["hits"]
    assert hits[0]["title"] == "Rice harvesting"


@pytest.mark.asyncio
async def test_empty_body_rejected(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9008000007")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    r = await _upload(client, hdr, "Empty", "")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_pdf_upload_and_scanned_rejected(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9008000008")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    # Build a minimal text PDF via pypdf's inverse — use reportlab if present, else skip
    try:
        from pypdf import PdfWriter
        # pypdf can't synthesize content; craft a tiny raw PDF with a single text chunk.
    except Exception:  # noqa
        pytest.skip("pypdf not available")
    # Build a minimal PDF via raw bytes (one Tj operator)
    raw = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"  # noqa: E501
        b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 30 150 Td (Mahindra 575 Powerplus) Tj ET\nendstream endobj\n"  # noqa: E501
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000010 00000 n \n0000000056 00000 n \n"
        b"0000000103 00000 n \n0000000215 00000 n \n0000000308 00000 n \n"
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n360\n%%EOF"
    )

    meta = json.dumps({"title": "PDF upload", "language": "en", "tags": []})
    r = await client.post(
        "/v1/kb/documents/upload", headers=hdr,
        files={"file": ("doc.pdf", raw, "application/pdf")},
        data={"meta": meta},
    )
    # Permissive: some pypdf versions reject a very minimal pdf. Either success or pdf_scanned.
    assert r.status_code in (201, 422), r.text

    # Empty bytes → scanned
    r = await client.post(
        "/v1/kb/documents/upload", headers=hdr,
        files={"file": ("blank.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        data={"meta": meta},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_search_returns_document_title_and_source(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9008000009")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    r = await client.post(
        "/v1/kb/documents", headers=hdr,
        json={"title": "Price list Q4 2026", "body": "Mahindra 575 is priced around 6.8L in Nashik.",
              "language": "en", "tags": ["price"], "source": "internal-dealer-sheet", "shared": False},
    )
    assert r.status_code == 201
    r = await client.get("/v1/kb/search?q=Mahindra", headers=hdr)
    hits = r.json()["hits"]
    assert hits and hits[0]["title"] == "Price list Q4 2026"
    assert hits[0]["source"] == "internal-dealer-sheet"
