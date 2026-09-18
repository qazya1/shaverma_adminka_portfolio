"""Second factor: Telegram-delivered one-time codes."""

import enum
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import constant_time_equals, generate_numeric_code, hmac_digest_hex
from app.models.admin import AdminUser
from app.models.auth import AdminLoginChallenge


class OtpVerifyResult(enum.Enum):
    OK = "ok"
    NOT_FOUND = "not_found"
    ALREADY_CONSUMED = "already_consumed"
    EXPIRED = "expired"
    NO_ATTEMPTS_LEFT = "no_attempts_left"
    INCORRECT = "incorrect"


@dataclass
class NewChallenge:
    challenge: AdminLoginChallenge
    code: str


def create_challenge(
    db: Session,
    admin: AdminUser,
    settings: Settings,
    request_ip: str | None,
) -> NewChallenge:
    """Create a new login challenge and return it together with the raw
    (plaintext) code -- the caller is responsible for sending the code to
    the admin's Telegram chat and MUST NOT log or persist the plaintext
    value anywhere else.
    """

    code = generate_numeric_code(settings.admin_otp_code_length)
    now = datetime.now(UTC)

    challenge = AdminLoginChallenge(
        admin_id=admin.id,
        code_digest=hmac_digest_hex(settings.admin_otp_secret, code),
        expires_at=now + timedelta(seconds=settings.admin_otp_ttl_seconds),
        attempts_left=settings.admin_otp_max_attempts,
        request_ip=request_ip,
    )
    db.add(challenge)
    db.flush()

    return NewChallenge(challenge=challenge, code=code)


def verify_challenge(
    db: Session,
    challenge: AdminLoginChallenge | None,
    code: str,
    settings: Settings,
) -> OtpVerifyResult:
    """Validate a submitted code against a stored challenge.

    On any outcome other than OK, the challenge's state (attempts_left /
    consumed_at) is updated and flushed so repeated guesses are bounded
    and a challenge can never be replayed after success.
    """

    if challenge is None:
        return OtpVerifyResult.NOT_FOUND

    if challenge.consumed_at is not None:
        return OtpVerifyResult.ALREADY_CONSUMED

    now = datetime.now(UTC)
    expires_at = challenge.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        return OtpVerifyResult.EXPIRED

    if challenge.attempts_left <= 0:
        challenge.consumed_at = now
        db.flush()
        return OtpVerifyResult.NO_ATTEMPTS_LEFT

    expected_digest = challenge.code_digest
    actual_digest = hmac_digest_hex(settings.admin_otp_secret, code)

    if not constant_time_equals(expected_digest, actual_digest):
        challenge.attempts_left -= 1
        if challenge.attempts_left <= 0:
            challenge.consumed_at = now
        db.flush()
        return OtpVerifyResult.INCORRECT

    challenge.consumed_at = now
    db.flush()
    return OtpVerifyResult.OK
