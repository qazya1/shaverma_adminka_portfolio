"""Business-logic layer between the API and the ActionRegistry for
listing/editing a shaverma instance's DB-seed script pairs and running
one of them against its own database.

    API -> SeedControlService -> ActionRegistry -> CommandExecutor -> Ubuntu -> seed_helper.py

Mirrors app.system.env_file_control in shape and in the same defense in
depth: system_name/pair_key are validated with the same identifier
patterns before either is ever passed to a registry action.
"""

import re

from app.system.exceptions import InvalidSystemNameError, SystemExecutionError
from app.system.models import CommandResult

# Same identifier rules as seed_helper.py's own SYSTEM_NAME_RE/
# PAIR_KEY_RE -- kept as independent constants here for the same reason
# env_file_control.py keeps its own copy of the system_name pattern:
# this module's safety shouldn't depend on the helper script's regex
# staying unchanged underneath it.
_SYSTEM_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,29}$")
_PAIR_KEY_RE = re.compile(r"^[A-Za-z0-9_]{0,50}$")

# seed_helper.py's own exit codes -- see that script's docstring.
HELPER_NOT_FOUND_EXIT_CODE = 3


def validate_system_name(system_name: str) -> None:
    if not _SYSTEM_NAME_RE.fullmatch(system_name):
        raise InvalidSystemNameError(f"invalid system_name: {system_name!r}")


class InvalidPairKeyError(SystemExecutionError):
    """Raised when a submitted pair_key is not a valid seed-pair
    identifier (see seed_helper.py's own PAIR_KEY_RE)."""


def validate_pair_key(pair_key: str) -> None:
    if not _PAIR_KEY_RE.fullmatch(pair_key):
        raise InvalidPairKeyError(f"invalid pair_key: {pair_key!r}")


class SeedPairNotFoundError(SystemExecutionError):
    """Raised when the named pair_key doesn't correspond to an existing
    seed data file -- for read_data/write_data only. run_db's own "not
    found" case (the db script missing) is deliberately NOT raised this
    way -- see SeedControlService.run_db's docstring for why."""

    def __init__(self, system_name: str, pair_key: str) -> None:
        super().__init__(f"seed pair not found: system_name={system_name!r} pair_key={pair_key!r}")
        self.system_name = system_name
        self.pair_key = pair_key


_PAIR_LINE_RE = re.compile(r"^PAIR=(.*)$")


def parse_pair_list(stdout: str) -> list[str]:
    """Parses seed_helper.py `list`'s `PAIR=<pair_key>` lines. Any other
    line is ignored rather than raising -- a listing should never fail
    just because of unexpected extra output."""

    pairs = []
    for line in stdout.splitlines():
        match = _PAIR_LINE_RE.fullmatch(line)
        if match:
            pairs.append(match.group(1))
    return pairs


class SeedControlService:
    def __init__(self, registry) -> None:
        self._registry = registry

    async def list_pairs(self, system_name: str) -> list[str]:
        validate_system_name(system_name)
        action = self._get_action("seed.list")
        result = await action.run(system_name=system_name)

        if result.exit_code == 0:
            return parse_pair_list(result.stdout)
        if result.exit_code == HELPER_NOT_FOUND_EXIT_CODE:
            # No seed/ directory at all for this instance -- e.g. its
            # uploaded backend never had one. Not an error: just nothing
            # to seed, same "treat as empty" as env_file_control.read()
            # does for a missing .env.
            return []
        raise SystemExecutionError(
            f"seed_helper.py list failed (exit {result.exit_code}): {result.stderr.strip()}"
        )

    async def read_data(self, system_name: str, pair_key: str) -> str:
        validate_system_name(system_name)
        validate_pair_key(pair_key)
        action = self._get_action("seed.read_data")
        result = await action.run(system_name=system_name, pair_key=pair_key)

        if result.exit_code == 0:
            return result.stdout
        if result.exit_code == HELPER_NOT_FOUND_EXIT_CODE:
            raise SeedPairNotFoundError(system_name, pair_key)
        raise SystemExecutionError(
            f"seed_helper.py read_data failed (exit {result.exit_code}): {result.stderr.strip()}"
        )

    async def write_data(self, system_name: str, pair_key: str, content: str) -> None:
        validate_system_name(system_name)
        validate_pair_key(pair_key)
        action = self._get_action("seed.write_data")
        result = await action.run(system_name=system_name, pair_key=pair_key, content=content.encode("utf-8"))

        if result.exit_code == 0:
            return
        if result.exit_code == HELPER_NOT_FOUND_EXIT_CODE:
            raise SeedPairNotFoundError(system_name, pair_key)
        raise SystemExecutionError(
            f"seed_helper.py write_data failed (exit {result.exit_code}): {result.stderr.strip()}"
        )

    async def run_db(self, system_name: str, pair_key: str) -> CommandResult:
        """Runs the pair's seed_db script and returns the raw
        CommandResult, unlike every other method here -- deliberately no
        exit-code-based error mapping (e.g. "not found" ->  a typed
        exception): seed_helper.py's `run_db` hands off to the seed
        script itself via `os.execve`, replacing the helper process
        entirely, so once that succeeds the exit code is the *seed
        script's own*, not the helper's -- exit code 3 after that point
        could mean either "helper's own pre-exec check failed" or "the
        seed script itself chose exit code 3" and can't be told apart
        from the exit code alone. The helper's own pre-exec failure
        still writes an unambiguous message to stderr before exiting
        (`seed db script not found: ...`), so a human reading the
        forwarded stdout/stderr always gets an accurate picture even
        though this layer doesn't try to interpret it -- see the API
        layer, which always returns the full CommandResult to the admin
        for exactly this reason.
        """

        validate_system_name(system_name)
        validate_pair_key(pair_key)
        action = self._get_action("seed.run_db")
        return await action.run(system_name=system_name, pair_key=pair_key)

    def _get_action(self, name: str):
        action = self._registry.get(name)
        if action is None:
            raise SystemExecutionError(f"required system action is not registered: {name}")
        return action
