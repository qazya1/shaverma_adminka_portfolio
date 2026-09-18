"""Concrete SystemActions for provisioning a new shaverma instance's
directory tree via the privileged instance_files_helper.py (see that
script and the README's sudoers section).

Like env_actions.py, these always go through sudo -- shaverma-admin has
no direct write access to the root-owned instance tree at all, by
design. None of these accept a filesystem path from the caller, only
`system_name`.
"""

from app.system.executor import CommandExecutor
from app.system.models import CommandResult, CommandSpec


class _BaseInstanceFilesAction:
    def __init__(self, executor: CommandExecutor, helper_path: str, sudo_path: str, timeout_seconds: float) -> None:
        self._executor = executor
        self._helper_path = helper_path
        self._sudo_path = sudo_path
        self._timeout_seconds = timeout_seconds

    async def _run(self, verb: str, system_name: str) -> CommandResult:
        spec = CommandSpec(
            executable=self._sudo_path,
            args=(self._helper_path, verb, system_name),
            timeout_seconds=self._timeout_seconds,
        )
        return await self._executor.run(spec)


class InstanceCreateTreeAction(_BaseInstanceFilesAction):
    name = "instance.create_tree"

    async def run(self, **kwargs: object) -> CommandResult:
        return await self._run("create_tree", str(kwargs["system_name"]))


class InstanceInstallBackendAction(_BaseInstanceFilesAction):
    name = "instance.install_backend"

    async def run(self, **kwargs: object) -> CommandResult:
        return await self._run("install_backend", str(kwargs["system_name"]))


class InstanceInstallDistAction(_BaseInstanceFilesAction):
    name = "instance.install_dist"

    async def run(self, **kwargs: object) -> CommandResult:
        return await self._run("install_dist", str(kwargs["system_name"]))
