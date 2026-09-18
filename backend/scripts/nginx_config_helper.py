#!/usr/bin/env python3
"""Privileged helper for reading/writing adminka's shared nginx config
file (the one shared file all provisioned service server{} blocks live
in -- see README, "nginx" section).

Deployment/invocation model is identical to env_file_helper.py in this
same directory (root-owned, mode 700, invoked only via a narrow sudoers
NOPASSWD rule). Unlike that script, there is no per-instance parameter
at all here -- CONFIG_PATH is a single fixed constant, so this script
takes no arguments beyond the subcommand itself. All of the "is this
edit actually safe" logic (marker-based idempotent insert/replace,
`nginx -t` validation, auto-rollback on failure) lives one layer up in
app.provisioning.nginx_template / the nginx.* SystemActions -- this
script only ever does a plain atomic file read/write.

Usage:
    nginx_config_helper.py read
    nginx_config_helper.py write     (new content on stdin)

Exit codes:
    0  success
    3  config file not found (read only -- write creates it)
    4  usage error
"""

import os
import sys
import tempfile

# Keep in sync with NGINX_CONFIG_PATH in the adminka backend's settings
# (display-only there) -- this constant is what actually gets touched.
CONFIG_PATH = "/etc/nginx/sites-available/shaverma-services.conf"


def _fail(message: str, code: int) -> None:
    sys.stderr.write(message + "\n")
    sys.exit(code)


def cmd_read() -> None:
    if not os.path.isfile(CONFIG_PATH):
        _fail(f"config file not found: {CONFIG_PATH}", 3)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        sys.stdout.write(f.read())


def cmd_write() -> None:
    new_content = sys.stdin.read()
    directory = os.path.dirname(CONFIG_PATH)

    if os.path.isfile(CONFIG_PATH):
        st = os.stat(CONFIG_PATH)
        uid, gid, mode = st.st_uid, st.st_gid, st.st_mode & 0o777
    else:
        uid, gid, mode = 0, 0, 0o644

    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".shaverma-services.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_content)
        os.chown(tmp_path, uid, gid)
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, CONFIG_PATH)  # atomic rename, same filesystem
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main(argv: list[str]) -> None:
    if len(argv) != 2 or argv[1] not in ("read", "write"):
        _fail(__doc__ or "usage error", 4)

    if argv[1] == "read":
        cmd_read()
    else:
        cmd_write()


if __name__ == "__main__":
    main(sys.argv)
