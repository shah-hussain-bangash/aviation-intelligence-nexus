"""Local OS-owner account management. Passwords are entered privately, never as arguments."""

import argparse
from getpass import getpass
import os
from pathlib import Path
import sqlite3

from services.api.auth import AuthStore
from services.api.main import ROOT, initialize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "set-role", "disable"])
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", choices=["admin", "researcher", "viewer"])
    args = parser.parse_args()
    database = Path(os.environ.get("AIN_DB_PATH", str(ROOT / ".local/ain.sqlite3")))
    initialize(database)
    auth = AuthStore(database)
    try:
        if args.action == "create":
            if not args.role:
                parser.error("create requires --role")
            password = getpass("New password (12–128 characters; hidden): ")
            if password != getpass("Confirm password: "):
                raise ValueError("Passwords did not match")
            auth.create_user(args.username, password, args.role)
            print("Account created. Sign in through the local dashboard.")
        else:
            if args.action == "set-role" and not args.role:
                parser.error("set-role requires --role")
            auth.set_access(args.username, args.role, args.action == "disable")
            print("Account access updated; its existing sessions were revoked.")
    except (ValueError, sqlite3.IntegrityError) as error:
        parser.exit(1, f"Account update failed: {error}\n")


if __name__ == "__main__":
    main()
