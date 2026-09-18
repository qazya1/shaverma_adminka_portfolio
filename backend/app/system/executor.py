"""Safe, low-level process executor.

This is the *only* place in the codebase allowed to spawn a subprocess.
It deliberately does not accept a shell string: `asyncio.create_subprocess_exec`
is used exclusively, with the executable and each argument passed as
separate items, so there is no shell involved and therefore no shell
injection surface.

Nothing in this module decides *what* command to run -- that is left
entirely to the ActionRegistry (see app/system/registry.py) and the
concrete, individually-reviewed actions registered there. This module
only answers "how do I run a fully-specified command safely", not "what
should be run".
"""

import asyncio
import time

from app.system.exceptions import SystemExecutionError
from app.system.models import CommandResult, CommandSpec


async def _write_stdin(stream: asyncio.StreamWriter | None, data: bytes) -> None:
    """Write `data` to the child's stdin, then close it. Runs concurrently
    with the stdout/stderr drain tasks so a child that reads and writes
    interleaved (rather than reading everything before producing output)
    can never deadlock us."""

    if stream is None:
        return
    try:
        stream.write(data)
        await stream.drain()
    except (BrokenPipeError, ConnectionResetError):
        # The child exited or closed stdin before consuming all of it
        # (e.g. it errored out early on bad input) -- not our problem to
        # raise over; its exit code/stderr already tell that story.
        pass
    finally:
        stream.close()


async def _drain_stream(stream: asyncio.StreamReader | None, limit: int) -> tuple[bytes, bool]:
    """Read a stream to EOF, keeping at most `limit` bytes.

    Bytes beyond the limit are discarded (not buffered) so a chatty
    command can't be used to exhaust memory, but the stream is still
    fully drained so the subprocess never blocks on a full pipe.
    """

    if stream is None:
        return b"", False

    chunks: list[bytes] = []
    total = 0
    truncated = False

    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        if total < limit:
            remaining = limit - total
            if len(chunk) > remaining:
                chunks.append(chunk[:remaining])
                truncated = True
            else:
                chunks.append(chunk)
            total += len(chunk)
        else:
            truncated = True

    return b"".join(chunks), truncated


class CommandExecutor:
    """Runs a `CommandSpec` and returns a structured `CommandResult`.

    Never raises on "expected" outcomes (timeout, truncated output,
    non-zero exit code) -- those are all represented in the returned
    `CommandResult` so callers can make policy decisions (e.g. what
    counts as failure) themselves. It only raises `SystemExecutionError`
    for genuinely exceptional conditions, such as the executable not
    existing.
    """

    async def run(self, spec: CommandSpec) -> CommandResult:
        start = time.monotonic()

        try:
            process = await asyncio.create_subprocess_exec(
                spec.executable,
                *spec.args,
                cwd=spec.cwd,
                env=dict(spec.env) if spec.env is not None else {},
                stdin=asyncio.subprocess.PIPE if spec.stdin is not None else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, PermissionError) as exc:
            raise SystemExecutionError(f"failed to start command: {spec.executable}") from exc

        stdout_task = asyncio.ensure_future(_drain_stream(process.stdout, spec.max_output_bytes))
        stderr_task = asyncio.ensure_future(_drain_stream(process.stderr, spec.max_output_bytes))
        stdin_task = (
            asyncio.ensure_future(_write_stdin(process.stdin, spec.stdin)) if spec.stdin is not None else None
        )

        timed_out = False
        try:
            await asyncio.wait_for(process.wait(), timeout=spec.timeout_seconds)
        except TimeoutError:
            timed_out = True
            await self._kill(process)

        stdout_bytes, stdout_truncated = await stdout_task
        stderr_bytes, stderr_truncated = await stderr_task
        if stdin_task is not None:
            await stdin_task

        duration_ms = int((time.monotonic() - start) * 1000)

        return CommandResult(
            exit_code=process.returncode,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            duration_ms=duration_ms,
            timed_out=timed_out,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )

    @staticmethod
    async def _kill(process: asyncio.subprocess.Process) -> None:
        try:
            process.kill()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except TimeoutError:
            # Nothing more we can do -- the OS will reap an unkillable
            # process on its own eventually. This should not happen in
            # practice for SIGKILL.
            pass
