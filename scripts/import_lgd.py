"""Load the all-India location hierarchy from LGD CSV exports.

Download reports from https://lgdirectory.gov.in (Download Directory → State /
District / Sub-District / Village, CSV). Load top-down, since each level's
parent must already exist:

    # from the repo root, with DATABASE_URL set (PowerShell: $env:PYTHONPATH="apps/api")
    export PYTHONPATH=apps/api
    python -m scripts.import_lgd states     path/to/states.csv
    python -m scripts.import_lgd districts  path/to/districts.csv
    python -m scripts.import_lgd tehsils    path/to/subdistricts.csv
    python -m scripts.import_lgd villages   path/to/villages_MH.csv --local-lang mr
    python -m scripts.import_lgd neighbours path/to/neighbours_MH.csv

`--local-lang` says which language the "Name (In Local)" column is in (it
differs per state: mr for Maharashtra, ta for Tamil Nadu, ...). Without it
the local name is stored under the key "local". Safe to re-run; upserts by code.

`neighbours` is our own format, `tehsil_code,neighbour_code[,rank]` (LGD has
no adjacency data). Tehsils without curated neighbours fall back to "same
district" for nearby queries.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from app.core.db import SessionLocal
from app.security.tenant import set_tenant_context
from app.services import location_import

LEVELS = (*location_import.LEVELS, "neighbours")


async def main(level: str, path: Path, local_lang: str | None) -> int:
    csv_text = path.read_text(encoding="utf-8-sig")
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        if level == "neighbours":
            return await location_import.import_neighbours(s, csv_text)
        return await location_import.import_level(s, level, csv_text, local_lang)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("level", choices=LEVELS)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--local-lang", default=None, help="language code of the local-name column")
    args = ap.parse_args()
    try:
        n = asyncio.run(main(args.level, args.csv, args.local_lang))
    except location_import.ImportError_ as e:
        print(f"import failed: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"{args.level}: {n} rows upserted")
