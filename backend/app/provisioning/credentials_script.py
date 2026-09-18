"""Runs the "bot" project's own credential-provisioning script for a
newly created service, and captures the two gateway secrets it prints.

This calls into a *separate* codebase (not shaverma, not this repo) that
owns `SYSTEM_GATEWAY_API_KEY`/`SYSTEM_GATEWAY_SIGNING_SECRET` and writes
them into `services.signing_secret_enc`/etc via its own DB session --
adminka never touches those columns itself. The script text below is a
fixed, reviewed constant (translated from the shell heredoc this was
based on into a directly-executable form, since CommandExecutor never
uses a shell and therefore can't `source venv/bin/activate` -- invoking
the venv's own `python` binary directly has the same effect for a single
subprocess). The only variable input is `service_id`, passed via the
environment, never interpolated into the script text itself.
"""

import os
import re

from app.system.executor import CommandExecutor
from app.system.exceptions import SystemExecutionError
from app.system.models import CommandSpec

# Kept byte-for-byte equivalent to the original:
#   PYTHONPATH=<parent of the bot project> SERVICE_ID=<id> python - <<'PY'
#   ...
#   PY
#
# `import bot....` needs the bot project's *parent* directory on
# sys.path (so `bot` resolves as a package), but `cwd` for the
# subprocess must stay *inside* the bot project directory itself --
# the bot project's own settings loader resolves its `.env` relative to
# cwd (same env_file="." pattern this app's own Settings uses), so
# moving cwd up a level to satisfy the import would break that lookup
# instead. Passing PYTHONPATH explicitly (rather than relying on `python
# -c` putting cwd on sys.path, which only works if cwd is *already* the
# import root) is what reconciles the two.
_SCRIPT = """\
import os

from bot.database import SessionLocal
from bot.repositories.services import get_service_by_id
from bot.services.service_provisioning import provision_service_credentials

service_id = int(os.environ["SERVICE_ID"])

with SessionLocal() as db:
    service = get_service_by_id(db, service_id)
    if service is None:
        raise SystemExit(f"Service {service_id} not found")

    creds = provision_service_credentials(db, service)
    db.commit()

    print("SYSTEM_GATEWAY_API_KEY=" + creds.gateway_api_key)
    print("SYSTEM_GATEWAY_SIGNING_SECRET=" + creds.signing_secret)
"""

_API_KEY_RE = re.compile(r"^SYSTEM_GATEWAY_API_KEY=(.*)$", re.MULTILINE)
_SIGNING_SECRET_RE = re.compile(r"^SYSTEM_GATEWAY_SIGNING_SECRET=(.*)$", re.MULTILINE)


class CredentialProvisioningError(SystemExecutionError):
    """Raised when the bot's provisioning script fails or doesn't print
    the two expected lines. Never includes stdout in the message --
    a successful-looking-but-malformed run could still have printed a
    secret on some other line."""


async def provision_gateway_credentials(
    executor: CommandExecutor,
    venv_dir: str,
    bot_project_dir: str,
    service_id: int,
    timeout_seconds: float,
) -> tuple[str, str]:
    """Returns (gateway_api_key, signing_secret). Never logs stdout --
    callers must not either."""

    bot_project_dir = bot_project_dir.rstrip("/")
    # BOT_PROJECT_DIR is the bot project's own directory (the one whose
    # immediate children are its database.py/config.py/etc, and its own
    # .env) -- not its parent. That parent is what needs to be on
    # sys.path for `import bot....` to resolve; cwd stays put so the
    # bot project's own .env-relative-to-cwd lookup keeps working.
    parent_dir = os.path.dirname(bot_project_dir)

    spec = CommandSpec(
        executable=f"{venv_dir.rstrip('/')}/bin/python",
        args=("-c", _SCRIPT),
        cwd=bot_project_dir,
        env={"SERVICE_ID": str(service_id), "PATH": "/usr/bin:/bin", "PYTHONPATH": parent_dir},
        timeout_seconds=timeout_seconds,
    )
    result = await executor.run(spec)

    if result.exit_code != 0:
        raise CredentialProvisioningError(
            f"credential provisioning script failed (exit {result.exit_code}): {result.stderr.strip()}"
        )

    api_key_match = _API_KEY_RE.search(result.stdout)
    signing_secret_match = _SIGNING_SECRET_RE.search(result.stdout)
    if not api_key_match or not signing_secret_match:
        raise CredentialProvisioningError(
            "credential provisioning script did not print the expected SYSTEM_GATEWAY_* lines"
        )

    return api_key_match.group(1), signing_secret_match.group(1)
