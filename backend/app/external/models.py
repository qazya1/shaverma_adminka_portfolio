"""Read/write-mapped subset of the shaverma project's own `services`
table.

adminka does not own this table -- it lives in the shaverma repository
(https://github.com/Shira-Artem/shaverma), not here, and this project
never runs a migration against it. This model deliberately maps only the
columns the service-control panel and new-service wizard actually need;
the real table has two more (`signing_secret_enc`, `notify_api_key_hash`)
that adminka never reads or writes -- those are exclusively managed by
the separate "bot" project (see app/provisioning/credentials_script.py).

`ExternalBase` is intentionally a *different* declarative base than
`app.models.base.Base`: it is never included in adminka's own
`Base.metadata`, so it can never be picked up by Alembic autogenerate or
`target_metadata` (see backend/migrations/env.py) -- there is no
migration here that could create, alter, or drop `services`. Both bases
share the same physical `system_db` connection/engine at runtime, so
querying `ManagedService` through the normal `get_db()` session works
exactly like querying any admin_* model.

As of 2026-08, `services.system_name` already exists in system_db
(`varchar(30)`, nullable, no unique constraint) -- confirmed against the
live schema, so no migration was needed to introduce it. The columns
below (`url`, `bot_entry_key`, `client_bot_entry_key`,
`supported_channels`, `backend_base_url`) were all confirmed present the
same way when the new-service wizard was added, and `server_local_port`
(`int`, nullable) the same way again in 2026-08.
"""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ExternalBase(DeclarativeBase):
    pass


class ManagedService(ExternalBase):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # The systemd unit this service is controlled through is
    # f"{system_name}-backend.service" (see app.system.service_control).
    # Not every row has this set -- only services onboarded onto systemd
    # control do, and the panel only lists rows where it is.
    system_name: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Full URL (with scheme), punycode-encoded, e.g.
    # "https://xn--d1ahbs6g.xn----8sbwack8bga.xn--p1ai". Unique in
    # shaverma's own schema.
    url: Mapped[str] = mapped_column(String(300), nullable=False)
    backend_base_url: Mapped[str | None] = mapped_column(String(300), nullable=True)

    bot_entry_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    client_bot_entry_key: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # JSON-encoded array stored as plain text in shaverma's own schema
    # (not a JSON column type), e.g. '["telegram", "max"]'.
    supported_channels: Mapped[str] = mapped_column(String(200), nullable=False)

    # The local TCP port the backend systemd unit listens on (nginx
    # proxies to 127.0.0.1:<this>). NULL until the new-service wizard's
    # nginx step allocates one. This is the single source of truth for
    # "which ports are already spoken for" -- port_allocation.py reads
    # it directly instead of parsing the shared nginx config.
    server_local_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
