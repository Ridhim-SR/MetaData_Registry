"""Promote a registered user to admin (first-admin bootstrap).

The API has no self-promotion path by design: POST /auth/register always
creates role=user, and PUT /users/{id} requires an existing admin. Run this
with server access instead (equivalent of a manual UPDATE on users.users).

Usage (from apps/api, backend .env loaded automatically):
    .venv/bin/python scripts/make_admin.py --email admin@example.com
    .venv\\Scripts\\python.exe scripts/make_admin.py --email admin@example.com  (Windows)
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()  # apps/api/.env when run from apps/api

from sqlalchemy import select

from database.database import async_session
from database.models import User, UserRole


async def promote(email: str) -> int:
    address = email.strip()
    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == address))
        user = result.scalar_one_or_none()
        if user is None:
            print(f"No user with email {address}")
            return 1
        if user.role == UserRole.admin:
            print(f"{address} is already admin (id={user.id})")
            return 0
        user.role = UserRole.admin
        await session.commit()
        print(f"Promoted {address} to admin (id={user.id})")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a user to admin by email.")
    parser.add_argument("--email", required=True, help="Login email of the user to promote")
    args = parser.parse_args()
    return asyncio.run(promote(args.email))


if __name__ == "__main__":
    sys.exit(main())
