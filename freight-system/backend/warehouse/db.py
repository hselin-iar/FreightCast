"""
warehouse/db.py — database engine and session setup.

DOC3 §FEATURE: Data Warehouse → db.py
DOC3 §4 Deployment: Render managed Postgres in production.

Build Step 3: reads DATABASE_URL from environment.
Tests: uses SQLite :memory: via override.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from backend.warehouse.models import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Typed exception — caught at the API layer and converted to 503
# DOC3: "Connection failures raise a typed WarehouseUnavailableError"
# ---------------------------------------------------------------------------

class WarehouseUnavailableError(Exception):
    """Raised when the warehouse cannot be reached. API layer converts to 503."""
    pass


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def get_engine(database_url: str | None = None) -> Engine:
    """
    Return (and cache) the SQLAlchemy engine.

    database_url overrides DATABASE_URL env var — used in tests to inject SQLite.
    """
    global _engine, _SessionFactory

    url = database_url or os.environ.get("DATABASE_URL", "")
    if not url:
        if os.path.exists("freight_dev.db"):
            url = "sqlite:///freight_dev.db"
        elif os.path.exists("freight-system/freight_dev.db"):
            url = "sqlite:///freight-system/freight_dev.db"
        else:
            raise WarehouseUnavailableError(
                "DATABASE_URL is not set. Cannot connect to the warehouse."
            )

    if _engine is None or (database_url is not None):
        # For SQLite (tests) use check_same_thread=False
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(
            url,
            connect_args=connect_args,
            pool_pre_ping=True,   # detect stale connections
            echo=False,
        )
        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)
        logger.info("Warehouse engine initialised: %s", url.split("@")[-1])  # no creds in logs

    return _engine


def get_session_factory(database_url: str | None = None) -> sessionmaker:
    """Return the session factory, initialising the engine if needed."""
    global _SessionFactory
    get_engine(database_url)
    assert _SessionFactory is not None
    return _SessionFactory


@contextmanager
def get_session(database_url: str | None = None) -> Generator[Session, None, None]:
    """
    Context-manager session.

    Usage:
        with get_session() as session:
            result = session.execute(...)
    """
    factory = get_session_factory(database_url)
    session: Session = factory()
    try:
        yield session
        session.commit()
    except OperationalError as exc:
        session.rollback()
        raise WarehouseUnavailableError(
            f"Warehouse unreachable during session: {exc}"
        ) from exc
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Schema management
# ---------------------------------------------------------------------------

def create_all_tables(database_url: str | None = None) -> None:
    """
    Create all tables from ORM metadata.
    Used in tests and initial setup. Production uses alembic migrations.
    """
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    logger.info("All warehouse tables created (create_all).")


def verify_connection(database_url: str | None = None) -> bool:
    """
    Return True if the warehouse is reachable, False otherwise.
    Used by /health endpoint (Build Step 10).
    Never raises — caller handles the False case.
    """
    try:
        engine = get_engine(database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Warehouse connection check failed: %s", exc)
        return False


def reset_engine() -> None:
    """
    Reset the cached engine and session factory.
    Used in tests to swap between SQLite and Postgres.
    """
    global _engine, _SessionFactory
    if _engine:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
