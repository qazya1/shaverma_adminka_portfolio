#!/usr/bin/env python3
"""Privileged helper for reading/writing one shaverma instance's
root-owned .env file.

This script is meant to be:
  - owned by root, mode 700 (not even readable by the adminka OS user);
  - invoked ONLY via a narrowly scoped sudoers NOPASSWD rule (see
    README.md, "Deployment: system user and sudoers") from the adminka
    backend -- never called directly by anything else, and never by a
    human typing `sudo env_file_helper.py ...` by hand for one-off edits.

It deliberately does NOT accept a path. The only input from the caller
is `system_name`, which is validated against a strict identifier pattern
before it is used at all; the actual path is always
PROJECT_ROOT/<system_name>/.env, where PROJECT_ROOT is a constant in
this file, not something the caller can influence. That is what makes
the sudoers wildcard ("... env_file_helper.py read *") safe: no argument
this script accepts can ever resolve to a path outside PROJECT_ROOT.

Usage:
    env_file_helper.py read  <system_name>          # .env content -> stdout
    env_file_helper.py write <system_name>           # new content <- stdin

Exit codes:
    0  success
    2  invalid system_name
    3  target not found (read: no .env file; write: no instance directory)
    4  usage error
"""

import os
import re
import sys
import tempfile

# Must match the SAME identifier rules the adminka backend enforces
# before it ever calls this script (see
# app.system.service_control.unit_name_for and
# app.system.env_file_control) -- kept as an independent literal here
# (not imported) so this script's own safety can be reviewed in complete
# isolation from the rest of the codebase, without having to trust that
# nothing upstream changed the pattern. Dots are allowed (real
# system_names include bare domains, e.g. "shashl.ru"); what's actually
# unsafe for a single path component like this is "/" and the exact
# values "."/".." -- requiring the first character to be alphanumeric
# rules both out.
SYSTEM_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,29}$")

# The one place the deployment root is configured for this script. Keep
# in sync with INSTANCES_ROOT_DIR in the adminka backend's .env (that
# setting is display-only on the app side -- this constant is what
# actually determines which file gets touched).
PROJECT_ROOT = "/opt/shaverma-instances"


def _fail(message: str, code: int) -> None:
    sys.stderr.write(message + "\n")
    sys.exit(code)


def resolve_env_path(system_name: str) -> str:
    if not SYSTEM_NAME_RE.fullmatch(system_name):
        _fail(f"invalid system_name: {system_name!r}", 2)
    return os.path.join(PROJECT_ROOT, system_name, ".env")


def cmd_read(system_name: str) -> None:
    path = resolve_env_path(system_name)
    if not os.path.isfile(path):
        _fail(f"env file not found: {path}", 3)
    with open(path, encoding="utf-8") as f:
        sys.stdout.write(f.read())


def cmd_write(system_name: str) -> None:
    path = resolve_env_path(system_name)
    instance_dir = os.path.dirname(path)
    if not os.path.isdir(instance_dir):
        _fail(f"instance directory not found: {instance_dir}", 3)

    new_content = sys.stdin.read()

    # Preserve the existing file's ownership/mode across the rewrite; for
    # a brand new .env, default to root:root 0644 -- root-owned (adminka's
    # own unprivileged process still can't *modify* it directly, only
    # through this helper), but world-readable so whatever OS user the
    # deployed service itself runs as -- not necessarily the same one on
    # every deployment, this script has no way to know it -- can still
    # read it at startup. This matches how .env files on already-deployed
    # instances on this same server are actually set up (root:root 0644,
    # confirmed against a working instance's own `ls -la`).
    # root:root 0600 (what this used to default to) made a brand new .env
    # unreadable by the service it was generated for -- silently fine
    # until the new-service wizard started exercising this exact path,
    # which it always has.
    if os.path.isfile(path):
        st = os.stat(path)
        uid, gid, mode = st.st_uid, st.st_gid, st.st_mode & 0o777
    else:
        uid, gid, mode = 0, 0, 0o644

    fd, tmp_path = tempfile.mkstemp(dir=instance_dir, prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_content)
        os.chown(tmp_path, uid, gid)
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)  # atomic rename, same filesystem
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main(argv: list[str]) -> None:
    if len(argv) != 3 or argv[1] not in ("read", "write"):
        _fail(__doc__ or "usage error", 4)

    command, system_name = argv[1], argv[2]
    if command == "read":
        cmd_read(system_name)
    else:
        cmd_write(system_name)


if __name__ == "__main__":
    main(sys.argv)
