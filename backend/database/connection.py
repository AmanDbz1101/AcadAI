"""
Database connection management.

Reads connection URL from environment / config and exposes
a singleton engine + session factory, plus a context manager helper.
"""

import logging
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.database.models import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_database_url() -> str:
    """
    Build PostgreSQL DSN from environment variables or fall back to a sensible
    local default suitable for development.

    Precedence (highest to lowest):
    1. ``DATABASE_URL``          – full DSN (e.g. from .env)
    2. Individual vars:          – PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD
    3. Hard-coded localhost default for local dev
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    db   = os.getenv("PG_DB",   "research_papers")
    user = os.getenv("PG_USER", "postgres")
    pwd  = os.getenv("PG_PASSWORD", "")

    if pwd:
        return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
    return f"postgresql+psycopg2://{user}@{host}:{port}/{db}"


# ---------------------------------------------------------------------------
# Singleton connection class
# ---------------------------------------------------------------------------

class DatabaseConnection:
    """
    Manages the SQLAlchemy engine and session factory.
    
    Usage::

        db = DatabaseConnection()
        db.create_tables()          # create all tables if they don't exist

        with db.session() as sess:
            sess.add(some_record)
    """

    def __init__(self, database_url: str | None = None):
        self._url = database_url or _build_database_url()
        self._engine = create_engine(
            self._url,
            pool_pre_ping=True,          # detect stale connections
            pool_size=5,
            max_overflow=10,
            echo=False,
        )
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)
        logger.info("DatabaseConnection initialised (url masked for security)")

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def create_tables(self) -> None:
        """Create all tables that do not already exist (idempotent)."""
        Base.metadata.create_all(self._engine)
        logger.info("Database tables created / verified.")

    def drop_tables(self) -> None:
        """Drop ALL managed tables – use only in tests / dev teardown."""
        Base.metadata.drop_all(self._engine)
        logger.warning("All database tables dropped.")

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """
        Context manager that provides a session with automatic commit/rollback.

        Example::

            with db.session() as sess:
                sess.add(record)
        """
        sess = self._Session()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()

    def health_check(self) -> bool:
        """Return True if the database is reachable."""
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.error(f"Database health check failed: {exc}")
            return False


# ---------------------------------------------------------------------------
# Module-level convenience (lazy singleton)
# ---------------------------------------------------------------------------

_default_connection: DatabaseConnection | None = None


def get_db_connection() -> DatabaseConnection:
    """Return the module-level singleton DatabaseConnection."""
    global _default_connection
    if _default_connection is None:
        _default_connection = DatabaseConnection()
    return _default_connection


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Shorthand context manager using the module-level connection."""
    with get_db_connection().session() as sess:
        yield sess
