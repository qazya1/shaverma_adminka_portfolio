"""Step 5 of the new-service wizard: build the uploaded frontend source
and hand the output over for the privileged move into place.

npm install/build always runs as adminka's own unprivileged OS user, in
the staging directory -- never inside the root-owned instance tree, and
never as root (see README's "npm install privilege model" note). Only
the already-built static `dist/` output is ever moved into the
privileged tree, via the instance.install_dist SystemAction -- this
module never touches that tree itself.
"""

import os
import shutil

from app.system.exceptions import SystemExecutionError
from app.system.executor import CommandExecutor
from app.system.models import CommandSpec


class FrontendBuildError(SystemExecutionError):
    pass


def stage_telegram_web_app_js(frontend_dir: str, source_path: str | None, enabled: bool) -> None:
    """Copies the Telegram Web App SDK script into this staged
    frontend's `public/` directory before the build runs, creating
    `public/` first if it doesn't exist yet -- Vite (and every other
    bundler this app has been used with so far) copies everything under
    `public/` verbatim into `dist/`, so this is what makes the SDK end
    up served at `/telegram-web-app.js` in the built output.

    `enabled` is this *service's own* opt-in/opt-out --
    `TELEGRAM_WEB_APP_LOCAL_SDK_ENABLED` in its `.env`, on by default
    (see app.provisioning.env_template's "Local Telegram Web SDK"
    checkbox and extract_telegram_web_app_local_sdk_enabled). `False`
    is always a plain no-op, checked first, before anything else here
    -- a service that opts out never has this directory touched at all,
    regardless of what adminka's own TELEGRAM_WEB_APP_JS_PATH says.

    `source_path` (adminka's own `TELEGRAM_WEB_APP_JS_PATH` setting) is
    a plain local path on this host, readable by adminka's own
    unprivileged OS user -- not privileged in any way (this whole
    function runs in adminka's own staging area, same as the rest of
    build_frontend, never inside the root-owned instance tree). Left
    unset entirely, this is *also* a no-op even for a service that opted
    in (nothing to copy from) -- only once it *is* configured does a
    missing file at that path become an error: silently shipping a
    build that was supposed to include the Telegram SDK and doesn't
    would be a much worse failure mode than failing loudly right here.
    """

    if not enabled or not source_path:
        return

    if not os.path.isfile(source_path):
        raise FrontendBuildError(f"TELEGRAM_WEB_APP_JS_PATH is set but the file doesn't exist: {source_path}")

    public_dir = os.path.join(frontend_dir, "public")
    os.makedirs(public_dir, exist_ok=True)
    shutil.copyfile(source_path, os.path.join(public_dir, "telegram-web-app.js"))


async def build_frontend(
    executor: CommandExecutor,
    node_bin_dir: str,
    frontend_dir: str,
    env_content: str,
    timeout_seconds: float,
    *,
    telegram_web_app_js_path: str | None = None,
    telegram_web_app_local_sdk_enabled: bool = True,
) -> str:
    """Writes `env_content` to {frontend_dir}/.env, stages the Telegram
    Web App SDK into {frontend_dir}/public/ if enabled and configured
    (see stage_telegram_web_app_js -- must happen before the build so
    it's present for the bundler to pick up), runs `npm install` then
    `npm run build` there (bypassing nvm's shell-function based "nvm
    use" entirely -- CommandExecutor never uses a shell, so node_bin_dir
    must already be the concrete versioned bin directory), and returns
    the path to the resulting dist/ directory."""

    stage_telegram_web_app_js(frontend_dir, telegram_web_app_js_path, telegram_web_app_local_sdk_enabled)

    env_path = os.path.join(frontend_dir, ".env")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content)

    node_bin_dir = node_bin_dir.rstrip("/")
    npm_path = f"{node_bin_dir}/npm"
    build_env = {"PATH": f"{node_bin_dir}:/usr/bin:/bin", "HOME": os.environ.get("HOME", "/tmp")}

    for args in (("install",), ("run", "build")):
        spec = CommandSpec(
            executable=npm_path,
            args=args,
            cwd=frontend_dir,
            env=build_env,
            timeout_seconds=timeout_seconds,
            max_output_bytes=2_097_152,
        )
        result = await executor.run(spec)
        if result.exit_code != 0 or result.timed_out:
            raise FrontendBuildError(
                f"npm {' '.join(args)} failed (exit {result.exit_code}, timed_out={result.timed_out}): "
                f"{result.stderr[-4000:].strip()}"
            )

    dist_dir = os.path.join(frontend_dir, "dist")
    if not os.path.isdir(dist_dir):
        raise FrontendBuildError(f"npm run build did not produce a dist/ directory at {dist_dir}")

    return dist_dir


def promote_dist(system_name: str, staging_root: str) -> str:
    """Moves {staging_root}/{system_name}/frontend/dist up to
    {staging_root}/{system_name}/dist -- the fixed location
    instance.install_dist expects its source at."""

    src = os.path.join(staging_root, system_name, "frontend", "dist")
    dest = os.path.join(staging_root, system_name, "dist")
    if not os.path.isdir(src):
        raise FrontendBuildError(f"built dist/ not found at {src}")
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.move(src, dest)
    return dest


def cleanup_staging(system_name: str, staging_root: str) -> None:
    """Removes the entire staging tree for this service -- both the
    pre-build frontend source and any node_modules/, and the backend/
    copy staged earlier. Safe to call even if nothing is there."""

    shutil.rmtree(os.path.join(staging_root, system_name), ignore_errors=True)
