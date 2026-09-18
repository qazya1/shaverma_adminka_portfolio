"""Business-logic layer between the API and the ActionRegistry for
reading/writing a shaverma instance's root-owned .env file.

    API -> EnvFileControlService -> ActionRegistry -> CommandExecutor -> Ubuntu -> env_file_helper.py

Mirrors app.system.service_control in shape and in the same defense in
depth: system_name is validated with the same identifier pattern before
it's ever passed to the registry action, and the actions themselves
never let it be interpreted by a shell.

This module also owns the .env text format: parsing preserves comments
and blank lines (and their position) so editing through the table UI
doesn't silently discard an operator's own annotations; only KEY=VALUE
lines are ever added, changed, or removed.
"""

import re
from dataclasses import dataclass

from app.system.exceptions import InvalidSystemNameError, SystemExecutionError

# Same identifier rules as app.system.service_control._SYSTEM_NAME_RE
# (dots allowed -- real system_names include bare domains like
# "shashl.ru"; only "/" and the exact values "."/".." are actually
# unsafe here, see that module for why) -- kept as an independent
# constant (not imported) for the same reason env_file_helper.py keeps
# its own copy: this module's safety shouldn't depend on another
# module's regex staying unchanged underneath it.
_SYSTEM_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,29}$")

# Standard shell/dotenv environment variable name rules -- deliberately
# stricter than system_name (no hyphens, can't start with a digit) so
# every key this module accepts is valid wherever a .env file gets
# sourced.
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# env_file_helper.py's own exit codes -- see that script's docstring.
HELPER_INVALID_NAME_EXIT_CODE = 2
HELPER_NOT_FOUND_EXIT_CODE = 3


def validate_system_name(system_name: str) -> None:
    if not _SYSTEM_NAME_RE.fullmatch(system_name):
        raise InvalidSystemNameError(f"invalid system_name: {system_name!r}")


class InvalidEnvKeyError(ValueError):
    """Raised when a submitted key is not a valid environment variable
    name, or a submission contains the same key twice."""


class InvalidEnvValueError(ValueError):
    """Raised when a submitted value can't be represented on a single
    .env line (contains a newline/carriage-return/NUL byte)."""


class InstanceDirectoryNotFoundError(SystemExecutionError):
    """Raised when env_file_helper.py reports there is no instance
    directory at all for this system_name (the deploy hasn't happened,
    or system_name doesn't match a real instance)."""

    def __init__(self, system_name: str) -> None:
        super().__init__(f"instance directory not found for system_name={system_name!r}")
        self.system_name = system_name


@dataclass(frozen=True)
class EnvLine:
    kind: str  # "blank" | "comment" | "kv"
    raw: str = ""
    key: str | None = None
    value: str | None = None


def parse_env_file(content: str) -> list[EnvLine]:
    lines: list[EnvLine] = []
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            lines.append(EnvLine(kind="blank", raw=raw_line))
        elif stripped.startswith("#") or "=" not in raw_line:
            # Whole-line comments, and anything else that isn't a
            # well-formed KEY=VALUE line, are preserved verbatim rather
            # than dropped or misinterpreted.
            lines.append(EnvLine(kind="comment", raw=raw_line))
        else:
            key, _, value = raw_line.partition("=")
            lines.append(EnvLine(kind="kv", key=key.strip(), value=value))
    return lines


def render_env_file(lines: list[EnvLine]) -> str:
    rendered_lines = [f"{line.key}={line.value}" if line.kind == "kv" else line.raw for line in lines]
    text = "\n".join(rendered_lines)
    return text + "\n" if text else ""


def entries_from_lines(lines: list[EnvLine]) -> list[tuple[str, str]]:
    """The effective key -> value mapping: last occurrence of a repeated
    key wins (matches how dotenv loaders behave), in first-occurrence
    order."""

    values: dict[str, str] = {}
    order: list[str] = []
    for line in lines:
        if line.kind != "kv" or line.key is None:
            continue
        if line.key not in values:
            order.append(line.key)
        values[line.key] = line.value or ""
    return [(key, values[key]) for key in order]


def _validate_entries(entries: list[tuple[str, str]]) -> None:
    seen: set[str] = set()
    for key, value in entries:
        if not _ENV_KEY_RE.fullmatch(key):
            raise InvalidEnvKeyError(f"invalid environment variable name: {key!r}")
        if key in seen:
            raise InvalidEnvKeyError(f"duplicate key: {key!r}")
        seen.add(key)
        if "\n" in value or "\r" in value or "\x00" in value:
            raise InvalidEnvValueError(f"value for {key!r} contains a character that can't fit on one line")


@dataclass(frozen=True)
class EnvDiff:
    lines: list[EnvLine]
    added: set[str]
    removed: set[str]
    changed: set[str]


def apply_entries(lines: list[EnvLine], desired: list[tuple[str, str]]) -> EnvDiff:
    """Merge a full desired key/value set into the existing parsed lines.

    Comments and blank lines are untouched and keep their position. Keys
    that still exist keep their line's position with the new value; new
    keys are appended at the end in submission order; keys no longer
    present are dropped. A key that appeared more than once in the
    original file collapses to a single line, at the position of its
    first occurrence, on save.
    """

    _validate_entries(desired)
    desired_map = dict(desired)

    current_map = dict(entries_from_lines(lines))
    added = set(desired_map) - set(current_map)
    removed = set(current_map) - set(desired_map)
    changed = {key for key in (set(desired_map) & set(current_map)) if desired_map[key] != current_map[key]}

    new_lines: list[EnvLine] = []
    written_keys: set[str] = set()
    for line in lines:
        if line.kind != "kv":
            new_lines.append(line)
            continue
        key = line.key
        if key in written_keys or key not in desired_map:
            continue  # collapsed duplicate, or removed
        new_lines.append(EnvLine(kind="kv", key=key, value=desired_map[key]))
        written_keys.add(key)

    for key, value in desired:
        if key not in written_keys:
            new_lines.append(EnvLine(kind="kv", key=key, value=value))
            written_keys.add(key)

    return EnvDiff(lines=new_lines, added=added, removed=removed, changed=changed)


class EnvFileControlService:
    def __init__(self, registry) -> None:
        self._registry = registry

    async def read(self, system_name: str) -> list[EnvLine]:
        validate_system_name(system_name)
        action = self._get_action("env.read")
        result = await action.run(system_name=system_name)

        if result.exit_code == 0:
            return parse_env_file(result.stdout)
        if result.exit_code == HELPER_NOT_FOUND_EXIT_CODE:
            # No .env file yet for an otherwise-real instance -- treat as
            # empty rather than an error, so the panel can still be used
            # to create one.
            return []
        raise SystemExecutionError(
            f"env_file_helper.py read failed (exit {result.exit_code}): {result.stderr.strip()}"
        )

    async def write(self, system_name: str, desired: list[tuple[str, str]]) -> EnvDiff:
        validate_system_name(system_name)
        current_lines = await self.read(system_name)
        diff = apply_entries(current_lines, desired)

        content = render_env_file(diff.lines)
        action = self._get_action("env.write")
        result = await action.run(system_name=system_name, content=content.encode("utf-8"))

        if result.exit_code == 0:
            return diff
        if result.exit_code == HELPER_NOT_FOUND_EXIT_CODE:
            raise InstanceDirectoryNotFoundError(system_name)
        raise SystemExecutionError(
            f"env_file_helper.py write failed (exit {result.exit_code}): {result.stderr.strip()}"
        )

    def _get_action(self, name: str):
        action = self._registry.get(name)
        if action is None:
            raise SystemExecutionError(f"required system action is not registered: {name}")
        return action
