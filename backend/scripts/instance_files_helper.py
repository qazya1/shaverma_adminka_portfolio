#!/usr/bin/env python3
"""Privileged helper for provisioning a shaverma instance's directory
tree and moving staged, already-built artifacts into it.

Deployment/invocation model is identical to env_file_helper.py in this
same directory -- read that file's docstring for the full rationale.
Same rules apply here:

  - owned by root, mode 700;
  - invoked ONLY via a narrowly scoped sudoers NOPASSWD rule (see
    README.md, "Deployment: system user and sudoers");
  - never accepts a path -- only `system_name`, validated against a
    strict identifier pattern, with both PROJECT_ROOT (the instance
    tree) and STAGING_ROOT (adminka's own unprivileged scratch space)
    hardcoded as constants in this file, not supplied by the caller.

Usage:
    instance_files_helper.py create_tree     <system_name>
    instance_files_helper.py install_backend <system_name>
    instance_files_helper.py install_dist    <system_name>

`create_tree` makes {PROJECT_ROOT}/{system_name}/, and backend/ + dist/
inside it (owned by WORK_USER), idempotently -- safe to call again on an
already-provisioned instance, it just fixes ownership/mode rather than
failing.

`install_backend`/`install_dist` each replace the corresponding
directory's *contents* with whatever adminka has already staged at
{STAGING_ROOT}/{system_name}/backend or /dist -- adminka stages there as
its own unprivileged OS user (extracting an uploaded zip, running `npm
install`/`npm run build`), this helper only ever does the final,
privileged move into place. The staging directory itself is left for
adminka to clean up afterwards; this script does not touch it beyond
reading.

Exit codes:
    0  success
    2  invalid system_name
    3  staged source not found (install_backend/install_dist only)
    4  usage error
"""

import os
import pwd
import re
import shutil
import sys

# Must match the SAME identifier rules the adminka backend enforces
# before it ever calls this script (see
# app.provisioning.service_creation / app.system.service_control) --
# kept as an independent literal here, same reasoning as
# env_file_helper.py. Dots are allowed (real system_names include bare
# domains, e.g. "shashl.ru"); what's actually unsafe for a single path
# component like this is "/" and the exact values "."/".." -- requiring
# the first character to be alphanumeric rules both out.
SYSTEM_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,29}$")

# Keep both in sync with the adminka backend's own settings
# (INSTANCES_ROOT_DIR / INSTANCE_STAGING_DIR) -- those are display-only
# on the app side; these constants are what actually decide which
# directories get touched.
PROJECT_ROOT = "/opt/shaverma-instances"
STAGING_ROOT = "/var/lib/shaverma_adminka/staging"

# The shared OS user every deployed backend instance runs as.
WORK_USER = "user1"


def _fail(message: str, code: int) -> None:
    sys.stderr.write(message + "\n")
    sys.exit(code)


def _validate_system_name(system_name: str) -> str:
    if not SYSTEM_NAME_RE.fullmatch(system_name):
        _fail(f"invalid system_name: {system_name!r}", 2)
    return system_name


def _work_user_ids() -> tuple[int, int]:
    pw = pwd.getpwnam(WORK_USER)
    return pw.pw_uid, pw.pw_gid


def cmd_create_tree(system_name: str) -> None:
    instance_dir = os.path.join(PROJECT_ROOT, system_name)
    backend_dir = os.path.join(instance_dir, "backend")
    dist_dir = os.path.join(instance_dir, "dist")
    uid, gid = _work_user_ids()

    os.makedirs(instance_dir, exist_ok=True)
    os.chown(instance_dir, 0, 0)
    os.chmod(instance_dir, 0o755)

    for path in (backend_dir, dist_dir):
        os.makedirs(path, exist_ok=True)
        os.chown(path, uid, gid)
        os.chmod(path, 0o755)


def _install_from_staging(system_name: str, subdir: str) -> None:
    source = os.path.join(STAGING_ROOT, system_name, subdir)
    dest = os.path.join(PROJECT_ROOT, system_name, subdir)

    if not os.path.isdir(source):
        _fail(f"staged source not found: {source}", 3)
    if not os.path.isdir(os.path.dirname(dest)):
        _fail(f"instance directory not found -- run create_tree first: {dest}", 3)

    uid, gid = _work_user_ids()

    # Full replace, not an incremental merge -- a retry should produce a
    # clean, reproducible result rather than layering old and new files.
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(source, dest)

    os.chown(dest, uid, gid)
    for root, dirs, files in os.walk(dest):
        for name in dirs:
            os.chown(os.path.join(root, name), uid, gid)
        for name in files:
            os.chown(os.path.join(root, name), uid, gid)


def cmd_install_backend(system_name: str) -> None:
    _install_from_staging(system_name, "backend")


def cmd_install_dist(system_name: str) -> None:
    _install_from_staging(system_name, "dist")


_COMMANDS = {
    "create_tree": cmd_create_tree,
    "install_backend": cmd_install_backend,
    "install_dist": cmd_install_dist,
}


def main(argv: list[str]) -> None:
    if len(argv) != 3 or argv[1] not in _COMMANDS:
        _fail(__doc__ or "usage error", 4)

    command, system_name = argv[1], argv[2]
    system_name = _validate_system_name(system_name)
    _COMMANDS[command](system_name)


if __name__ == "__main__":
    main(sys.argv)
