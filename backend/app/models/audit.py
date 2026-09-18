"""Audit log model.

Every security-relevant event (auth attempts, and later real system
actions) is recorded here. Call sites are responsible for never passing
secrets (passwords, password hashes, OTP codes, session tokens, bot
tokens, env secrets) into `parameters_json` -- see app/audit/service.py.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class AdminAuditEvent(Base):
    __tablename__ = "admin_audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Nullable: some events (e.g. a failed login for an unknown username)
    # have no resolvable admin.
    admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parameters_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False)

    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    request_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Nullable until real system actions (with a subprocess exit code and
    # a measurable duration) are introduced on top of this foundation.
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
