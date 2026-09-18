"""Declarative base for the admin panel's own tables.

This Base/metadata is intentionally isolated from the shaverma project's
ORM: this project never imports shaverma's models, and this Base's
metadata only ever contains the admin_* tables owned by this service.
Alembic (see backend/migrations) is configured to track only this
metadata, in its own `admin_alembic_version` table, so its migration
history cannot collide with the main shaverma project's migrations even
though both live in the same physical database.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
