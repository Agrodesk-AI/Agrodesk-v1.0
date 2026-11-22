"""Import the all-India location hierarchy from LGD (Local Government Directory) CSVs.

LGD (lgdirectory.gov.in) publishes downloadable reports for states, districts,
sub-districts (tehsil / taluka / mandal) and villages. Column headers vary a
little between reports and over time, so headers are matched loosely: case,
spaces and punctuation are ignored and several aliases are accepted per field.

LGD has no adjacency data, so `neighbours` uses our own two-column format
(`tehsil_code,neighbour_code[,rank]`), built and reviewed by the ops team.
Every edge is stored in both directions.

All upserts are idempotent: re-running a file updates names and parents.
"""

import csv
import io
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scripts import LANG_SCRIPT, detect_script, unique_lang_for_script
from app.models import District, State, Tehsil, TehsilNeighbour, Village

BATCH = 1000

_SUBDISTRICT = ("subdistrict", "tehsil", "taluka", "taluk", "mandal", "block")


@dataclass(frozen=True)
class Level:
    model: type
    prefixes: tuple[str, ...]
    parent_col: str | None
    parent_prefixes: tuple[str, ...]


LEVELS: dict[str, Level] = {
    "states": Level(State, ("state",), None, ()),
    "districts": Level(District, ("district",), "state_id", ("state",)),
    "tehsils": Level(Tehsil, _SUBDISTRICT, "district_id", ("district",)),
    "villages": Level(Village, ("village",), "tehsil_id", _SUBDISTRICT),
}


class ImportError_(ValueError):
    pass


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", h.lower())


def _find(headers: dict[str, str], candidates: Iterable[str]) -> str | None:
    for c in candidates:
        if c in headers:
            return headers[c]
    return None


def _code_aliases(prefixes: tuple[str, ...]) -> list[str]:
    out = []
    for p in prefixes:
        out += [f"{p}code", f"{p}lgdcode", f"lgd{p}code"]
    return out


def _resolve_columns(fieldnames: list[str], level: Level) -> dict[str, str | None]:
    headers = {_norm(f): f for f in fieldnames}
    code = _find(headers, _code_aliases(level.prefixes) + ["code", "lgdcode"])
    name_en = _find(
        headers,
        [f"{p}nameinenglish" for p in level.prefixes]
        + [f"{p}name" for p in level.prefixes]
        + ["nameinenglish", "name", "nameen"],
    )
    name_local = _find(
        headers,
        [f"{p}nameinlocal" for p in level.prefixes]
        + [f"{p}namelocal" for p in level.prefixes]
        + ["nameinlocal", "localname", "namelocal"],
    )
    parent = _find(headers, _code_aliases(level.parent_prefixes)) if level.parent_col else None
    missing = [label for label, col in (("code", code), ("name", name_en)) if col is None]
    if level.parent_col and parent is None:
        missing.append("parent code")
    if missing:
        raise ImportError_(f"missing columns {missing}; got headers {fieldnames}")
    return {"code": code, "name_en": name_en, "name_local": name_local, "parent": parent}


def _lang_key(local_name: str, local_lang: str | None) -> str:
    """--local-lang applies only when the name is in that language's script (a
    multi-state file tagged `mr` must not label Tamil names as Marathi). Else tag
    by script when one supported language owns it (Tamil -> ta); shared scripts
    (Devanagari, Bengali) stay under "local"."""
    script = detect_script(local_name)
    if local_lang and (LANG_SCRIPT.get(local_lang) in (None, script)):
        return local_lang
    return unique_lang_for_script(script) or "local"


def parse_rows(csv_text: str, level_name: str, local_lang: str | None) -> Iterator[dict]:
    level = LEVELS[level_name]
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("﻿")))
    cols = _resolve_columns(reader.fieldnames or [], level)
    for line_no, row in enumerate(reader, start=2):
        raw_code = (row.get(cols["code"]) or "").strip()
        name = (row.get(cols["name_en"]) or "").strip()
        if not raw_code and not name:
            continue  # blank / footer line
        try:
            code = int(raw_code)
        except ValueError:
            raise ImportError_(f"line {line_no}: bad code {raw_code!r}") from None
        if not name:
            raise ImportError_(f"line {line_no}: empty name")
        out: dict = {"id": code, "name_en": name, "names": {}}
        if cols["name_local"]:
            local = (row.get(cols["name_local"]) or "").strip()
            if local:
                out["names"] = {_lang_key(local, local_lang): local}
        if level.parent_col:
            raw_parent = (row.get(cols["parent"]) or "").strip()
            try:
                out[level.parent_col] = int(raw_parent)
            except ValueError:
                raise ImportError_(f"line {line_no}: bad parent code {raw_parent!r}") from None
        yield out


async def import_level(
    session: AsyncSession, level_name: str, csv_text: str, local_lang: str | None = None
) -> int:
    if level_name not in LEVELS:
        raise ImportError_(f"unknown level {level_name}")
    level = LEVELS[level_name]
    table = level.model.__table__
    count = 0
    batch: list[dict] = []

    async def flush() -> None:
        if not batch:
            return
        stmt = insert(table).values(batch)
        update = {
            "name_en": stmt.excluded.name_en,
            # merge so importing a second language file keeps the first
            "names": table.c.names.op("||")(stmt.excluded.names),
            "updated_at": text("now()"),
        }
        if level.parent_col:
            update[level.parent_col] = stmt.excluded[level.parent_col]
        await session.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=update))
        batch.clear()

    seen: set[int] = set()
    for row in parse_rows(csv_text, level_name, local_lang):
        if row["id"] in seen:
            continue  # LGD exports occasionally repeat rows; one upsert per code
        seen.add(row["id"])
        batch.append(row)
        count += 1
        if len(batch) >= BATCH:
            await flush()
    await flush()
    return count


async def import_neighbours(session: AsyncSession, csv_text: str, source: str = "import") -> int:
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("﻿")))
    headers = {_norm(f): f for f in reader.fieldnames or []}
    a_col = _find(headers, ["tehsilcode", "tehsilid", "subdistrictcode"])
    b_col = _find(
        headers,
        [
            "neighbourcode",
            "neighbortehsilcode",
            "neighbourtehsilcode",
            "neighbourid",
            "neighborcode",
        ],
    )
    rank_col = _find(headers, ["rank", "order"])
    if a_col is None or b_col is None:
        raise ImportError_(f"need tehsil_code,neighbour_code columns; got {reader.fieldnames}")
    edges: dict[tuple[int, int], int] = {}
    for line_no, row in enumerate(reader, start=2):
        try:
            a, b = int(row[a_col]), int(row[b_col])
            rank = int(row[rank_col]) if rank_col and row.get(rank_col) else 1
        except (TypeError, ValueError):
            raise ImportError_(f"line {line_no}: bad codes") from None
        if a == b:
            continue
        for key in ((a, b), (b, a)):
            edges[key] = min(rank, edges.get(key, rank))
    rows = [
        {"tehsil_id": a, "neighbour_tehsil_id": b, "rank": r, "source": source}
        for (a, b), r in edges.items()
    ]
    table = TehsilNeighbour.__table__
    for i in range(0, len(rows), BATCH):
        stmt = insert(table).values(rows[i : i + BATCH])
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["tehsil_id", "neighbour_tehsil_id"],
                set_={"rank": stmt.excluded.rank, "source": stmt.excluded.source},
            )
        )
    return len(rows)
