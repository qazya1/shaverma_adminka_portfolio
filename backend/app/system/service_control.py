"""Business-logic layer between the API and the ActionRegistry for
controlling shaverma backend systemd units.

    API -> ServiceControlService -> ActionRegistry -> CommandExecutor -> Ubuntu

This is where "does this unit exist" gets decided, where a
services.system_name value gets turned into a concrete unit name (and
validated before it does), and where the raw stdout of `systemctl show`
gets turned into something the API can return as JSON. The registry
lookups and CommandSpec construction stay in app.system.service_actions;
nothing here spawns a process directly.
"""

import re
from dataclasses import dataclass

from app.system.exceptions import InvalidSystemNameError, ServiceNotFoundError, SystemExecutionError
from app.system.models import CommandResult
from app.system.registry import ActionRegistry

UNIT_SUFFIX = "-backend.service"

# shaverma's services.system_name is a MySQL varchar(30) with no format
# constraint of its own -- real values include bare domains (e.g.
# "shashl.ru"), so dots are allowed. What's actually unsafe here is only
# ever "/" (this value becomes a single filesystem path component *and*
# a single systemd unit name component -- a "/" would let it escape into
# a different one) and the value being exactly "." or ".." (a
# self-reference/parent-directory path component); requiring the first
# character to be alphanumeric rules out both of those, since neither
# starts with one. Not the injection boundary itself either way --
# CommandExecutor never uses a shell, so there is no injection surface
# even for a value that failed this check.
_SYSTEM_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,29}$")


def unit_name_for(system_name: str) -> str:
    if not _SYSTEM_NAME_RE.fullmatch(system_name):
        raise InvalidSystemNameError(f"invalid system_name: {system_name!r}")
    return f"{system_name}{UNIT_SUFFIX}"


@dataclass(frozen=True)
class UnitStatus:
    exists: bool
    load_state: str | None
    active_state: str | None
    sub_state: str | None
    unit_file_state: str | None


def _parse_systemctl_show(stdout: str) -> dict[str, str]:
    """Parse `systemctl show --property=...` output (one `Key=Value` pair
    per line) into a dict. Deliberately tolerant of blank/malformed
    lines rather than raising -- a status read should never 500 just
    because of unexpected extra output."""

    props: dict[str, str] = {}
    for line in stdout.splitlines():
        key, sep, value = line.partition("=")
        if not sep:
            continue
        props[key] = value
    return props


class ServiceControlService:
    def __init__(self, registry: ActionRegistry) -> None:
        self._registry = registry

    async def get_status(self, system_name: str) -> UnitStatus:
        return await self._status_for_unit(unit_name_for(system_name))

    async def start(self, system_name: str) -> tuple[UnitStatus, CommandResult]:
        return await self._control("service.start", system_name)

    async def stop(self, system_name: str) -> tuple[UnitStatus, CommandResult]:
        return await self._control("service.stop", system_name)

    async def restart(self, system_name: str) -> tuple[UnitStatus, CommandResult]:
        """Stop then start, rather than a single `systemctl restart` --
        deliberately reuses the two verbs already granted in sudoers
        (service.start / service.stop, see the README's sudoers section)
        instead of needing a third NOPASSWD rule just for this. Same
        observable effect for our purposes: whatever process was running
        the unit's old code is gone, and a fresh one picks up whatever
        was just installed underneath it (see app.api.services --
        replacing an already-deployed service's backend files).

        Raises ServiceNotFoundError (from the `stop` call) if the unit
        doesn't exist at all -- same as calling stop()/start() directly
        would. Runs `start` regardless of whether `stop`'s own
        CommandResult reported success, so a merely-already-stopped unit
        (the common case: `systemctl stop` on a stopped unit exits 0
        anyway) never skips the start half; the returned CommandResult is
        `start`'s, since that's the one that decides whether the new code
        ended up running."""

        await self._control("service.stop", system_name)
        return await self._control("service.start", system_name)

    async def _control(self, action_name: str, system_name: str) -> tuple[UnitStatus, CommandResult]:
        unit_name = unit_name_for(system_name)

        # Never attempt to start/stop a unit that doesn't exist -- fail
        # with a clear, specific error instead of letting a confusing
        # sudo/systemctl failure bubble up.
        current = await self._status_for_unit(unit_name)
        if not current.exists:
            raise ServiceNotFoundError(unit_name)

        action = self._get_action(action_name)
        result = await action.run(unit_name=unit_name)

        new_status = await self._status_for_unit(unit_name)
        return new_status, result

    async def _status_for_unit(self, unit_name: str) -> UnitStatus:
        action = self._get_action("service.status")
        result = await action.run(unit_name=unit_name)

        props = _parse_systemctl_show(result.stdout)
        load_state = props.get("LoadState")
        # A unit that was never installed reports LoadState=not-found;
        # everything else (loaded, masked, error, ...) counts as "exists"
        # for our purposes -- the panel just needs to know whether there
        # is anything to show a live status for.
        exists = load_state not in (None, "", "not-found")

        return UnitStatus(
            exists=exists,
            load_state=load_state,
            active_state=props.get("ActiveState") if exists else None,
            sub_state=props.get("SubState") if exists else None,
            unit_file_state=props.get("UnitFileState") if exists else None,
        )

    def _get_action(self, name: str):
        action = self._registry.get(name)
        if action is None:
            raise SystemExecutionError(f"required system action is not registered: {name}")
        return action
