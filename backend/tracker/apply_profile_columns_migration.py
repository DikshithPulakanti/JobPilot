"""
Apply migrate_candidates_profile.sql using DATABASE_URL from backend/.env.

Usage (from backend/):
  python tracker/apply_profile_columns_migration.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

_BACKEND = Path(__file__).resolve().parents[1]


def main() -> None:
    load_dotenv(_BACKEND / ".env")
    load_dotenv()  # cwd .env if present

    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit(
            "DATABASE_URL is not set. Add it to backend/.env (see .env.example), e.g.\n"
            "  DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/jobpilot"
        )

    sql_path = Path(__file__).resolve().parent / "migrate_candidates_profile.sql"
    lines: list[str] = []
    for raw in sql_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("--"):
            continue
        lines.append(line)

    # One ALTER per line in our migration file
    statements = [ln.rstrip(";") for ln in lines if ln.upper().startswith("ALTER")]

    if not statements:
        raise SystemExit(f"No ALTER statements found in {sql_path}")

    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
    except OperationalError as exc:
        parsed = urlparse(url)
        role = parsed.username
        low = str(exc).lower()
        print(f"Could not connect: {exc}", file=sys.stderr)
        if "role" in low and "does not exist" in low:
            print(
                "\nYour DATABASE_URL uses a PostgreSQL role that is not created on this server.\n"
                f"  Role from URL: {role!r}\n\n"
                "Fix one of:\n"
                "  1) Edit backend/.env and set DATABASE_URL to a user that exists, e.g.\n"
                "       postgresql://postgres@localhost:5432/jobpilot\n"
                "       postgresql://$(whoami)@localhost:5432/jobpilot   # often works on Mac\n"
                "  2) Create the missing role (as a superuser), e.g.\n"
                "       psql postgres -c \"CREATE ROLE \\\"YourName\\\" LOGIN;\"\n"
                "       psql postgres -c \"CREATE DATABASE jobpilot OWNER \\\"YourName\\\";\"\n"
                "  3) List roles:  psql postgres -c \"\\du\"\n",
                file=sys.stderr,
            )
        raise SystemExit(1) from exc

    print(f"Applied {len(statements)} statement(s) from {sql_path.name}")


if __name__ == "__main__":
    main()
