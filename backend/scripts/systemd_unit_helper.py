#!/usr/bin/env python3
"""Privileged helper for writing a shaverma instance's systemd unit
file and reloading the systemd daemon.

Same deployment/invocation model as env_file_helper.py in this same
directory (root-owned, mode 700, invoked only via a narrow sudoers
NOPASSWD rule). Only accepts `system_name`, validated the same way as
every other helper in this project; the actual unit file path is always
{UNIT_DIR}/{system_name}-backend.service -- a constant directory plus a
name built entirely from the validated system_name, never a path the
caller supplies. Rendering the unit file's *content* (which template,
which port, ...) happens one layer up in
app.provisioning.systemd_template -- this script only ever writes bytes
it's given and reloads the daemon so systemd notices.

Usage:
    systemd_unit_helper.py write <system_name>   (unit file content on stdin)

Exit codes:
    0  success
    2  invalid system_name
    4  usage error
    5  `systemctl daemon-reload` itself failed
"""

import os
import re
import subprocess
import sys
import tempfile

# Dots allowed (real system_names include bare domains, e.g.
# "shashl.ru"); what's actually unsafe for a single path/unit-name
# component like this is "/" and the exact values "."/".." -- requiring
# the first character to be alphanumeric rules both out. Must match the
# same rules the adminka backend enforces before it ever calls this
# script (see app.system.service_control) -- kept as an independent
# literal here so this script's own safety can be reviewed in isolation.
SYSTEM_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,29}$")

# Fixed -- not an adminka backend setting (there is no SYSTEMD_UNIT_DIR
# in .env); edit this constant directly if it ever needs to differ.
UNIT_DIR = "/etc/systemd/system"
SYSTEMCTL_PATH = "/usr/bin/systemctl"


def _fail(message: str, code: int) -> None:
    sys.stderr.write(message + "\n")
    sys.exit(code)


def _validate_system_name(system_name: str) -> str:
    if not SYSTEM_NAME_RE.fullmatch(system_name):
        _fail(f"invalid system_name: {system_name!r}", 2)
    return system_name


def cmd_write(system_name: str) -> None:
    unit_path = os.path.join(UNIT_DIR, f"{system_name}-backend.service")
    new_content = sys.stdin.read()

    fd, tmp_path = tempfile.mkstemp(dir=UNIT_DIR, prefix=f".{system_name}-backend.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_content)
        os.chown(tmp_path, 0, 0)
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, unit_path)  # atomic rename, same filesystem
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    # Already running as root at this point (invoked via sudo) -- no
    # need to go back through sudo again for this.
    result = subprocess.run([SYSTEMCTL_PATH, "daemon-reload"], capture_output=True, text=True)
    if result.returncode != 0:
        _fail(f"systemctl daemon-reload failed: {result.stderr.strip()}", 5)


def main(argv: list[str]) -> None:
    if len(argv) != 3 or argv[1] != "write":
        _fail(__doc__ or "usage error", 4)

    system_name = _validate_system_name(argv[2])
    cmd_write(system_name)


if __name__ == "__main__":
    main(sys.argv)
