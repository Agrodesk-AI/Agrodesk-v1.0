import csv
import io
from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import UUID

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer, Lead
from app.schemas.import_ import ImportMapping, ImportResult, ImportRowError
from app.security.phone import normalize_phone
from app.services.lead_service import ALLOWED_SOURCES, _write_event, _upsert_task_for_next_action

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
ALLOWED_POLICIES = {"skip", "update_customer", "create_lead_only"}


class ImportError_(Exception):
    pass


def _parse_rows(filename: str, data: bytes) -> tuple[list[str], list[list[Any]]]:
    if len(data) > MAX_BYTES:
        raise ImportError_(f"file_too_large:{MAX_BYTES}")
    lower = filename.lower()
    if lower.endswith(".csv"):
        text = data.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        all_rows = list(reader)
    elif lower.endswith(".xlsx") or lower.endswith(".xlsm"):
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            raise ImportError_("empty_workbook")
        all_rows = [[c for c in row] for row in ws.iter_rows(values_only=True)]
    else:
        raise ImportError_("unsupported_format")

    if not all_rows:
        return [], []
    header = [str(c).strip() if c is not None else "" for c in all_rows[0]]
    data_rows = all_rows[1:]
    if len(data_rows) > MAX_ROWS:
        raise ImportError_(f"too_many_rows:{MAX_ROWS}")
    return header, data_rows


def _col_index(header: list[str], name: str) -> int | None:
    if not name:
        return None
    lower = [h.lower().strip() for h in header]
    needle = name.lower().strip()
    return lower.index(needle) if needle in lower else None


def _cell(row: list[Any], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    v = row[idx]
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v).strip()


def _parse_datetime(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        # ISO first
        if "T" in raw:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        # YYYY-MM-DD
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
            except ValueError:
                continue
    except Exception:
        pass
    return None


def _default_next_action() -> datetime:
    return (datetime.now(UTC) + timedelta(days=1)).replace(hour=4, minute=30, second=0, microsecond=0)
    # 04:30 UTC = 10:00 IST


async def run_import(
    session: AsyncSession,
    *,
    dealer_id: UUID,
    actor_user_id: UUID,
    filename: str,
    data: bytes,
    mapping: ImportMapping,
    default_source: str,
    duplicate_policy: str,
    dry_run: bool,
) -> ImportResult:
    if default_source not in ALLOWED_SOURCES:
        raise ImportError_(f"bad_default_source:{default_source}")
    if duplicate_policy not in ALLOWED_POLICIES:
        raise ImportError_(f"bad_duplicate_policy:{duplicate_policy}")

    header, rows = _parse_rows(filename, data)

    idx = {
        "phone": _col_index(header, mapping.phone),
        "name": _col_index(header, mapping.name),
        "model_interest": _col_index(header, mapping.model_interest or ""),
        "source": _col_index(header, mapping.source or ""),
        "campaign": _col_index(header, mapping.campaign or ""),
        "ad_name": _col_index(header, mapping.ad_name or ""),
        "next_action_at": _col_index(header, mapping.next_action_at or ""),
    }
    if idx["phone"] is None:
        raise ImportError_(f"missing_column:phone:{mapping.phone}")
    if idx["name"] is None:
        raise ImportError_(f"missing_column:name:{mapping.name}")

    created = updated = skipped = 0
    errors: list[ImportRowError] = []
    default_next = _default_next_action()

    for i, row in enumerate(rows, start=2):  # data starts at spreadsheet row 2
        try:
            name = _cell(row, idx["name"])
            phone_raw = _cell(row, idx["phone"])
            if not name:
                errors.append(ImportRowError(row=i, field="name", message="required"))
                continue
            if not phone_raw:
                errors.append(ImportRowError(row=i, field="phone", message="required"))
                continue
            try:
                phone = normalize_phone(phone_raw)
            except ValueError:
                errors.append(ImportRowError(row=i, field="phone", message="invalid"))
                continue

            source = _cell(row, idx["source"]).lower() or default_source
            if source not in ALLOWED_SOURCES:
                errors.append(ImportRowError(row=i, field="source",
                                             message=f"invalid:{source}"))
                continue

            next_at_raw = _cell(row, idx["next_action_at"])
            next_at = _parse_datetime(next_at_raw) if next_at_raw else default_next
            if next_at_raw and next_at is None:
                errors.append(ImportRowError(row=i, field="next_action_at",
                                             message="unparseable"))
                continue

            model_interest = _cell(row, idx["model_interest"]) or None
            campaign = _cell(row, idx["campaign"]) or None
            ad_name = _cell(row, idx["ad_name"]) or None

            # Dedupe
            existing = await session.scalar(
                select(Customer).where(Customer.dealer_id == dealer_id, Customer.phone == phone)
            )
            if existing is not None and duplicate_policy == "skip":
                skipped += 1
                continue

            if dry_run:
                # count what would happen, but don't write
                if existing is None:
                    created += 1
                elif duplicate_policy == "update_customer":
                    updated += 1
                    created += 1  # a new lead would also be made
                else:  # create_lead_only
                    created += 1
                continue

            if existing is None:
                cust = Customer(dealer_id=dealer_id, name=name, phone=phone)
                session.add(cust)
                await session.flush()
                customer_id = cust.id
            else:
                if duplicate_policy == "update_customer":
                    existing.name = name
                    await session.flush()
                    updated += 1
                customer_id = existing.id

            lead = Lead(
                dealer_id=dealer_id,
                customer_id=customer_id,
                source=source,
                model_interest=model_interest,
                stage="new",
                owner_user_id=actor_user_id,
                next_action_at=next_at,
                campaign=campaign,
                ad_name=ad_name,
                created_via="csv",
            )
            session.add(lead)
            await session.flush()
            _write_event(
                session,
                dealer_id=dealer_id,
                lead_id=lead.id,
                type_="created",
                payload={
                    "source": source,
                    "customer_id": str(customer_id),
                    "via": "csv_import",
                    "row": i,
                },
                actor_type="user",
                actor_id=actor_user_id,
            )
            await _upsert_task_for_next_action(session, lead)
            await session.flush()
            created += 1
        except Exception as e:  # defensive catch-all per row
            errors.append(ImportRowError(row=i, field=None, message=f"error:{type(e).__name__}"))

    return ImportResult(
        total=len(rows),
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors,
        dry_run=dry_run,
    )
