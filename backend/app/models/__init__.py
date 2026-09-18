"""SQLAlchemy models owned by the admin panel.

Importing this package registers all admin_* tables on `Base.metadata`,
which Alembic's env.py relies on for autogenerate/target metadata.
"""

from app.models.admin import AdminUser
from app.models.audit import AdminAuditEvent
from app.models.auth import AdminLoginChallenge, AdminSession
from app.models.base import Base

__all__ = [
    "Base",
    "AdminUser",
    "AdminLoginChallenge",
    "AdminSession",
    "AdminAuditEvent",
]
