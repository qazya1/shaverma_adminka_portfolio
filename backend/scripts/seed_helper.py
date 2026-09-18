#!/usr/bin/env python3
"""Privileged helper for listing/editing a shaverma instance's DB-seed
script pairs, and for running one of them against the instance's own
database.

Deployment/invocation model is identical to env_file_helper.py and
instance_files_helper.py in this same directory -- read either file's
docstring for the full rationale. Same rules apply here:

  - owned by root, mode 700;
  - invoked ONLY via a narrowly scoped sudoers NOPASSWD rule (see
    README.md, "Deployment: system user and sudoers");
  - never accepts a filesystem path -- only `system_name` and
    `pair_key`, both validated against strict identifier patterns, with
    PROJECT_ROOT (the instance tree), WORK_USER, and VENV_DIR hardcoded
    as constants in this file, not supplied by the caller.

Background: each deployed instance's `backend/app/seed/` folder holds
zero or more *pairs* of scripts an operator runs by hand today (`cd
backend && python -m app.seed.seed_db...`, in the shared venv) to
populate a fresh database -- `seed_data<suffix>.py` (the data, imported
by the other file) and `seed_db<suffix>.py` (the script that actually
does the DB writes), sharing the same `<suffix>` (empty for the base
`seed_data.py`/`seed_db.py` pair, or `_mrgiros`, `_venue2`, ...). This
script only ever touches the *data* half directly (list which pairs
exist, read/replace one data file's content) and, for running, only
ever launches the matching *db* half -- it never lets a caller name an
arbitrary module or path to import/execute.

Usage:
    seed_helper.py list       <system_name>
    seed_helper.py read_data  <system_name> <pair_key>
    seed_helper.py write_data <system_name> <pair_key>   # new content <- stdin
    seed_helper.py run_db     <system_name> <pair_key>

`pair_key` is the part of the filename between `seed_data`/`seed_db` and
`.py` (with its leading `_` stripped) -- `""` for the base pair, or
e.g. `"mrgiros"` for `seed_data_mrgiros.py`/`seed_db_mrgiros.py`.

`list` prints one `PAIR=<pair_key>` line per pair for which *both*
halves exist on disk -- an orphan `seed_data_x.py` with no matching
`seed_db_x.py` (or vice versa) is silently skipped, never surfaced as a
selectable pair.

`write_data` deliberately never creates a new file: `pair_key` must name
a data file that already exists (i.e., one `list` would have reported)
-- unlike env_file_helper.py's `write`, there is no legitimate "brand
new seed pair" case here, the pairs come from whatever backend code was
uploaded, not from anything this app generates.

`run_db` drops privileges to WORK_USER (setgid/setuid, after
initializing its supplementary group list) before exec'ing the seed_db
script -- this process (invoked via sudo) starts out as root, but there
is no reason for admin-edited application-level Python to ever run with
more privilege than the deployed service itself already has (its own
systemd unit also runs as WORK_USER). `os.execve` replaces this process
entirely, so the seed script's stdout/stderr/exit code become this
command's own -- nothing here parses or wraps them.

Exit codes:
    0  success
    2  invalid system_name or pair_key
    3  target not found (seed dir / data file / db script missing)
    4  usage error
"""

import os
import pwd
import re
import sys
import tempfile

# Same identifier rules as env_file_helper.py / instance_files_helper.py
# -- kept as an independent literal here for the same reason: this
# script's own safety should be reviewable in complete isolation.
SYSTEM_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,29}$")

# The part of a seed filename between "seed_data"/"seed_db" and ".py".
# Empty string is the base seed_data.py/seed_db.py pair. Deliberately
# narrower than SYSTEM_NAME_RE (no dots/dashes) -- these are Python
# module name suffixes (`app.seed.seed_db_<pair_key>`), and dotted or
# dashed text isn't a valid module name component anyway.
PAIR_KEY_RE = re.compile(r"^[A-Za-z0-9_]{0,50}$")

_DATA_FILENAME_RE = re.compile(r"^seed_data(?:_([A-Za-z0-9_]{1,50}))?\.py$")

# Keep in sync with the adminka backend's own settings -- see the
# README's sudoers section sync table. Display-only on the app side;
# these constants are what actually decide which files get touched and
# what runs.
PROJECT_ROOT = "/opt/shaverma-instances"
WORK_USER = "user1"
VENV_DIR = "/home/user1/common_venv"


def _fail(message: str, code: int) -> None:
    sys.stderr.write(message + "\n")
    sys.exit(code)


def _validate_system_name(system_name: str) -> str:
    if not SYSTEM_NAME_RE.fullmatch(system_name):
        _fail(f"invalid system_name: {system_name!r}", 2)
    return system_name


def _validate_pair_key(pair_key: str) -> str:
    if not PAIR_KEY_RE.fullmatch(pair_key):
        _fail(f"invalid pair_key: {pair_key!r}", 2)
    return pair_key


def _data_filename(pair_key: str) -> str:
    return f"seed_data_{pair_key}.py" if pair_key else "seed_data.py"


def _db_filename(pair_key: str) -> str:
    return f"seed_db_{pair_key}.py" if pair_key else "seed_db.py"


def _db_module(pair_key: str) -> str:
    return f"seed_db_{pair_key}" if pair_key else "seed_db"


def _seed_dir(system_name: str) -> str:
    return os.path.join(PROJECT_ROOT, system_name, "backend", "app", "seed")


def cmd_list(system_name: str) -> None:
    seed_dir = _seed_dir(system_name)
    if not os.path.isdir(seed_dir):
        _fail(f"seed directory not found: {seed_dir}", 3)

    pair_keys: list[str] = []
    for name in os.listdir(seed_dir):
        match = _DATA_FILENAME_RE.fullmatch(name)
        if not match:
            continue
        pair_key = match.group(1) or ""
        if os.path.isfile(os.path.join(seed_dir, _db_filename(pair_key))):
            pair_keys.append(pair_key)

    for pair_key in sorted(pair_keys):
        sys.stdout.write(f"PAIR={pair_key}\n")


def cmd_read_data(system_name: str, pair_key: str) -> None:
    path = os.path.join(_seed_dir(system_name), _data_filename(pair_key))
    if not os.path.isfile(path):
        _fail(f"seed data file not found: {path}", 3)
    with open(path, encoding="utf-8") as f:
        sys.stdout.write(f.read())


def cmd_write_data(system_name: str, pair_key: str) -> None:
    path = os.path.join(_seed_dir(system_name), _data_filename(pair_key))
    if not os.path.isfile(path):
        # Deliberately never creates a new file -- see the module
        # docstring. `list` (or the file having been part of the
        # uploaded backend) is what makes a pair_key legitimate here.
        _fail(f"seed data file not found -- run list first: {path}", 3)

    new_content = sys.stdin.read()

    # Preserve the existing file's ownership/mode across the rewrite --
    # same atomic-replace idiom as env_file_helper.py's cmd_write. Always
    # takes the "existing file" branch (write_data never creates one),
    # so there is no "brand new file" default to pick here at all.
    st = os.stat(path)
    uid, gid, mode = st.st_uid, st.st_gid, st.st_mode & 0o777

    seed_dir = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=seed_dir, prefix=".seed_data.", suffix=".tmp")
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


def cmd_run_db(system_name: str, pair_key: str) -> None:
    backend_dir = os.path.join(PROJECT_ROOT, system_name, "backend")
    db_script = os.path.join(_seed_dir(system_name), _db_filename(pair_key))
    if not os.path.isfile(db_script):
        _fail(f"seed db script not found: {db_script}", 3)

    python_path = os.path.join(VENV_DIR.rstrip("/"), "bin", "python")

    # Drop root before running any admin-edited application code -- the
    # deployed service itself runs as WORK_USER too (see its own systemd
    # unit's User=), so this matches, rather than exceeds, the privilege
    # that code already runs with elsewhere. Order matters: initgroups
    # and setgid must happen before setuid, since dropping the uid first
    # would remove permission to change the gid/group list afterwards.
    pw = pwd.getpwnam(WORK_USER)
    os.initgroups(WORK_USER, pw.pw_gid)
    os.setgid(pw.pw_gid)
    os.setuid(pw.pw_uid)
    os.chdir(backend_dir)

    # Replaces this process entirely -- the seed script's own
    # stdout/stderr/exit code become this command's, nothing here
    # captures or wraps them.
    argv = [python_path, "-m", f"app.seed.{_db_module(pair_key)}"]
    env = {"PATH": "/usr/bin:/bin", "HOME": pw.pw_dir}
    os.execve(python_path, argv, env)


def main(argv: list[str]) -> None:
    if len(argv) == 3 and argv[1] == "list":
        system_name = _validate_system_name(argv[2])
        cmd_list(system_name)
        return

    if len(argv) == 4 and argv[1] in ("read_data", "write_data", "run_db"):
        system_name = _validate_system_name(argv[2])
        pair_key = _validate_pair_key(argv[3])
        if argv[1] == "read_data":
            cmd_read_data(system_name, pair_key)
        elif argv[1] == "write_data":
            cmd_write_data(system_name, pair_key)
        else:
            cmd_run_db(system_name, pair_key)
        return

    _fail(__doc__ or "usage error", 4)


if __name__ == "__main__":
    main(sys.argv)
