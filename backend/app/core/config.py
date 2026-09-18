"""Application configuration.

All configuration is read from environment variables (optionally via a
local .env file during development). Nothing secret ever gets a default
value here -- if a required secret is missing, startup fails loudly
instead of falling back to something insecure.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General -----------------------------------------------------
    app_env: Literal["development", "production", "test"] = "development"
    # Not read anywhere else in the app -- only used for the local-dev
    # `uvicorn ... --host $APP_HOST --port $APP_PORT` invocation in the
    # README. deploy/shaverma-adminka.service hardcodes its own host/port
    # directly in ExecStart= rather than sourcing these via systemd
    # variable substitution -- see the comment there for why.
    app_host: str = "127.0.0.1"
    app_port: int = 8100

    # --- Database ------------------------------------------------------
    # The admin panel connects directly to the existing shaverma system_db.
    # It only owns the admin_* tables described in the models package --
    # it never touches or imports the shaverma project's own models.
    system_database_url: str

    # --- Secrets ---------------------------------------------------------
    admin_session_secret: str
    admin_otp_secret: str

    # --- Telegram (dedicated admin bot, separate from the shaverma bot) --
    admin_telegram_bot_token: str
    telegram_api_base_url: str = "https://api.telegram.org"
    # Optional proxy for the admin bot's own calls to the Telegram API --
    # api.telegram.org is blocked/throttled from some hosting locations,
    # so a direct connection isn't always possible. Any scheme httpx
    # understands: http://, https://, or socks5://user:pass@host:port
    # (the socks5 scheme needs the `socksio` package, already a
    # dependency here for exactly this). Unset -> no proxy, same direct
    # connection as before.
    telegram_proxy_url: str | None = None

    # --- Sessions / OTP tuning --------------------------------------------
    admin_session_ttl_seconds: int = 28800
    admin_otp_ttl_seconds: int = 300
    admin_otp_max_attempts: int = 5
    admin_otp_code_length: int = 6

    # --- System command execution --------------------------------------
    system_command_timeout_seconds: int = 30
    system_command_output_limit_bytes: int = 1_048_576
    # A seed_db script does real (possibly bulk) DB writes, not a plain
    # filesystem operation like every other privileged action -- gets its
    # own, more generous timeout rather than sharing
    # system_command_timeout_seconds (30s is comfortable for e.g. a
    # single `systemctl start`, not for seeding a database).
    seed_run_timeout_seconds: int = 300

    # Absolute paths only -- CommandExecutor never resolves an executable
    # through $PATH. Override if a target host's binaries live elsewhere.
    systemctl_path: str = "/usr/bin/systemctl"
    sudo_path: str = "/usr/bin/sudo"

    # The privileged helper used to read/write a shaverma instance's
    # root-owned .env file (see backend/scripts/env_file_helper.py and
    # the README's sudoers section). Must match wherever that script is
    # actually deployed.
    env_helper_path: str = "/opt/shaverma_adminka/backend/scripts/env_file_helper.py"

    # Used to show the resolved .env path in the UI/API, to check
    # provisioning status against the live filesystem, and -- since the
    # new-service wizard was added -- to build the `root`/WorkingDirectory
    # paths baked into the nginx block and systemd unit it generates. The
    # privileged helpers still never trust this value themselves (each
    # has its own hardcoded PROJECT_ROOT, so a mismatch can't become a
    # path-traversal or access-control issue there), but it now MUST
    # match that PROJECT_ROOT exactly, or newly provisioned services will
    # get a working instance directory pointing at the wrong path in
    # their own nginx/systemd config.
    instances_root_dir: str | None = None

    # --- New-service provisioning ---------------------------------------
    # Every deployed shaverma backend instance shares one OS user and one
    # Python virtualenv (see deploy/*.service and README) -- not created
    # per service, always this fixed pair.
    service_work_user: str = "user1"
    service_venv_dir: str = "/home/user1/common_venv"

    # Node.js (for `npm install && npm run build` on a freshly uploaded
    # frontend). CommandExecutor never resolves through $PATH or sources
    # nvm's shell functions, so this must be the concrete versioned bin
    # directory nvm would otherwise have put on PATH via "nvm use".
    node_bin_dir: str = "/home/shaverma-admin/.nvm/versions/node/22.23.0/bin"

    # Local path, on this host, to the Telegram Web App SDK script
    # (telegram-web-app.js) -- one file, shared across every service that
    # opts into using it (see TELEGRAM_WEB_APP_LOCAL_SDK_ENABLED in each
    # service's own .env, app.provisioning.env_template). Plain local
    # file, readable by adminka's own OS user -- no elevated privilege
    # involved. Optional: unset means no frontend build ever touches
    # public/telegram-web-app.js at all, whatever any service's own
    # opt-in flag says.
    telegram_web_app_js_path: str | None = None

    # Where uploaded/extracted/built service files are staged before a
    # privileged helper moves the finished artifacts into place. Owned by
    # and fully writable by the OS user running adminka itself -- npm
    # install/build always runs here, never inside the root-owned
    # instance tree. Cleared after each successful/failed frontend build.
    instance_staging_dir: str = "/var/lib/shaverma_adminka/staging"

    # The privileged helpers used to provision a brand-new instance
    # directory/nginx entry/systemd unit -- see backend/scripts/ and the
    # README's sudoers section. Must match wherever they're deployed.
    instance_files_helper_path: str = "/opt/shaverma_adminka/backend/scripts/instance_files_helper.py"
    nginx_config_helper_path: str = "/opt/shaverma_adminka/backend/scripts/nginx_config_helper.py"
    systemd_unit_helper_path: str = "/opt/shaverma_adminka/backend/scripts/systemd_unit_helper.py"
    # Lists/edits an instance's backend/app/seed/ script pairs and runs
    # one of them (see backend/scripts/seed_helper.py and the README's
    # sudoers section). Must match wherever that script is deployed.
    seed_helper_path: str = "/opt/shaverma_adminka/backend/scripts/seed_helper.py"
    nginx_binary_path: str = "/usr/sbin/nginx"
    # Only used to list currently-listening local ports (no `-p`/process
    # detail needed) -- doesn't require any elevated privilege.
    ss_path: str = "/usr/sbin/ss"

    # Display-only, same caveat as instances_root_dir above -- the actual
    # nginx config path is a constant inside nginx_config_helper.py.
    nginx_config_path: str | None = None

    # Local TCP ports for new backend units are allocated starting here.
    service_port_range_start: int = 8000

    # A wildcard TLS certificate is assumed to already cover every
    # {label}.<service_domain_zone> subdomain -- no per-service cert
    # issuance happens as part of provisioning.
    service_domain_zone: str = "example-service.рф"
    nginx_ssl_certificate: str = "/etc/letsencrypt/live/example-service.ru/fullchain.pem"
    nginx_ssl_certificate_key: str = "/etc/letsencrypt/live/example-service.ru/privkey.pem"

    # The "bot" project (a separate codebase -- not shaverma, not this
    # repo) that owns provisioning gateway credentials for each new
    # service. Runs in the SAME shared venv as the services themselves
    # (service_venv_dir). No sudo needed to invoke it -- confirmed to
    # already be readable/executable by adminka's own OS user.
    bot_project_dir: str

    # Fixed, shared constants copied verbatim into every new service's
    # .env (see app/provisioning/env_template.py) -- NOT per-service, and
    # NOT the same bot as ADMIN_TELEGRAM_BOT_TOKEN above (that one is
    # adminka's own admin-notification bot; these are the actual
    # customer-facing bot's credentials).
    service_telegram_bot_token: str
    service_max_bot_token: str
    service_max_entry_secret: str
    system_gateway_base_url: str = "http://127.0.0.1:8081"

    # Deep-link identifiers used to build VITE_TELEGRAM_APP_RETURN_URL /
    # VITE_MAX_APP_RETURN_URL (".../{this}?start={system_name}-all") --
    # assumed fixed/shared across every instance, same as the tokens
    # above. Adjust per-service afterwards via the .env editor if wrong.
    service_telegram_bot_username: str = "example_service_bot"
    service_max_bot_deep_link_id: str = "id000000000000_1_bot"

    # --- CORS / cookies -----------------------------------------------
    frontend_origin: str = "http://localhost:3000"
    session_cookie_name: str = "admin_session"
    csrf_cookie_name: str = "admin_csrf"
    # Unset (default) -> both cookies are host-only, scoped to whichever
    # origin issued them. Set this when the frontend and backend are
    # deployed on *different* subdomains of the same parent domain (e.g.
    # frontend on admin.example.com, backend on api-admin.example.com --
    # both count as "same-site" for SameSite=Strict, since that's based
    # on the registrable domain, but a host-only cookie set by the API
    # origin is still invisible to JS running on the frontend's own
    # origin -- the CSRF cookie specifically must be readable there for
    # the double-submit pattern to work at all). Needs the leading dot,
    # e.g. ".example.com", to cover every subdomain.
    cookie_domain: str | None = None

    @field_validator(
        "admin_session_secret",
        "admin_otp_secret",
        "admin_telegram_bot_token",
        "bot_project_dir",
        "service_telegram_bot_token",
        "service_max_bot_token",
        "service_max_entry_secret",
    )
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("secret/required values must not be blank")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor.

    Using a function (rather than a module-level singleton) makes it easy
    to override settings in tests via dependency overrides / env vars.
    """

    return Settings()
