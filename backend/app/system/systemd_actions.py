"""SystemAction for writing a new instance's systemd unit file via the
privileged systemd_unit_helper.py (writes the file + runs `systemctl
daemon-reload`, both inside that already-root helper process -- see that
script's docstring)."""

from app.system.executor import CommandExecutor
from app.system.models import CommandResult, CommandSpec


class SystemdWriteUnitAction:
    name = "systemd.write_unit"

    def __init__(self, executor: CommandExecutor, helper_path: str, sudo_path: str, timeout_seconds: float) -> None:
        self._executor = executor
        self._helper_path = helper_path
        self._sudo_path = sudo_path
        self._timeout_seconds = timeout_seconds

    async def run(self, **kwargs: object) -> CommandResult:
        system_name = str(kwargs["system_name"])
        content = kwargs["content"]
        assert isinstance(content, bytes)
        spec = CommandSpec(
            executable=self._sudo_path,
            args=(self._helper_path, "write", system_name),
            timeout_seconds=self._timeout_seconds,
            stdin=content,
        )
        return await self._executor.run(spec)
