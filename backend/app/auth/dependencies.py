"""FastAPI dependencies for cookie-session authentication and CSRF
protection.

Sessions live in an HttpOnly cookie, which means they are immune to theft
via JS but are automatically attached by the browser to any request --
including cross-site ones. To protect state-changing endpoints, we use
the double-submit-cookie pattern: a second, non-HttpOnly CSRF cookie is
issued alongside the session, and its value must be echoed back in the
`X-CSRF-Token` header on every state-changing request. A cross-site
attacker can trigger the cookie-bearing request but cannot read the
CSRF cookie's value (blocked by the same-origin policy), so they cannot
supply a matching header.
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import constant_time_equals
from app.models.admin import AdminUser
from app.models.auth import AdminSession

from . import sessions as sessions_module


def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdminSession:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    session = sessions_module.get_active_session_by_token(db, token)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    sessions_module.touch_session(db, session)
    return session


def get_current_admin(
    session: AdminSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> AdminUser:
    admin = db.get(AdminUser, session.admin_id)
    if admin is None or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return admin


def require_csrf(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """Enforce the double-submit CSRF cookie/header pair on state-changing
    requests that rely on the session cookie.
    """

    cookie_value = request.cookies.get(settings.csrf_cookie_name)
    header_value = request.headers.get("x-csrf-token")

    if not cookie_value or not header_value or not constant_time_equals(cookie_value, header_value):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid")
