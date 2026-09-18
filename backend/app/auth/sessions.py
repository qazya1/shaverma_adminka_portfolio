"""Server-side session management.

Sessions are opaque random tokens handed to the browser as an HttpOnly
cookie. The database only ever stores a SHA-256 digest of the token, so a
database leak alone cannot be used to impersonate a session.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import generate_secure_token, sha256_hex
from app.models.admin import AdminUser
from app.models.auth import AdminSession


@dataclass
class NewSession:
    session: AdminSession
    token: str


def create_session(
    db: Session,
    admin: AdminUser,
    settings: Settings,
    ip: str | None,
    user_agent: str | None,
) -> NewSession:
    token = generate_secure_token()
    now = datetime.now(UTC)

    session = AdminSession(
        admin_id=admin.id,
        token_hash=sha256_hex(token),
        expires_at=now + timedelta(seconds=settings.admin_session_ttl_seconds),
        ip=ip,
        user_agent=user_agent,
    )
    db.add(session)
    db.flush()

    return NewSession(session=session, token=token)


def get_active_session_by_token(db: Session, token: str) -> AdminSession | None:
    """Look up a session by its raw token, returning it only if it is
    still valid (not revoked, not expired). Does not touch last_seen_at
    -- call `touch_session` separately once the caller has decided the
    session is usable.
    """

    token_hash = sha256_hex(token)
    session = db.query(AdminSession).filter(AdminSession.token_hash == token_hash).one_or_none()
    if session is None:
        return None

    if session.revoked_at is not None:
        return None

    expires_at = session.expires_at
    now = datetime.now(UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        return None

    return session


def touch_session(db: Session, session: AdminSession) -> None:
    session.last_seen_at = datetime.now(UTC)
    db.flush()


def revoke_session(db: Session, session: AdminSession) -> None:
    session.revoked_at = datetime.now(UTC)
    db.flush()
