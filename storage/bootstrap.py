from __future__ import annotations

import os
from threading import RLock
from typing import Optional

import psycopg2
from psycopg2.extensions import connection as Connection

from .migrations import MIGRATIONS
from .postgres import Storage

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/postgres"

_storage_instance: Optional[Storage] = None
_storage_lock = RLock()


def init_storage(*, database_url: Optional[str] = None) -> Storage:
    """
    Initialise storage singleton with PostgreSQL. Ensures migrations are applied.
    """
    global _storage_instance

    if _storage_instance is not None:
        return _storage_instance

    with _storage_lock:
        if _storage_instance is not None:
            return _storage_instance

        db_url = database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

        conn = psycopg2.connect(db_url)
        conn.autocommit = False

        _apply_migrations(conn)

        _storage_instance = Storage(conn=conn)
        return _storage_instance


def get_storage() -> Storage:
    if _storage_instance is None:
        raise RuntimeError("Storage was not initialised. Call init_storage() first.")
    return _storage_instance


def _apply_migrations(conn: Connection) -> None:
    with conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)")
        conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations ORDER BY version")
        applied = {row[0] for row in cur.fetchall()}

    for version, sql in MIGRATIONS:
        if version in applied:
            continue

        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (version,))
            conn.commit()

