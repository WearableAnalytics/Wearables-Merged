"""Initialize one named administrator using protected server/DB access. Never pass passwords as arguments."""

import argparse
import asyncio
from getpass import getpass

from fastapi import HTTPException

from app.db.postgres.engine import AsyncSessionLocal, engine
from app.services.password_service import PasswordService


async def initialize(email: str, password: str, *, reset: bool = False, reason: str | None = None) -> None:
    try:
        async with AsyncSessionLocal() as db:
            await PasswordService(db).bootstrap(email, password, reset=reset, reason=reason)
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Protected operator recovery of an existing active admin; forces personal password setup.",
    )
    args = parser.parse_args()
    reason = input("Operator recovery reason (1–256 characters): ").strip() if args.reset_password else None
    first = getpass("Administrator password (at least 15 characters): ")
    if first != getpass("Repeat password: "):
        raise SystemExit("Passwords did not match.")
    try:
        asyncio.run(initialize(args.email, first, reset=args.reset_password, reason=reason))
    except HTTPException as error:
        raise SystemExit(str(error.detail)) from None
    print(
        "Administrator password reset; first-login change required."
        if args.reset_password
        else "Named administrator initialized. No case access was inferred."
    )


if __name__ == "__main__":
    main()
