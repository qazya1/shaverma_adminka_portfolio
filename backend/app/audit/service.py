"""Audit logging service.

Centralizing writes here (rather than letting every call site `db.add(
AdminAuditEvent(...))` directly) gives us one place to reason about what
is and isn't safe to persist.

NEVER pass any of the following into `parameters`:
  - password / password_hash
  - OTP codes
  - session tokens
  - the Telegram bot token
  - any other environment secret
Call sites are expected to only pass identifiers (usernames, challenge
ids, IPs, etc.), never secret material.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AdminAuditEvent

# Defensive allow-list-adjacent guard: if a caller accidentally includes a
# key that looks sensitive, drop it rather than persist it.
_FORBIDDEN_PARAM_KEYS = {
    "password",
    "password_hash",
    "otp",
    "otp_code",
    "code",
    "session_token",
    "token",
    "bot_token",
    "secret",
}


def _sanitize_parameters(parameters: dict[str, Any] | None) -> dict[str, Any] | None:
    if parameters is None:
        return None
    return {k: v for k, v in parameters.items() if k.lower() not in _FORBIDDEN_PARAM_KEYS}


def record_event(
    db: Session,
    *,
    action: str,
    status: str,
    admin_id: int | None = None,
    target: str | None = None,
    parameters: dict[str, Any] | None = None,
    request_id: str | None = None,
    request_ip: str | None = None,
    exit_code: int | None = None,
    duration_ms: int | None = None,
) -> AdminAuditEvent:
    event = AdminAuditEvent(
        admin_id=admin_id,
        action=action,
        target=target,
        parameters_json=_sanitize_parameters(parameters),
        status=status,
        request_id=request_id,
        request_ip=request_ip,
        exit_code=exit_code,
        duration_ms=duration_ms,
    )
    db.add(event)
    db.flush()
    return event
