"""Concrete SystemAction implementations for reading/writing a shaverma
instance's root-owned .env file via the privileged env_file_helper.py
script (see that file and the README's sudoers section).

Both actions always go through sudo -- unlike service.status, there is
no unprivileged way to read a root-owned, non-world-readable .env file.
Neither action accepts a filesystem path from its caller: only a
system_name, which the helper script itself validates and confines to
its own fixed PROJECT_ROOT. Unit-name-style validation also happens one
layer up, in app.system.env_file_control, before an action is ever
invoked.
"""

from app.system.executor import CommandExecutor
from app.system.models import CommandResult, CommandSpec


class _BaseEnvHelperAction:
    def __init__(
        self,
        executor: CommandExecutor,
        helper_path: str,
        sudo_path: str,
        timeout_seconds: float,
        max_output_bytes: int,
    ) -> None:
        self._executor = executor
        self._helper_path = helper_path
        self._sudo_path = sudo_path
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes

    def _spec(self, args: tuple[str, ...], stdin: bytes | None = None) -> CommandSpec:
        return CommandSpec(
            executable=self._sudo_path,
            args=args,
            timeout_seconds=self._timeout_seconds,
            max_output_bytes=self._max_output_bytes,
            stdin=stdin,
        )


class EnvReadAction(_BaseEnvHelperAction):
    name = "env.read"

    async def run(self, **kwargs: object) -> CommandResult:
        system_name = str(kwargs["system_name"])
        spec = self._spec((self._helper_path, "read", system_name))
        return await self._executor.run(spec)


class EnvWriteAction(_BaseEnvHelperAction):
    name = "env.write"

    async def run(self, **kwargs: object) -> CommandResult:
        system_name = str(kwargs["system_name"])
        content = kwargs["content"]
        assert isinstance(content, bytes)
        spec = self._spec((self._helper_path, "write", system_name), stdin=content)
        return await self._executor.run(spec)
