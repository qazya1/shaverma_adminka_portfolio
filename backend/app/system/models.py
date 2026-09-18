"""Data structures for the system command execution layer."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CommandSpec:
    """A fully-specified command to run.

    `executable` and `args` are always separate -- there is no way to
    construct a CommandSpec from a single shell string, which is what
    keeps this layer immune to shell injection by construction.
    """

    executable: str
    args: tuple[str, ...] = field(default_factory=tuple)
    timeout_seconds: float = 30.0
    cwd: str | None = None
    # An explicit, minimal environment. None means "inherit nothing extra
    # beyond what the executor itself sets up" -- callers must opt in to
    # every variable a command needs.
    env: dict[str, str] | None = None
    max_output_bytes: int = 1_048_576
    # Bytes written to the child's stdin, then the stream is closed. None
    # means "give the child no stdin at all" (DEVNULL) -- never silently
    # inherit the server process's own stdin.
    stdin: bytes | None = None


@dataclass(frozen=True)
class CommandResult:
    """The outcome of running a CommandSpec."""

    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False
