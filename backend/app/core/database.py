"""SQLAlchemy engine/session wiring for the admin panel.

The admin panel connects directly to the existing shaverma `system_db`,
but it only ever creates/reads/writes the admin_* tables defined under
app.models -- it does not import or depend on the shaverma project's own
ORM models.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _make_engine():
    settings = get_settings()
    connect_args = {}
    if settings.system_database_url.startswith("sqlite"):
        # Only relevant for tests, which use an in-memory sqlite database.
        connect_args = {"check_same_thread": False}
    return create_engine(
        settings.system_database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


engine = _make_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped DB session."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
