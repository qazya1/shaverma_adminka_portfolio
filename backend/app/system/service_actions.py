"""Concrete SystemAction implementations for controlling shaverma
backend systemd units.

Each one only knows how to build one specific CommandSpec and run it --
unit name validation, "does this unit exist" interpretation, and
audit-relevant decisions all live one layer up, in
app.system.service_control.ServiceControlService. Nothing here accepts
an arbitrary command string; the unit name is the only variable part,
and it is always passed as a single argv element, never interpolated
into a shell string. See app.system.bootstrap for where these get
registered into the ActionRegistry.
"""

from app.system.executor import CommandExecutor
from app.system.models import CommandResult, CommandSpec

_STATUS_PROPERTIES = "LoadState,ActiveState,SubState,UnitFileState"


class _BaseSystemctlAction:
    def __init__(
        self,
        executor: CommandExecutor,
        systemctl_path: str,
        timeout_seconds: float,
        max_output_bytes: int,
    ) -> None:
        self._executor = executor
        self._systemctl_path = systemctl_path
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes

    def _spec(self, executable: str, args: tuple[str, ...]) -> CommandSpec:
        return CommandSpec(
            executable=executable,
            args=args,
            timeout_seconds=self._timeout_seconds,
            max_output_bytes=self._max_output_bytes,
        )


class ServiceStatusAction(_BaseSystemctlAction):
    """Read-only: `systemctl show <unit>`. Never needs sudo -- unit state
    is readable by any local user through the systemd D-Bus policy."""

    name = "service.status"

    async def run(self, **kwargs: object) -> CommandResult:
        unit_name = str(kwargs["unit_name"])
        spec = self._spec(
            self._systemctl_path,
            ("show", unit_name, "--no-page", f"--property={_STATUS_PROPERTIES}"),
        )
        return await self._executor.run(spec)


class _SudoSystemctlVerbAction(_BaseSystemctlAction):
    """Base for actions that mutate a unit's running state and therefore
    need root -- always via a narrowly scoped `sudo systemctl <verb>
    <unit>`, never a bare privileged shell."""

    verb: str

    def __init__(
        self,
        executor: CommandExecutor,
        systemctl_path: str,
        sudo_path: str,
        timeout_seconds: float,
        max_output_bytes: int,
    ) -> None:
        super().__init__(executor, systemctl_path, timeout_seconds, max_output_bytes)
        self._sudo_path = sudo_path

    async def run(self, **kwargs: object) -> CommandResult:
        unit_name = str(kwargs["unit_name"])
        spec = self._spec(self._sudo_path, (self._systemctl_path, self.verb, unit_name))
        return await self._executor.run(spec)


class ServiceStartAction(_SudoSystemctlVerbAction):
    name = "service.start"
    verb = "start"


class ServiceStopAction(_SudoSystemctlVerbAction):
    name = "service.stop"
    verb = "stop"


class ServiceEnableNowAction(_BaseSystemctlAction):
    """`sudo systemctl enable --now <unit>` -- used once, right after a
    brand-new unit is written (see app.system.systemd_actions), so it
    both starts immediately and survives a reboot. Existing units
    controlled from the dashboard never call this -- they're already
    enabled."""

    name = "service.enable_now"

    def __init__(
        self,
        executor: CommandExecutor,
        systemctl_path: str,
        sudo_path: str,
        timeout_seconds: float,
        max_output_bytes: int,
    ) -> None:
        super().__init__(executor, systemctl_path, timeout_seconds, max_output_bytes)
        self._sudo_path = sudo_path

    async def run(self, **kwargs: object) -> CommandResult:
        unit_name = str(kwargs["unit_name"])
        spec = self._spec(self._sudo_path, (self._systemctl_path, "enable", "--now", unit_name))
        return await self._executor.run(spec)
