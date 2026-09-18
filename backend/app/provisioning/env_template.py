"""Renders a new service's initial `.env`, reusing the same EnvLine /
render_env_file machinery the existing .env editor already uses -- so a
generated file round-trips through that editor exactly like a hand-
written one, comments included.

What's filled in automatically vs. left for the admin to complete by
hand via the .env editor afterwards (`docs`: see README, ".env editor"
and "new-service wizard" sections):

  - computed from the form (system_name, frontend/backend URLs)
  - fixed literal defaults, copied straight from the template
  - constants from adminka's own settings (bot tokens, gateway base URL)
  - freshly generated (SESSION_SECRET, the two SYSTEM_GATEWAY_* values
    from the bot's own provisioning script, and DATABASE_URL from
    app.provisioning.database_provisioning -- a MySQL database + user
    created for this service specifically, admin-named)
  - YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY: entered by hand on the
    wizard's env step, exactly as the template this is based on marks
    them ("entered by hand, optional") -- left BLANK if not given
  - TELEGRAM_WEB_APP_LOCAL_SDK_ENABLED: the wizard's env step's "Local
    Telegram Web SDK" checkbox, on by default -- whether this service's
    frontend build should copy in the Telegram Web App SDK script (see
    app.provisioning.frontend_build.stage_telegram_web_app_js; the
    actual source file location is adminka's own
    TELEGRAM_WEB_APP_JS_PATH setting, one path shared by every service
    that opts in, not per-service)
"""

from app.system.env_file_control import EnvLine, entries_from_lines, render_env_file

VITE_PREFIX = "VITE_"
TELEGRAM_WEB_APP_LOCAL_SDK_ENABLED_KEY = "TELEGRAM_WEB_APP_LOCAL_SDK_ENABLED"


def _kv(key: str, value: str) -> EnvLine:
    return EnvLine(kind="kv", key=key, value=value)


def _comment(text: str) -> EnvLine:
    return EnvLine(kind="comment", raw=text)


def _blank() -> EnvLine:
    return EnvLine(kind="blank", raw="")


def render_new_service_env(
    *,
    system_name: str,
    display_name: str,
    frontend_url: str,
    backend_url: str,
    telegram_bot_token: str,
    telegram_bot_username: str,
    max_bot_token: str,
    max_entry_secret: str,
    max_bot_deep_link_id: str,
    system_gateway_base_url: str,
    gateway_api_key: str,
    gateway_signing_secret: str,
    session_secret: str,
    database_url: str,
    yookassa_recurring_payments_enabled: bool,
    yookassa_shop_id: str = "",
    yookassa_secret_key: str = "",
    telegram_web_app_local_sdk_enabled: bool = True,
) -> list[EnvLine]:
    start_param = f"{system_name}-all"

    lines: list[EnvLine] = [
        _comment("#FRONTEND"),
        _kv("VITE_API_BASE_URL", backend_url),
        _kv("VITE_APP_NAME", display_name),
        _kv("VITE_RECEIPT_CONTACT_MODE", "email"),
        _kv("VITE_MAX_RESOLVER_BASE", "http://localhost:8080"),
        _kv("VITE_TELEGRAM_APP_RETURN_URL", f"https://t.me/{telegram_bot_username}?start={start_param}"),
        _kv("VITE_MAX_APP_RETURN_URL", f"https://max.ru/{max_bot_deep_link_id}?start={start_param}"),
        _blank(),
        _comment("# Copy the Telegram Web App SDK (telegram-web-app.js) into public/ before"),
        _comment("# every build of this frontend, creating public/ if it doesn't exist yet --"),
        _comment("# from adminka's own TELEGRAM_WEB_APP_JS_PATH (one shared source file, not"),
        _comment("# per-service). Set to false to skip this entirely for this service."),
        _kv(
            TELEGRAM_WEB_APP_LOCAL_SDK_ENABLED_KEY,
            "true" if telegram_web_app_local_sdk_enabled else "false",
        ),
        _comment("#BACKEND"),
        _kv("DATABASE_URL", database_url),
        _kv("APP_NAME", f"{system_name} Backend"),
        _kv("APP_ENV", "production"),
        # A bare [url] here isn't valid JSON (json.loads chokes on an
        # unquoted string) -- pydantic-settings parses a List[str] field
        # from a `[...]`-looking env value as JSON, so each origin needs
        # its own quotes: ["https://..."], not [https://...].
        _kv("BACKEND_CORS_ORIGINS", f'["{frontend_url}"]'),
        _kv("FRONTEND_BASE_URL", frontend_url),
        _kv("APP_BASE_URL", backend_url),
        _blank(),
        _comment("# SESSION / AUTH"),
        _kv("CLIENT_SESSION_COOKIE_NAME", "client_session"),
        _kv("STAFF_SESSION_COOKIE_NAME", "staff_session"),
        _kv("SESSION_SECRET", session_secret),
        _kv("SESSION_COOKIE_SECURE", "true"),
        _kv("SESSION_COOKIE_SAMESITE", "lax"),
        _kv("CLIENT_SESSION_TTL_MINUTES", "43200"),
        _kv("STAFF_SESSION_TTL_MINUTES", "480"),
        _kv("TELEGRAM_BOT_TOKEN", telegram_bot_token),
        _kv("TELEGRAM_INIT_DATA_MAX_AGE_SECONDS", "86400"),
        _kv("MAX_BOT_TOKEN", max_bot_token),
        _kv("MAX_ENTRY_SECRET", max_entry_secret),
        _blank(),
        _comment("#YOOKASSA {необязательно}"),
        _kv("YOOKASSA_API_BASE", "https://api.yookassa.ru/v3"),
        _kv("YOOKASSA_SHOP_ID", yookassa_shop_id),
        _kv("YOOKASSA_SECRET_KEY", yookassa_secret_key),
        _kv("YOOKASSA_TIMEOUT_SECONDS", "30"),
        _kv("YOOKASSA_RETURN_URL", f"{frontend_url}/payment-return.html"),
        _kv("YOOKASSA_VAT_CODE", "1"),
        _kv("PAYMENT_PENDING_TTL_MINUTES", "20"),
        _kv("YOOKASSA_RECURRING_PAYMENTS_ENABLED", "true" if yookassa_recurring_payments_enabled else "false"),
        _blank(),
        _comment("#SYSTEM"),
        _kv("SYSTEM_GATEWAY_API_KEY", gateway_api_key),
        _kv("SYSTEM_GATEWAY_SIGNING_SECRET", gateway_signing_secret),
        _kv("SYSTEM_GATEWAY_BASE_URL", system_gateway_base_url),
    ]

    return lines


def extract_frontend_vars(lines: list[EnvLine]) -> str:
    """The VITE_-prefixed subset, rendered as its own .env text -- what
    actually gets dropped into the frontend's build directory (Vite only
    embeds VITE_-prefixed variables into the built bundle)."""

    frontend_lines = [line for line in lines if line.kind == "kv" and (line.key or "").startswith(VITE_PREFIX)]
    return render_env_file(frontend_lines)


def extract_telegram_web_app_local_sdk_enabled(lines: list[EnvLine]) -> bool:
    """Whether this service's frontend build should copy in the Telegram
    Web App SDK -- TELEGRAM_WEB_APP_LOCAL_SDK_ENABLED in this service's
    own .env (see render_new_service_env's own "Local Telegram Web SDK"
    checkbox, which seeds it, on by default). Deliberately NOT part of
    extract_frontend_vars's VITE_-prefixed subset: a build-time-only
    switch for adminka's own frontend_build.stage_telegram_web_app_js,
    never meant to reach the frontend's own runtime .env or get embedded
    in the built bundle.

    Defaults to True (matches the checkbox's own default) when the key
    is missing entirely or its value doesn't parse as a recognized
    boolean -- covers a service whose .env predates this key, without
    silently turning the feature off for it."""

    raw = dict(entries_from_lines(lines)).get(TELEGRAM_WEB_APP_LOCAL_SDK_ENABLED_KEY)
    if raw is None or raw.strip() == "":
        return True
    return raw.strip().lower() not in ("false", "0", "no", "off")
