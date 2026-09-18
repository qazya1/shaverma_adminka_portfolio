"""Concrete SystemAction implementations for listing/editing a shaverma
instance's DB-seed script pairs and running one of them, via the
privileged seed_helper.py script (see that file and the README's
sudoers section).

Same defense in depth as env_actions.py/instance_actions.py: always via
sudo, never a filesystem path from the caller -- only system_name and
pair_key, both re-validated one layer up in app.system.seed_control
before an action is ever invoked.
"""

from app.system.executor import CommandExecutor
from app.system.models import CommandResult, CommandSpec


class _BaseSeedHelperAction:
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

    def _spec(
        self,
        args: tuple[str, ...],
        stdin: bytes | None = None,
        timeout_seconds: float | None = None,
    ) -> CommandSpec:
        return CommandSpec(
            executable=self._sudo_path,
            args=args,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else self._timeout_seconds,
            max_output_bytes=self._max_output_bytes,
            stdin=stdin,
        )


class SeedListAction(_BaseSeedHelperAction):
    name = "seed.list"

    async def run(self, **kwargs: object) -> CommandResult:
        system_name = str(kwargs["system_name"])
        spec = self._spec((self._helper_path, "list", system_name))
        return await self._executor.run(spec)


class SeedReadDataAction(_BaseSeedHelperAction):
    name = "seed.read_data"

    async def run(self, **kwargs: object) -> CommandResult:
        system_name = str(kwargs["system_name"])
        pair_key = str(kwargs["pair_key"])
        spec = self._spec((self._helper_path, "read_data", system_name, pair_key))
        return await self._executor.run(spec)


class SeedWriteDataAction(_BaseSeedHelperAction):
    name = "seed.write_data"

    async def run(self, **kwargs: object) -> CommandResult:
        system_name = str(kwargs["system_name"])
        pair_key = str(kwargs["pair_key"])
        content = kwargs["content"]
        assert isinstance(content, bytes)
        spec = self._spec((self._helper_path, "write_data", system_name, pair_key), stdin=content)
        return await self._executor.run(spec)


class SeedRunDbAction(_BaseSeedHelperAction):
    """Runs a seed_db script against the instance's own database --
    legitimately slower than every other action here (bulk DB writes,
    not a filesystem operation), so this is the one action in this
    module that gets its own, separately configured timeout rather than
    reusing the shared system_command_timeout_seconds."""

    name = "seed.run_db"

    def __init__(
        self,
        executor: CommandExecutor,
        helper_path: str,
        sudo_path: str,
        timeout_seconds: float,
        max_output_bytes: int,
        run_timeout_seconds: float,
    ) -> None:
        super().__init__(executor, helper_path, sudo_path, timeout_seconds, max_output_bytes)
        self._run_timeout_seconds = run_timeout_seconds

    async def run(self, **kwargs: object) -> CommandResult:
        system_name = str(kwargs["system_name"])
        pair_key = str(kwargs["pair_key"])
        spec = self._spec(
            (self._helper_path, "run_db", system_name, pair_key),
            timeout_seconds=self._run_timeout_seconds,
        )
        return await self._executor.run(spec)
