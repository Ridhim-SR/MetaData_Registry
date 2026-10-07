"""Seed demo visibility rows in users.dataset_visibility (manual only).

Never run automatically: the data engineering team owns access levels in
OpenMetadata/long-term process; this script exists to set up demo and test
scenarios by hand.

Usage (from apps/api, DATABASE_URL in env or .env):
    python scripts/seed_visibility.py --public <fqn> [fqn ...]
        --department <fqn> [fqn ...] --restricted <fqn> [fqn ...]
        --confidential <fqn> [fqn ...] [--owner-department NAME]

FQNs are OpenMetadata *table* FQNs (service.database.schema.table).
service/database/schema/table columns are derived from the FQN; the owning
department defaults to the FQN service unless --owner-department is given.
Upserts by fqn: safe to re-run.

Example (demo: one public dataset, others department/restricted):
    python scripts/seed_visibility.py \\
        --public ag.db.public.crop_sales \\
        --department pwd.vishwakarma.public.TBD_confirm_with_pwd \\
        --restricted res.db.public.res_table
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from database.database import async_session  # noqa: E402
from database.models import DatasetVisibility, Visibility  # noqa: E402
from src.openmetadata.visibility import normalize_visibility, split_fqn  # noqa: E402

LEVELS = ("public", "department", "restricted", "confidential")


async def seed(assignments: list[tuple[str, str]], owner_department: str | None) -> dict[str, int]:
    counts = {level: 0 for level in LEVELS}
    async with async_session() as session:
        for fqn, level in assignments:
            visibility = Visibility(normalize_visibility(level))
            service, database, schema, table = split_fqn(fqn)
            if not service or not table:
                print(f"skip {fqn!r}: not a table FQN (service.database.schema.table)")
                continue
            existing = (
                await session.execute(
                    select(DatasetVisibility).where(DatasetVisibility.fqn == fqn)
                )
            ).scalar_one_or_none()
            if existing:
                existing.visibility = visibility
                existing.department = owner_department or service
                existing.service = service
                existing.database_name = database
                existing.schema_name = schema
                existing.table_name = table
            else:
                session.add(
                    DatasetVisibility(
                        fqn=fqn,
                        service=service,
                        database_name=database,
                        schema_name=schema,
                        table_name=table,
                        visibility=visibility,
                        department=owner_department or service,
                    )
                )
            counts[visibility.value] += 1
        await session.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo visibility rows (manual).")
    for level in LEVELS:
        parser.add_argument(f"--{level}", nargs="*", default=[],
                            help=f"table FQNs to mark {level}")
    parser.add_argument("--owner-department", default=None,
                        help="owning department override (default: FQN service)")
    args = parser.parse_args()
    assignments = [(fqn, level) for level in LEVELS for fqn in getattr(args, level)]
    if not assignments:
        parser.error("pass at least one FQN, e.g. --public svc.db.schema.table")
    counts = asyncio.run(seed(assignments, args.owner_department))
    print("upserted:", {k: v for k, v in counts.items() if v})


if __name__ == "__main__":
    main()
