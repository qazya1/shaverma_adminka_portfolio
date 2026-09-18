"""Low-level cryptographic primitives shared across the auth layer.

Nothing in this module knows about HTTP, the database, or business logic --
it is pure crypto/random helpers so the auth code above stays easy to
audit.
"""

import hashlib
import hmac
import secrets


def generate_secure_token(n_bytes: int = 32) -> str:
    """Return a URL-safe, cryptographically secure random token."""

    return secrets.token_urlsafe(n_bytes)


def sha256_hex(value: str) -> str:
    """Deterministic SHA-256 digest, hex encoded.

    Used to store session tokens: the raw token only ever exists in the
    HttpOnly cookie handed to the browser, the database only ever sees
    this digest.
    """

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_numeric_code(length: int = 6) -> str:
    """Generate a cryptographically secure numeric one-time code."""

    if length <= 0:
        raise ValueError("length must be positive")
    digits = [secrets.choice("0123456789") for _ in range(length)]
    return "".join(digits)


def hmac_digest_hex(secret: str, value: str) -> str:
    """HMAC-SHA256 digest of `value` keyed by `secret`, hex encoded.

    Used to store OTP codes: never store the plaintext code, only this
    digest keyed by a server-side secret (ADMIN_OTP_SECRET).
    """

    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    """Timing-safe string comparison."""

    return hmac.compare_digest(a, b)
