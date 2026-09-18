"""Picks the first free local TCP port (starting from
`Settings.service_port_range_start`, usually 8000) for a new backend
unit to listen on.

The single source of truth for "which ports are already spoken for" is
`services.server_local_port` (read by the caller and passed in here as
`used_ports`) -- not the shared nginx config. Parsing nginx's
`proxy_pass` lines used to be how this worked, but that made the nginx
config the source of truth for something it merely reflects, and made a
retry of the nginx step pick a *different* port every time (its own
previous block was itself counted as "in use"). `server_local_port` does
not have that problem: the caller reuses it directly once it is set,
without calling this module again at all.

`ports_currently_listening` (`ss -ltn`) stays as a live safety net on
top of that -- it catches a port already bound by something the
`services` table doesn't know about at all. Reading listening ports
needs no privilege -- only the per-process ownership detail (`-p`) is
restricted to root for other users' sockets, and this doesn't need that,
just the port numbers.
"""

import re

from app.system.exceptions import SystemExecutionError
from app.system.executor import CommandExecutor
from app.system.models import CommandSpec

_LISTEN_PORT_RE = re.compile(r":(\d+)\s*$")


async def ports_currently_listening(executor: CommandExecutor, ss_path: str, timeout_seconds: float) -> set[int]:
    spec = CommandSpec(executable=ss_path, args=("-Hltn",), timeout_seconds=timeout_seconds)
    result = await executor.run(spec)
    if result.exit_code != 0:
        raise SystemExecutionError(f"{ss_path} -Hltn failed (exit {result.exit_code}): {result.stderr.strip()}")

    ports: set[int] = set()
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) < 4:
            continue
        local_address = columns[3]  # e.g. "127.0.0.1:8000" or "*:8000" or "[::]:8000"
        match = _LISTEN_PORT_RE.search(local_address)
        if match:
            ports.add(int(match.group(1)))
    return ports


async def allocate_port(
    executor: CommandExecutor,
    ss_path: str,
    timeout_seconds: float,
    used_ports: set[int],
    start: int,
    max_port: int = 65535,
) -> int:
    used = used_ports | await ports_currently_listening(executor, ss_path, timeout_seconds)

    for port in range(start, max_port + 1):
        if port not in used:
            return port

    raise SystemExecutionError(f"no free port found in range {start}-{max_port}")
