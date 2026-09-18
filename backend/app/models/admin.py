"""Admin user model.

There are exactly two administrators, they are fully equal (no roles, no
permissions, no groups). There is deliberately no way to create one
through the running app -- no HTTP endpoint, no admin-facing UI, nothing
`app.main` serves or imports. `backend/create_admin.py` is a local-only
convenience over the manual `hash_password()` + `INSERT INTO
admin_users` steps this used to require by hand: it still needs a shell
on the box (or a checkout pointed at the real database) to run, it is
never deployed as, or reachable through, the service itself. See the
README's "Administrators" section.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # The admin's numeric Telegram user id (not a phone number, and not a
    # chat id in the general sense -- for a private bot<->user chat these
    # coincide, but this column names what it actually is: the identity
    # of the Telegram account the OTP is delivered to).
    telegram_user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
