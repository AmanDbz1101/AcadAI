"""Bootstrap PostgreSQL database and schema for the research assistant.

This script aligns setup with ``backend/database/connection.py`` and the
canonical SQLAlchemy models in ``backend/extraction/persistence/postgres_store.py``.

Usage:

    source env_research/bin/activate
    python backend/database/setup_postgres.py --db-name research_agent
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

# Ensure project root is importable when running this file directly.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.database.connection import DatabaseConnection


def _resolve_conn_params() -> dict[str, str]:
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    user = os.getenv("PG_USER", "postgres")
    password = os.getenv("PG_PASSWORD", "")
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
    }


def _database_exists(params: dict[str, str], db_name: str) -> bool:
    with psycopg.connect(dbname="postgres", **params) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            return cur.fetchone() is not None


def _create_database(params: dict[str, str], db_name: str) -> None:
    with psycopg.connect(dbname="postgres", autocommit=True, **params) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE DATABASE {}") .format(sql.Identifier(db_name)))


def _build_db_url(params: dict[str, str], db_name: str) -> str:
    user = params["user"]
    host = params["host"]
    port = params["port"]
    password = params["password"]
    if password:
        return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db_name}"
    return f"postgresql+psycopg://{user}@{host}:{port}/{db_name}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap PostgreSQL database/schema")
    parser.add_argument("--db-name", default=os.getenv("PG_DB", "research_agent"))
    args = parser.parse_args()

    db_name = args.db_name
    params = _resolve_conn_params()

    try:
        exists = _database_exists(params, db_name)
    except Exception as exc:
        print(f"ERROR: could not connect to PostgreSQL using current PG_* settings: {exc}")
        return 1

    if not exists:
        try:
            _create_database(params, db_name)
            print(f"Created database: {db_name}")
        except Exception as exc:
            print(f"ERROR: unable to create database '{db_name}': {exc}")
            print(
                "Hint: run as a PostgreSQL superuser or grant CREATEDB to PG_USER, "
                "then rerun this script."
            )
            return 2
    else:
        print(f"Database already exists: {db_name}")

    db_url = _build_db_url(params, db_name)
    try:
        conn = DatabaseConnection(database_url=db_url)
        conn.create_tables()
    except Exception as exc:
        print(f"ERROR: database exists but schema initialization failed: {exc}")
        return 3

    print("Schema initialization complete.")
    print("Recommended environment values:")
    print(f"  PG_DB={db_name}")
    print(f"  DATABASE_URL={db_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())