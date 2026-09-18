#!/usr/bin/env python3
"""Local-only helper for provisioning an `admin_users` row.

Run BY HAND, from a shell with access to the real `.env`/database --
never imported by `app.main`, never served over HTTP, never deployed
anywhere the app runs as a service. This does not relax "no
network-reachable way to create an admin" (see `app/models/admin.py`'s
module docstring, updated alongside this file): it's a convenience over
the manual `hash_password()` + hand-written `INSERT INTO admin_users`
steps the README used to spell out, nothing more -- someone still needs
a shell on the box (or a local checkout pointed at the real
`SYSTEM_DATABASE_URL`) to run it.

Usage:
    cd backend
    .venv/bin/python create_admin.py --username alice --telegram-user-id 123456789

Prompts for the password interactively, twice (never accepted as a CLI
argument or environment variable, so it never lands in shell history or
a process listing); nothing about the password is ever printed, logged,
or held onto longer than it takes to hash it.
"""

import argparse
import getpass
import sys

from sqlalchemy import select

from app.auth.password import hash_password
from app.core.database import SessionLocal
from app.models.admin import AdminUser

_MIN_PASSWORD_LENGTH = 12


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--username", required=True, help="Login username -- must be unique.")
    parser.add_argument(
        "--telegram-user-id",
        required=True,
        help="The admin's numeric Telegram user id (NOT a phone number) -- see README, 'Administrators'.",
    )
    parser.add_argument(
        "--inactive",
        action="store_true",
        help="Create the row with is_active=false instead of the default true.",
    )
    return parser.parse_args()


def _prompt_password() -> str:
    while True:
        password = getpass.getpass("Password: ")
        if len(password) < _MIN_PASSWORD_LENGTH:
            print(f"Password must be at least {_MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
            continue
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords did not match -- try again.", file=sys.stderr)
            continue
        return password


def _confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().lower() == "y"


def main() -> int:
    args = _parse_args()

    if not args.telegram_user_id.isdigit():
        print(f"error: --telegram-user-id must be numeric, got {args.telegram_user_id!r}", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        existing_count = db.query(AdminUser).count()
        if existing_count >= 2:
            print(
                f"warning: this system already has {existing_count} administrator(s). "
                "The rest of adminka assumes exactly two, fully equal admins with no "
                "roles/permissions -- adding more is untested territory.",
                file=sys.stderr,
            )
            if not _confirm("Continue anyway?"):
                print("Aborted.")
                return 1

        if db.execute(select(AdminUser.id).where(AdminUser.username == args.username)).first() is not None:
            print(f"error: username {args.username!r} is already taken", file=sys.stderr)
            return 1
        if (
            db.execute(select(AdminUser.id).where(AdminUser.telegram_user_id == args.telegram_user_id)).first()
            is not None
        ):
            print(f"error: telegram_user_id {args.telegram_user_id!r} is already in use", file=sys.stderr)
            return 1

        is_active = not args.inactive
        print(f"About to create: username={args.username!r} telegram_user_id={args.telegram_user_id!r} is_active={is_active}")
        if not _confirm("Proceed?"):
            print("Aborted.")
            return 1

        password = _prompt_password()
        password_hash = hash_password(password)
        del password  # never referenced again, out of scope as soon as possible

        row = AdminUser(
            username=args.username,
            password_hash=password_hash,
            telegram_user_id=args.telegram_user_id,
            is_active=is_active,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    finally:
        db.close()

    print(f"Created admin_users row id={row.id} username={row.username!r} is_active={row.is_active}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
