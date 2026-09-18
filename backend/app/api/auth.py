"""Two-stage (password + Telegram OTP) authentication endpoints."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.audit import service as audit_service
from app.auth import otp as otp_module
from app.auth import password as password_module
from app.auth import sessions as sessions_module
from app.auth.dependencies import get_current_admin, get_current_session, require_csrf
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import generate_secure_token
from app.models.admin import AdminUser
from app.models.auth import AdminLoginChallenge, AdminSession
from app.schemas.auth import (
    LoginStartRequest,
    LoginStartResponse,
    LoginVerifyRequest,
    LoginVerifyResponse,
    LogoutResponse,
    MeResponse,
)
from app.telegram.client import TelegramClient, TelegramDeliveryError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Errors returned to the client are intentionally generic so that neither
# endpoint can be used to enumerate valid usernames or probe challenge
# state.
_GENERIC_LOGIN_ERROR = "Invalid credentials"
_GENERIC_OTP_ERROR = "Invalid or expired code"

# Coarse, in-process brute-force guards on top of the per-challenge
# attempt counter enforced in app.auth.otp. See app.core.rate_limit for
# the known limitations of this approach.
_login_start_limiter = InMemoryRateLimiter(max_attempts=10, window_seconds=60)
_login_verify_limiter = InMemoryRateLimiter(max_attempts=20, window_seconds=60)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _set_session_cookies(response: Response, settings: Settings, session_token: str, csrf_token: str) -> None:
    common = {
        "secure": settings.is_production,
        "samesite": "strict",
        "max_age": settings.admin_session_ttl_seconds,
        "path": "/",
        # None (default) -> host-only, same as before COOKIE_DOMAIN
        # existed. Set it when the frontend and backend are on different
        # subdomains -- see the setting's own docstring in core/config.py.
        "domain": settings.cookie_domain,
    }
    response.set_cookie(key=settings.session_cookie_name, value=session_token, httponly=True, **common)
    # The CSRF cookie must be readable by frontend JS (double-submit
    # pattern), so it is deliberately NOT HttpOnly.
    response.set_cookie(key=settings.csrf_cookie_name, value=csrf_token, httponly=False, **common)


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    # domain must match what the cookie was actually set with, or the
    # browser won't recognize this as clearing the same cookie.
    response.delete_cookie(settings.session_cookie_name, path="/", domain=settings.cookie_domain)
    response.delete_cookie(settings.csrf_cookie_name, path="/", domain=settings.cookie_domain)


@router.post("/login/start", response_model=LoginStartResponse)
def login_start(
    payload: LoginStartRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LoginStartResponse:
    ip = _client_ip(request)
    request_id = _request_id(request)

    if not _login_start_limiter.check(ip or "unknown"):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts")

    admin = db.query(AdminUser).filter(AdminUser.username == payload.username).one_or_none()

    password_ok = admin is not None and admin.is_active and password_module.verify_password(
        payload.password, admin.password_hash
    )

    if not password_ok:
        audit_service.record_event(
            db,
            action="auth.login.password_failed",
            status="failure",
            admin_id=admin.id if admin is not None else None,
            target=payload.username,
            request_id=request_id,
            request_ip=ip,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_LOGIN_ERROR)

    admin_id = admin.id
    new_challenge = otp_module.create_challenge(db, admin, settings, ip)
    challenge_id = new_challenge.challenge.id
    expires_at = new_challenge.challenge.expires_at

    try:
        TelegramClient(settings).send_login_code(admin.telegram_user_id, new_challenge.code)
    except TelegramDeliveryError:
        # Roll back the challenge we just created -- it was never
        # delivered, so it must not be usable.
        db.rollback()
        audit_service.record_event(
            db,
            action="auth.login.otp_requested",
            status="failure",
            admin_id=admin_id,
            request_id=request_id,
            request_ip=ip,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to deliver login code"
        ) from None

    audit_service.record_event(
        db,
        action="auth.login.otp_requested",
        status="success",
        admin_id=admin_id,
        target=str(challenge_id),
        request_id=request_id,
        request_ip=ip,
    )
    db.commit()

    return LoginStartResponse(challenge_id=challenge_id, expires_at=expires_at)


@router.post("/login/verify", response_model=LoginVerifyResponse)
def login_verify(
    payload: LoginVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LoginVerifyResponse:
    ip = _client_ip(request)
    request_id = _request_id(request)

    if not _login_verify_limiter.check(ip or "unknown"):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts")

    challenge = db.get(AdminLoginChallenge, payload.challenge_id)
    result = otp_module.verify_challenge(db, challenge, payload.code, settings)

    if result is not otp_module.OtpVerifyResult.OK:
        audit_service.record_event(
            db,
            action="auth.login.otp_failed",
            status="failure",
            admin_id=challenge.admin_id if challenge is not None else None,
            target=str(payload.challenge_id),
            parameters={"reason": result.value},
            request_id=request_id,
            request_ip=ip,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_OTP_ERROR)

    admin = db.get(AdminUser, challenge.admin_id)
    if admin is None or not admin.is_active:
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_OTP_ERROR)

    user_agent = request.headers.get("user-agent")
    new_session = sessions_module.create_session(db, admin, settings, ip, user_agent)
    admin.last_login_at = datetime.now(UTC)

    audit_service.record_event(
        db,
        action="auth.login.success",
        status="success",
        admin_id=admin.id,
        request_id=request_id,
        request_ip=ip,
    )
    db.commit()

    csrf_token = generate_secure_token(16)
    _set_session_cookies(response, settings, new_session.token, csrf_token)

    return LoginVerifyResponse(admin=admin)


@router.get("/me", response_model=MeResponse)
def me(admin: AdminUser = Depends(get_current_admin)) -> MeResponse:
    return MeResponse(admin=admin)


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    session: AdminSession = Depends(get_current_session),
    _csrf: None = Depends(require_csrf),
) -> LogoutResponse:
    ip = _client_ip(request)
    request_id = _request_id(request)

    sessions_module.revoke_session(db, session)

    audit_service.record_event(
        db,
        action="auth.logout",
        status="success",
        admin_id=session.admin_id,
        request_id=request_id,
        request_ip=ip,
    )
    db.commit()

    _clear_session_cookies(response, settings)

    return LogoutResponse()
