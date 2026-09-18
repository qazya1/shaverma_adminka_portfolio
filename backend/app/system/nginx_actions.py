"""Concrete SystemActions for adminka's shared nginx config: reading/
writing the file (via the privileged nginx_config_helper.py) and
validating/reloading nginx itself.

`nginx.test` and `nginx.reload` take **no parameters at all** -- the
safest possible shape of sudo grant, since there is nothing for a caller
to influence.
"""

from app.system.executor import CommandExecutor
from app.system.models import CommandResult, CommandSpec


class _BaseSudoAction:
    def __init__(self, executor: CommandExecutor, sudo_path: str, timeout_seconds: float) -> None:
        self._executor = executor
        self._sudo_path = sudo_path
        self._timeout_seconds = timeout_seconds

    def _spec(self, args: tuple[str, ...], stdin: bytes | None = None) -> CommandSpec:
        return CommandSpec(
            executable=self._sudo_path,
            args=args,
            timeout_seconds=self._timeout_seconds,
            stdin=stdin,
        )


class NginxReadConfigAction(_BaseSudoAction):
    name = "nginx.read_config"

    def __init__(self, executor: CommandExecutor, helper_path: str, sudo_path: str, timeout_seconds: float) -> None:
        super().__init__(executor, sudo_path, timeout_seconds)
        self._helper_path = helper_path

    async def run(self, **kwargs: object) -> CommandResult:
        return await self._executor.run(self._spec((self._helper_path, "read")))


class NginxWriteConfigAction(_BaseSudoAction):
    name = "nginx.write_config"

    def __init__(self, executor: CommandExecutor, helper_path: str, sudo_path: str, timeout_seconds: float) -> None:
        super().__init__(executor, sudo_path, timeout_seconds)
        self._helper_path = helper_path

    async def run(self, **kwargs: object) -> CommandResult:
        content = kwargs["content"]
        assert isinstance(content, bytes)
        return await self._executor.run(self._spec((self._helper_path, "write"), stdin=content))


class NginxTestAction(_BaseSudoAction):
    name = "nginx.test"

    def __init__(self, executor: CommandExecutor, nginx_binary_path: str, sudo_path: str, timeout_seconds: float) -> None:
        super().__init__(executor, sudo_path, timeout_seconds)
        self._nginx_binary_path = nginx_binary_path

    async def run(self, **kwargs: object) -> CommandResult:
        return await self._executor.run(self._spec((self._nginx_binary_path, "-t")))


class NginxReloadAction(_BaseSudoAction):
    name = "nginx.reload"

    def __init__(self, executor: CommandExecutor, systemctl_path: str, sudo_path: str, timeout_seconds: float) -> None:
        super().__init__(executor, sudo_path, timeout_seconds)
        self._systemctl_path = systemctl_path

    async def run(self, **kwargs: object) -> CommandResult:
        return await self._executor.run(self._spec((self._systemctl_path, "reload", "nginx")))
