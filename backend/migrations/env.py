"""Alembic environment for the admin panel's own tables.

This migration history is fully independent from the shaverma project's
migrations even though both live in the same physical `system_db`:

- It tracks its own version table, `admin_alembic_version`, instead of
  the default `alembic_version` -- so it can never collide with (or be
  mistaken for) the shaverma project's own Alembic history in the same
  database.
- `include_object` restricts autogenerate to objects belonging to this
  app's tables (name starts with `admin_`), so `alembic revision
  --autogenerate` can never propose dropping or altering a table it
  doesn't own.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.models import Base  # noqa: F401  (imports all admin_* models)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

ADMIN_TABLE_PREFIX = "admin_"


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table":
        return name is not None and name.startswith(ADMIN_TABLE_PREFIX)
    # For columns/indexes/constraints, only compare within tables we own.
    table = getattr(obj, "table", None)
    if table is not None:
        return table.name.startswith(ADMIN_TABLE_PREFIX)
    return True


def _get_url() -> str:
    return get_settings().system_database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="admin_alembic_version",
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _get_url()

    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table="admin_alembic_version",
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
