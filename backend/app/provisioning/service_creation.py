"""Step 1 of the new-service wizard: create the `services` row itself.

Pure DB work -- no filesystem/systemd/nginx side effects here at all.
"""

import json
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.external.models import ManagedService
from app.provisioning.domain import InvalidDomainLabelError, build_service_urls

# Same identifier rules as app.system.service_control._SYSTEM_NAME_RE --
# dots allowed (real system_names include bare domains); only "/" and
# the exact values "."/".." are actually unsafe for what this becomes
# (a filesystem path component and a systemd unit name component), and
# requiring the first character to be alphanumeric rules both out.
_SYSTEM_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,29}$")

_SUPPORTED_CHANNEL_CHOICES = ("telegram", "max")


class DuplicateFieldError(ValueError):
    """Raised when a value that must be unique is already used by
    another row in shaverma's own `services` table."""

    def __init__(self, field: str) -> None:
        super().__init__(f"{field} is already in use")
        self.field = field


class InvalidSystemNameError(ValueError):
    pass


@dataclass(frozen=True)
class NewServiceInput:
    label: str  # third-level domain label, e.g. "индия"
    name: str
    system_name: str
    is_active: bool
    supported_channels: list[str]
    bot_entry_key: str | None
    client_bot_entry_key: str | None


def _validate_system_name(system_name: str) -> None:
    if not _SYSTEM_NAME_RE.fullmatch(system_name):
        raise InvalidSystemNameError(f"invalid system_name: {system_name!r}")


def _validate_channels(channels: list[str]) -> list[str]:
    unknown = set(channels) - set(_SUPPORTED_CHANNEL_CHOICES)
    if unknown:
        raise ValueError(f"unsupported channel(s): {sorted(unknown)}")
    # Stable, predictable order regardless of what the client sent.
    return [c for c in _SUPPORTED_CHANNEL_CHOICES if c in channels]


def _check_unique(db: Session, field, value: str, field_name: str) -> None:
    if value is None:
        return
    exists = db.execute(select(ManagedService.id).where(field == value)).first()
    if exists is not None:
        raise DuplicateFieldError(field_name)


def create_service(db: Session, data: NewServiceInput, domain_zone: str) -> ManagedService:
    """Validate everything, then insert the new `services` row. Raises
    InvalidDomainLabelError / InvalidSystemNameError / DuplicateFieldError
    on any problem -- callers should not commit a partially-valid row."""

    _validate_system_name(data.system_name)
    channels = _validate_channels(data.supported_channels)
    url, backend_base_url = build_service_urls(data.label, domain_zone)

    _check_unique(db, ManagedService.url, url, "url")
    _check_unique(db, ManagedService.system_name, data.system_name, "system_name")
    _check_unique(db, ManagedService.bot_entry_key, data.bot_entry_key, "bot_entry_key")
    _check_unique(db, ManagedService.client_bot_entry_key, data.client_bot_entry_key, "client_bot_entry_key")

    row = ManagedService(
        name=data.name,
        is_active=data.is_active,
        system_name=data.system_name,
        url=url,
        backend_base_url=backend_base_url,
        bot_entry_key=data.bot_entry_key,
        client_bot_entry_key=data.client_bot_entry_key,
        supported_channels=json.dumps(channels),
    )
    db.add(row)
    db.flush()
    return row


__all__ = [
    "NewServiceInput",
    "DuplicateFieldError",
    "InvalidSystemNameError",
    "InvalidDomainLabelError",
    "create_service",
]
