# shaverma_adminka

*[Читать на русском](README.ru.md)*

Administrative control-plane service for the `shaverma` project.

This repository is **independent** from the main `shaverma` repository:
it does not import shaverma's code, does not depend on its models, and
is not modified by changes here. It connects to the same physical
`system_db` database, but owns and touches only its own `admin_*`
tables.

## Current scope

- A FastAPI backend with two-factor (password + Telegram OTP) admin
  login, server-side sessions, and an audit log.
- A minimal, fully static/independent frontend: login flow, a dashboard
  that lists shaverma's backend services and their live systemd status,
  a per-service `.env` editor, and a wizard for provisioning a brand-new
  service end to end.
- A safe, generic subprocess execution layer (`app/system`), and the
  real capabilities built on top of it: starting/stopping a shaverma
  instance's backend systemd unit; reading/writing that instance's
  root-owned `.env` file; and the full new-service pipeline --
  provisioning its directory tree, placing uploaded code, running the
  separate "bot" project's credential-provisioning script, building its
  frontend, and writing its nginx + systemd config -- each through its
  own narrowly scoped privileged helper.

It deliberately does **not** implement: admin roles/permissions, any
network-reachable way to register/edit/remove an admin (a local-only
script exists for the first of those -- see "Administrators" below,
it's not part of the running service), or any endpoint beyond what's
listed above that manages the Ubuntu host (arbitrary deploy/redeploy of an *existing*
service's code, git pull, docker, logs, a general file manager, a
shell/terminal, or anything similar). Those stay out of scope until a
later stage builds on top of this foundation. The new-service wizard
also deliberately leaves a few things manual -- see "New-service
provisioning wizard" below for exactly what and why.

## Stack

- Backend: Python 3.12+, FastAPI, SQLAlchemy 2.x, Alembic, PyMySQL,
  pydantic-settings, pwdlib (Argon2id), httpx.
- Frontend: static HTML/CSS/vanilla JS, no build step, no framework
  coupling to the backend (the backend is a plain JSON API and can be
  paired with any frontend later).

## Project layout

```
backend/
  app/
    core/         settings, DB engine/session, crypto primitives, rate limiting
    models/       SQLAlchemy models for admin_users / admin_login_challenges /
                  admin_sessions / admin_audit_events (adminka-owned, migrated)
    external/     minimal read/write mapping onto shaverma's own `services`
                  table -- NOT owned by adminka, no migration here (see below)
    schemas/      Pydantic request/response models
    api/          FastAPI routers (health, auth, services + .env editor,
                  new-service provisioning wizard)
    auth/         password hashing, OTP, sessions, auth dependencies
    audit/        audit log writer
    telegram/     minimal client for the dedicated admin Telegram bot
    middleware/   request-id middleware
    system/       CommandExecutor, ActionRegistry, every concrete
                  SystemAction, and the business-logic layer between the
                  API and the registry for each capability
                  (service_control, env_file_control, nginx_control)
    provisioning/ everything the new-service wizard needs that ISN'T a
                  SystemAction: domain/punycode, DB row creation, zip
                  upload validation, the bot credential script's fixed
                  text, .env/nginx/systemd templates, port allocation
  scripts/
    env_file_helper.py         privileged root-owned helper (see below)
    instance_files_helper.py   -- deployed separately, root:root mode 700,
    nginx_config_helper.py        NOT part of the app's own import path
    systemd_unit_helper.py
  create_admin.py   local-only script to provision an admin_users row --
                     NOT deployed, not reachable through the running app
                     (see "Administrators" below)
  migrations/   Alembic, independent history (see below)
  tests/
deploy/
  shaverma-adminka.service   example systemd unit for adminka itself
frontend/
  login.html         step 1 (password) + step 2 (Telegram OTP)
  index.html         dashboard: services list, live systemd status, start/stop
  service-env.html   per-service .env editor (field/value table)
  new-service.html   new-service provisioning wizard
  css/, js/
```

## Running the backend locally

```bash
cd backend
uv venv --python 3.12 .venv
uv pip install -e ".[dev]" --python .venv/bin/python
cp ../.env.example .env   # then fill in real values
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
```

(Any standard `pip install -e ".[dev]"` in a 3.12 venv works too; `uv`
is just faster.)

## Frontend

Plain static HTML/CSS/vanilla JS, no build step, nginx (or any static
file server) serves `frontend/` as-is. It knows nothing about the
backend beyond one thing it must be told by hand:

**`frontend/js/config.js`'s `API_BASE` constant is hardcoded to
`http://127.0.0.1:8100/api/v1`** -- the local-dev default from "Running
the backend locally" above. Every page includes this one file first, so
it's the single place to edit. On a real deployment, where the frontend
is served from one nginx `server{}` block and the backend from a
*different* one proxying to uvicorn (see "New-service provisioning
wizard" for the same front/back split, done per-service), this needs to
point at wherever the backend's `server{}` block is actually publicly
reachable -- **not** `127.0.0.1:<port>`, which from a visitor's browser
means their own machine, not the server, and just fails to connect:

```js
const API_BASE = "https://api-админка.example-service.рф/api/v1"; // your actual backend origin
```

Forgetting this edit is the most common way this ends up looking broken
after a deploy: the pages load fine (nginx *is* serving the static
files correctly), but every API call the JS makes silently tries to
reach `127.0.0.1:8100` on whoever's browser is viewing the page.

## Database migrations

Alembic is configured with its own migration history, kept fully
independent from the shaverma project's own migrations even though both
run against the same `system_db`:

- migrations live under `backend/migrations`, not the repo root;
- Alembic's version-tracking table is named **`admin_alembic_version`**
  (not the default `alembic_version`), so it can never collide with or
  be mistaken for the shaverma project's own Alembic history in the
  same database;
- `migrations/env.py` restricts autogenerate to tables named `admin_*`,
  so `alembic revision --autogenerate` can never propose altering or
  dropping a table this project doesn't own.

```bash
cd backend
.venv/bin/alembic upgrade head
```

## Administrators

There are exactly **two** administrators. They are fully equal — there
are no roles, permissions, or groups in this system, by design.

Administrators are **not** created through the API or the frontend --
neither exists on purpose, and never will: nothing served by the running
app can create an admin. What *does* exist is `backend/create_admin.py`,
a local-only script -- run it by hand, from a shell with access to the
real `.env`/database:

```bash
cd backend
.venv/bin/python create_admin.py --username alice --telegram-user-id <alice's telegram user id>
```

It prompts for the password interactively (twice, never as a CLI
argument -- that would land in shell history and process listings),
checks `username`/`telegram_user_id` aren't already taken, warns (with a
confirmation prompt, not a hard block) if the system already has two or
more administrators since the rest of adminka assumes exactly that many,
and otherwise inserts the row itself using the app's own
`hash_password()` -- no separate hashing step, no hand-written SQL.

`telegram_user_id` is the admin's numeric Telegram user id -- **not**
their phone number, and not a separate "chat id": for a private
bot<->user chat these are numerically the same value, so this one field
is all delivery needs. Get it e.g. by having the admin message the admin
bot once and reading `message.from.id` off the bot's `getUpdates`
response (a phone number alone cannot be used to message a Telegram user
via the Bot API -- there is no such lookup in that API).

If a raw `INSERT` is ever preferred instead (e.g. scripting this from
outside a shell that has the venv): generate a compatible hash with
`hash_password()` from `app.auth.password` the same way the script does,
and insert into `admin_users(username, password_hash, telegram_user_id,
is_active)` directly -- the columns are exactly those four plus the
auto-managed `id`/timestamps.

## Telegram bot

The admin panel uses its **own dedicated Telegram bot**, separate from
the shaverma customer-facing bot. Create a bot via @BotFather, put its
token in `ADMIN_TELEGRAM_BOT_TOKEN`, and never reuse the main product
bot's token here. The bot currently does exactly one thing:
`TelegramClient.send_login_code(telegram_user_id, code)`.

If `api.telegram.org` isn't directly reachable from where adminka is
deployed, set `TELEGRAM_PROXY_URL` (`http://`, `https://`, or
`socks5://[user:pass@]host:port`) and every call routes through it --
unset, it's a direct connection, same as before this existed.
`socksio` (needed for the `socks5://` scheme) is already a dependency
either way.

## Auth flow

```
POST /api/v1/auth/login/start   {username, password}
  -> {challenge_id, expires_at}   (OTP sent via Telegram)

POST /api/v1/auth/login/verify  {challenge_id, code}
  -> sets HttpOnly session cookie + CSRF cookie

GET  /api/v1/auth/me            -> current admin
POST /api/v1/auth/logout        -> requires X-CSRF-Token header
```

Sessions are server-side (`admin_sessions` table); the browser only ever
holds an opaque random token in an HttpOnly, SameSite=Strict cookie
(Secure in production). The database stores only a SHA-256 digest of
that token. There is no JWT and nothing auth-related is ever put in
`localStorage`.

CSRF protection uses the double-submit-cookie pattern: `login/verify`
also sets a non-HttpOnly `admin_csrf` cookie, whose value must be
echoed back in the `X-CSRF-Token` header on state-changing requests
(`/auth/logout`, `/services/{id}/start`/`.../stop`/`check-status`, and
every provisioning-wizard step).

**If the frontend and backend are deployed on different subdomains**
(e.g. `админка.example.com` serving the static files,
`api-админка.example.com` proxying to uvicorn — a real, working split,
not just an example) **set `COOKIE_DOMAIN`** (e.g. `.example.com`,
leading dot, covers every subdomain). Left unset, both cookies default
to host-only -- scoped to whichever origin actually issued them, which
is the *backend's* origin, since that's what the frontend's `fetch()`
calls target. The session cookie still works fine either way (the
browser just attaches it automatically on matching requests), but the
CSRF cookie specifically needs to be read by `document.cookie` from
JavaScript running on the *frontend's* own origin -- and a host-only
cookie set by a different origin is invisible there, browser-enforced,
same mechanism that keeps a cross-site attacker from reading it either.
Without `COOKIE_DOMAIN` in a split deployment: login succeeds (nothing
about it needs the CSRF cookie), but every POST fails with "CSRF token
missing or invalid" -- the frontend's `getCookie("admin_csrf")` always
returns null, so `X-CSRF-Token` never even gets attached.

## Audit log

Every auth event and every service-control/.env action is recorded in
`admin_audit_events`: `auth.login.password_failed`,
`auth.login.otp_requested`, `auth.login.otp_failed`,
`auth.login.success`, `auth.logout`, `service.start`, `service.stop`
(target = the resolved unit name, plus exit code and duration),
`env.read`, `env.write` (target = `system_name`; `env.write`'s
`parameters_json` holds only the *names* of keys added/removed/changed,
e.g. `{"added": ["NEW_KEY"], "removed": [], "changed": ["FOO"]}` — never
values). `env.read` is logged on success too, not just failure, since
viewing a service's secrets is itself worth an audit trail.
`app/audit/service.py` actively strips any parameter key that looks
sensitive (`password`, `otp`, `token`, `secret`, ...) before writing —
passwords, password hashes, OTP codes, session tokens, the Telegram bot
token, and .env values are never logged anywhere.

## The system command layer

`app/system/executor.py` provides `CommandExecutor`, a safe wrapper
around `asyncio.create_subprocess_exec` (never a shell string — the
executable and each argument are always passed as separate items, so
there is no shell-injection surface by construction). It supports a
timeout, a restricted `cwd`/environment, capped stdout/stderr capture,
and killing a hung process, returning a structured `CommandResult`.

`app/system/registry.py` defines the `SystemAction` protocol and an
`ActionRegistry` actions register into by name. There is intentionally
no generic `execute(command: str)` entry point anywhere in the API —
every capability is an explicit, named, individually-reviewed
`SystemAction`. The complete set registered today
(`app/system/service_actions.py` + `app/system/env_actions.py`, wired up
once at startup by `app/system/bootstrap.py`):

| name             | what it runs                                | privilege |
|------------------|----------------------------------------------|-----------|
| `service.status` | `systemctl show <unit> --property=...`        | none      |
| `service.start`  | `sudo systemctl start <unit>`                 | sudoers   |
| `service.stop`   | `sudo systemctl stop <unit>`                  | sudoers   |
| `env.read`       | `sudo env_file_helper.py read <system_name>`  | sudoers   |
| `env.write`      | `sudo env_file_helper.py write <system_name>` (new content on stdin) | sudoers |

`app/system/service_control.py` is the layer above the registry
(`API -> ServiceControlService -> ActionRegistry -> CommandExecutor`):
it turns a `services.system_name` value into a unit name
(`{system_name}-backend.service`), validates that value against a safe
identifier pattern first, and decides "does this unit exist" from
`systemctl show`'s `LoadState` (`not-found` -> doesn't exist -- reported
to the API/UI as such rather than as an error, and start/stop refuse to
even attempt a `sudo` call against a unit that doesn't exist).
`app/system/env_file_control.py` is the equivalent layer for `.env`
files -- see the next section.

`CommandExecutor` can also pipe bytes to a child's stdin
(`CommandSpec.stdin`, used by `env.write` to hand the new file content
to the helper script) -- and gives a child **no** stdin at all
(`DEVNULL`) when `stdin` is `None`, rather than silently inheriting the
server process's own, so a spawned command can never accidentally block
on it.

## Service control panel

`GET /api/v1/services` lists every row of shaverma's own `services`
table that has `system_name` set. It deliberately does **not** touch
systemd at all -- it's a plain DB read, so listing stays cheap
regardless of how many services are onboarded -- so each row's `status`
comes back `null` and the panel colors it from the stored `is_active`
flag alone (with a "not checked" hint), not from live reality.

Three actions all touch systemd directly and return that row's live
status, and all three require an authenticated session and the CSRF
header, and are all audit-logged exactly like the auth endpoints:

- `POST /api/v1/services/{id}/start` / `.../stop` control the backend
  unit (`service.start` / `service.stop`, with the unit name, exit code,
  and duration). On success, they also write `services.is_active` to
  match (`True` after start, `False` after stop).
- `POST /api/v1/services/{id}/check-status` (`service.check_status`)
  changes nothing about the unit itself -- it only reads its live
  status via the same unprivileged `systemctl show` the other two use --
  but if that disagrees with the stored `is_active`, it corrects
  `is_active` to match and records that in the audit event
  (`parameters.corrected`).

`is_active` is the single source of truth the list renders from; the
panel is what keeps it truthful, via these three actions. It can still
lag reality between them, e.g. if the unit was started/stopped, or
`is_active` itself was changed by shaverma's own business logic,
outside the panel.

On the dashboard itself, each row/card exposes `start`/`stop` and
`check-status` directly as icon buttons -- not tucked into a menu,
since they're the actions taken most often. A separate "..." menu per
row holds the three things that navigate away to the per-service ".env"
page instead of acting in place: editing `.env`, the file-update panel,
and the seed panel (deep-linked via `service-env.html?id=...#env-panel`
/ `#update-panel` / `#seed-panel` -- `service-env.js` scrolls to the
matching section once it's actually visible, since all three start
`hidden` and a browser's own anchor-scroll can't reach a hidden target
on first load, nor retries once it's revealed).

`POST /api/v1/services/{id}/check-status`, run against every service at
once, is also exposed as a single "Проверить службы" button on the
dashboard header -- fires all of them in parallel
(`Promise.allSettled`, so one failing service never blocks the rest
from updating) rather than adding any new bulk endpoint; there isn't
one, this is purely N sequential-looking-but-parallel calls to the
existing per-service endpoint from the frontend.

adminka does not own the `services` table -- it belongs to the
[shaverma repo](https://github.com/Shira-Artem/shaverma). `services.system_name`
(`varchar(30)`, nullable, no unique constraint) already exists in
`system_db`, so no migration was needed here to introduce it.
`app/external/models.py` maps only the columns adminka actually needs
(`id`, `name`, `is_active`, `system_name`, `server_local_port`, ...) on a
declarative base completely separate from adminka's own `Base` — it is
never part of `target_metadata` in `migrations/env.py`, so there is no
migration anywhere in this project that could create, alter, or drop
`services`.

## .env editor

Each shaverma instance is deployed as
`{some root folder}/{system_name}/`, owned by root, containing `dist/`
and `backend/` (owned by the OS user that instance runs as) and a
root-owned `.env`. adminka's own process is unprivileged and can't read
or write that file directly, so this goes through a narrowly scoped
privileged helper instead of a generic `sudo cat`/`sudo tee` (which
would let anything holding the sudoers grant read or overwrite an
arbitrary root-owned file):

- `backend/scripts/env_file_helper.py` -- a small standalone script,
  deployed separately (root-owned, mode `700`, **not** part of the
  adminka Python package's own import path). It accepts only
  `read <system_name>` / `write <system_name>` (new content on stdin
  for `write`), never a path; the actual `{root}/{system_name}/.env`
  path is built from a `PROJECT_ROOT` constant hardcoded in the script
  itself, so no argument the caller supplies can ever resolve outside
  that root. `write` replaces the file atomically (write to a temp file
  in the same directory, `os.replace`) and preserves the existing
  file's owner/group/mode -- or defaults to `root:root 0644` for a
  brand new one (root-owned so only this helper can modify it, but
  world-readable so the deployed service's own process -- whatever OS
  user that happens to run as -- can still read its `.env` at startup;
  matches how already-deployed instances' `.env` files are set up in
  practice). An earlier `root:root 0600` default made a brand new
  `.env` unreadable by the very service it was generated for -- fine
  until the new-service wizard's first-ever write started exercising
  this exact path.
- `app/system/env_file_control.py` owns the `.env` text format on the
  application side: parsing preserves comments and blank lines (and
  their position) so editing through the table UI doesn't silently
  discard an operator's own annotations -- only `KEY=VALUE` lines are
  ever added, changed, or removed. A key must match
  `^[A-Za-z_][A-Za-z0-9_]*$`; a value may be any string that fits on one
  line (no `\n`/`\r`/NUL). No .env file yet for an otherwise-real
  instance reads back as an empty list rather than an error, so the
  panel can still be used to create one; writing to a `system_name` with
  no instance directory at all returns 409, same "doesn't exist, say so"
  spirit as the service-control panel above.

API: `GET /api/v1/services/{id}/env` returns the parsed entries (plus a
display-only resolved path, if `INSTANCES_ROOT_DIR` is set).
`POST /api/v1/services/{id}/env` takes the *complete* desired
`{key, value}` list -- a key missing from it is deleted, a new one is
added, a changed value is updated -- and requires the CSRF header like
every other state-changing endpoint. There's no version/lock on
concurrent edits; with two admins this is an accepted last-write-wins
limitation, not something this stage tries to solve.

Frontend: `service-env.html` (linked from each row's ".env" button on
the dashboard) is an actual field/value table, not a raw text box --
add, edit, remove, plus a "show values" toggle (masked by default, since
this is exactly where secrets live) and a confirmation prompt before
saving if any variable is about to be removed.

## New-service provisioning wizard

`new-service.html` walks an admin through turning a domain label into a
fully running shaverma instance. It is **one endpoint per step, not one
all-or-nothing transaction** -- the side effects span the DB, the
filesystem, a *separate project's own database writes* (see "credential
provisioning" below), nginx, and systemd, and there is no way to roll
all of that back atomically as a group if step 5 fails after steps 1-4
already succeeded. Instead:

- every step is independently callable and safe to retry -- it either
  checks live reality before acting (e.g. `instance.install_backend`
  requires `instance.create_tree` to have actually run) or fully
  replaces rather than appends (a re-run of the nginx step updates its
  existing block in place; the systemd step rewrites the whole unit
  file);
- `GET /api/v1/services/{id}/provision/status` never trusts a cached
  "step N done" flag -- it re-derives every step's status from reality
  each time it's called (does the directory exist and have content?
  does `.env` have `SYSTEM_GATEWAY_API_KEY` set? does the nginx config
  have this service's marker block? is the systemd unit active?), the
  same philosophy as the dashboard's live systemd status;
- every step is audit-logged individually, success or failure.

### Steps

1. **`POST /api/v1/services`** -- pure DB work, no filesystem/systemd/
   nginx side effect at all. Takes the admin-supplied third-level domain
   label (e.g. `индия`), name, `system_name`, `is_active` (default on),
   `channels` (`telegram`/`max`, default both on), and optional
   `bot_entry_key`/`client_bot_entry_key`. `app/provisioning/domain.py`
   builds `url` = `https://{label}.{SERVICE_DOMAIN_ZONE}` and
   `backend_base_url` = `https://api-{label}.{SERVICE_DOMAIN_ZONE}`,
   both IDNA2008/punycode-encoded in full (via the `idna` package, not
   Python's older built-in codec) -- so a Cyrillic label under a
   Cyrillic zone (`example-service.рф`) round-trips correctly.
   `app/provisioning/service_creation.py` checks `url`, `system_name`,
   `bot_entry_key`, and `client_bot_entry_key` for uniqueness against
   existing `services` rows *before* inserting, returning 409 with the
   specific field name rather than letting a DB `IntegrityError` surface.
2. **`POST /services/{id}/provision/dirs`** -- `instance.create_tree`:
   creates `{root}/{system_name}/`, `dist/`, `backend/` (owned by
   `SERVICE_WORK_USER`), idempotently.
3. **`POST /services/{id}/provision/upload`** (`multipart/form-data`,
   one `file` field) -- the admin sends a zip with top-level `frontend/`
   and `backend/` folders. `app/provisioning/upload.py` extracts it
   in-process with Python's `zipfile` (never `unzip` via a subprocess --
   no command-injection surface at all from a zip's contents), rejecting
   path traversal, symlinks, and archives over a size/entry-count limit
   (500 MB total uncompressed, `_MAX_TOTAL_UNCOMPRESSED_BYTES`),
   *before* extracting anything. The `backend/` half is then moved into
   the instance tree via `instance.install_backend`; `frontend/` stays
   in adminka's own unprivileged staging directory (`INSTANCE_STAGING_DIR`)
   for the next step.

   **nginx's own `client_max_body_size` defaults to 1 MB** -- far below
   any real project zip -- and a request nginx itself rejects for being
   too large never reaches this app at all, so it comes back with no
   CORS headers either (those are added by the app's own
   `CORSMiddleware`, which never runs): the browser shows a `413`
   alongside a confusing "CORS Missing Allow Origin", masking the real
   cause. Raise it in the *backend's* nginx `server{}` block (not the
   frontend's -- this only affects the upload endpoint):
   ```nginx
   client_max_body_size 200M;
   ```
   200M is comfortably under the 500 MB uncompressed cap above; there's
   no benefit to raising it past that.
4. **`POST /services/{id}/provision/env`** -- takes admin-supplied
   `database_name`/`database_user` (defaulted to `system_name` in the
   UI, editable) and creates them:
   `app/provisioning/database_provisioning.py` runs `CREATE DATABASE IF
   NOT EXISTS`, then `CREATE USER ... IDENTIFIED BY RANDOM PASSWORD`
   (or, on a retry against a user that already exists, `ALTER USER ...
   IDENTIFIED BY RANDOM PASSWORD` -- always a *fresh* password rather
   than silently keeping whichever one was generated, and lost, on an
   earlier attempt), then the fixed `GRANT SELECT, INSERT, UPDATE,
   DELETE, CREATE, ALTER, INDEX, REFERENCES ON {db_name}.* TO
   '{db_user}'@'localhost'`. `database_name`/`database_user` are
   validated against a strict identifier pattern *before* ever being
   interpolated into SQL text -- MySQL has no way to bind an identifier
   as a parameter, so that check is the only real defense here. Runs on
   the same MySQL server/connection as `SYSTEM_DATABASE_URL` -- see the
   sudoers section below ("What this wizard does NOT automate") for the
   extra grant that connection's own MySQL user needs. It then runs the
   separate "bot"
   project's own credential-provisioning script (below), and renders and
   writes the new instance's complete `.env` -- including the freshly
   built `DATABASE_URL` -- via the *same* `EnvFileControlService`/
   `env.write` the manual editor uses. `YOOKASSA_SHOP_ID`/
   `YOOKASSA_SECRET_KEY` are optional admin input on this same step;
   left blank if not given (they, and anything else, can still be
   adjusted afterwards via `service-env.html`).
5. **`POST /services/{id}/provision/frontend`** -- writes the `.env`'s
   `VITE_`-prefixed subset into the staged frontend source, then runs
   `npm install` and `npm run build` there (see "npm install privilege
   model" below), then moves the built `dist/` into the instance tree
   via `instance.install_dist` and deletes the staging copy (source +
   `node_modules` + intermediate build output) -- nothing about the
   uploaded frontend *source* survives past this step, only the built
   static output.
6. **`POST /services/{id}/provision/nginx`** -- allocates a local port if
   this service doesn't already have one (`services.server_local_port`
   is the single source of truth for "already spoken for" -- not the
   nginx config, which only reflects it; `app/provisioning/port_allocation.py`
   picks the first free port from `SERVICE_PORT_RANGE_START` that isn't
   already some other row's `server_local_port` and that `ss -Hltn`
   doesn't report as listening -- reading listening ports needs no
   privilege). A retry of this step reuses the port already stored on
   the row instead of picking a new one. Renders this service's two
   `server {}` blocks (front + back) wrapped in a
   `# adminka:service:{system_name}:begin/end` marker pair, and asks
   `NginxControlService` (`app/system/nginx_control.py`) to upsert it --
   see "nginx: never a partial edit" below for what that actually does.
7. **`POST /services/{id}/provision/systemd`** -- renders the unit file
   (`app/provisioning/systemd_template.py`; explicitly **no** `--reload`
   on `uvicorn`'s `ExecStart` -- that's a dev-only file-watcher flag with
   no place in a production unit), writes it via `systemd.write_unit`
   (which also runs `systemctl daemon-reload`, already-root, inside that
   same helper invocation), then `service.enable_now` (`systemctl enable
   --now`, so it's both started immediately and survives a reboot).

### Credential provisioning (the "bot" project)

Step 4 shells out to a **separate codebase** -- not shaverma, not this
repo -- that owns generating `SYSTEM_GATEWAY_API_KEY` /
`SYSTEM_GATEWAY_SIGNING_SECRET` for a service and writes them into
`system_db` via its *own* SQLAlchemy session (adminka never touches
those columns itself). `app/provisioning/credentials_script.py` embeds
a fixed, reviewed Python script (translated from a shell heredoc into a
form `CommandExecutor` can run directly -- it never uses a shell, so it
can't `source venv/bin/activate`; invoking `{SERVICE_VENV_DIR}/bin/python`
directly has the same effect for one subprocess). The only variable
input is the new service's numeric id, passed via the `SERVICE_ID`
environment variable, never interpolated into the script text. No sudo
is used here -- confirmed that adminka's own OS user already has
read/execute access to the bot project's code and its shared venv.

**`BOT_PROJECT_DIR` must be the bot project's own directory** -- the one
whose immediate children are its `database.py`/`config.py`/etc, and its
own `.env` -- **not** its parent, even though `import bot....` needs the
*parent* directory importable. Reconciling that without touching the
bot project's own code (or its `.env` lookup, which is relative to
`cwd`, same `env_file="."` pattern this app's own `Settings` uses) is
exactly why `credentials_script.py` sets `cwd=BOT_PROJECT_DIR` (so the
bot project's own settings loader keeps finding its `.env`) *and*
`PYTHONPATH=` the parent of `BOT_PROJECT_DIR` (so `import bot....`
resolves) as two separate things, rather than relying on `python -c`
putting `cwd` on `sys.path` the way the module used to before this was
fixed -- that only works when `cwd` *is* the import root, which
conflicts with the bot project needing `cwd` to be one level lower, at
its own directory.

### npm install privilege model

`npm install`/`npm run build` execute arbitrary code from `package.json`
and its dependencies' own lifecycle scripts. They run as **adminka's own
OS user, in `INSTANCE_STAGING_DIR`** -- never as root, and never inside
the root-owned instance tree; only the finished, static `dist/` output
ever gets promoted into that tree, via `instance.install_dist`. This was
a deliberate choice among real alternatives (running as a dedicated,
even-more-isolated build-only OS user was the other one seriously
considered) -- adminka's own account is not maximally low-privilege
either (it holds the sudoers grants below), so if that trade-off ever
stops being acceptable, swapping in a dedicated build user only touches
`app/provisioning/frontend_build.py`.

`node_bin_dir`/`NODE_BIN_DIR` must be the concrete versioned bin/
directory `nvm use 22` would otherwise resolve to (e.g.
`~/.nvm/versions/node/22.23.0/bin`) -- `CommandExecutor` never sources
nvm's shell functions, so `nvm use` itself cannot be invoked.

**The Telegram Web App SDK (`telegram-web-app.js`)**, if a service's own
frontend loads it locally rather than from Telegram's CDN, is expected
at `public/telegram-web-app.js` in that frontend's source *before* the
build runs -- Vite (and every bundler this app has been used with so
far) copies everything under `public/` verbatim into `dist/`, it
doesn't fetch or bundle it from anywhere. `build_frontend` copies it
there itself (creating `public/` first if it doesn't exist yet), gated
by two independent settings:

- **`TELEGRAM_WEB_APP_JS_PATH`** -- adminka's own setting (`.env`), a
  single local path on this host, readable by adminka's own OS user,
  shared by every service that opts in. Unset means no frontend build
  ever touches `public/telegram-web-app.js` at all, whatever any given
  service says.
- **`TELEGRAM_WEB_APP_LOCAL_SDK_ENABLED`** -- per-service, in that
  service's own `.env` (`env_template.render_new_service_env` adds it
  to every newly generated `.env`; the new-service wizard's env step
  has a "Local Telegram Web SDK" checkbox for it, **on by default**),
  editable any time afterwards right there in the `.env` editor like
  any other value. `env_template.extract_telegram_web_app_local_sdk_enabled`
  is what reads it back out at build time -- deliberately not part of
  `extract_frontend_vars`'s `VITE_`-prefixed subset, since this is a
  build-time-only switch for adminka itself, never meant to reach the
  frontend's own runtime `.env` or get embedded in the built bundle.
  Both places that build a frontend (the new-service wizard's own
  frontend step, and the file-update panel's frontend rebuild) read it
  fresh from that service's current `.env` each time, so flipping it
  takes effect on the next build, no adminka restart involved.

`false` on the per-service flag is checked first and is always a no-op,
before anything else -- a service that opts out never has `public/`
touched at all, regardless of whether `TELEGRAM_WEB_APP_JS_PATH` is even
configured. With the flag on (the default) and `TELEGRAM_WEB_APP_JS_PATH`
left unset, it's *also* a no-op (nothing to copy from) -- adminka simply
hasn't set this feature up yet, not every service's own error to report.
Only once both are true -- opted in *and* a path is configured -- does a
missing file at that path become an error: silently shipping a build
that was supposed to include the Telegram SDK and doesn't would be a
much worse failure mode than failing loudly right here.

### nginx: never a partial edit

Nginx corrupting the *shared* config file would take down every
provisioned site at once, not just the one being added. So
`NginxControlService.upsert_service_block` never just writes and hopes:
it reads the current config, computes the new content in memory (via
`app/provisioning/nginx_template.py`'s marker-based insert/replace --
idempotent, so re-running this step updates the existing block instead
of duplicating it), writes that, runs `nginx -t`, and if that fails,
**immediately writes the previous content back** before returning an
error -- the live config is never left in a state that failed
validation, even briefly. Only after `nginx -t` passes does it run
`systemctl reload nginx`.

### What this wizard does NOT automate

The 7-step process this was built from never mentioned these, so
automating them would be inventing scope rather than following it --
each is left as an explicit manual step instead. (Creating the
service's own MySQL database and user *used to* be on this list -- see
step 4 above, it's automated now.)

- **Per-service TLS certificates.** A wildcard certificate covering
  every `{label}.SERVICE_DOMAIN_ZONE` subdomain is assumed to already
  exist (`NGINX_SSL_CERTIFICATE`/`NGINX_SSL_CERTIFICATE_KEY`); nothing
  here calls certbot or any other issuance flow.
- **YooKassa credentials.** `YOOKASSA_SHOP_ID`/`YOOKASSA_SECRET_KEY` are
  optional admin input on the env step (left blank if not given), never
  generated -- exactly as the template this was built from marked them
  ("entered by hand, optional").
- **The Telegram/MAX deep-link bot identities**
  (`SERVICE_TELEGRAM_BOT_USERNAME`, `SERVICE_MAX_BOT_DEEP_LINK_ID`) are
  assumed fixed and shared across every instance, based on the one
  example available when this was built -- only the `?start=` parameter
  is derived per service. If that assumption is wrong for a given
  service, fix it afterwards via the `.env` editor; it's cheap to be
  wrong about (a broken deep link, not a broken deployment).

In production this service runs as its own unprivileged Ubuntu user,
e.g. `shaverma-admin` — never as root. Nothing in the code assumes root,
and **the username is not application config**: the app never reads its
own OS username, and `sudo` authorizes based on the real UID of the
running process, not on anything from `.env`. It only needs to be
consistent between two OS-level places:

1. the systemd unit that runs adminka itself — see
   `deploy/shaverma-adminka.service`, `User=`/`Group=`;
2. the sudoers rule below, granted to that same user.

Rename `shaverma-admin` to whatever you like in both places together;
there's nothing to change in `.env` either way.

**The MySQL user `SYSTEM_DATABASE_URL` authenticates as also needs
`CREATE`, `CREATE USER`, and `GRANT OPTION`** (in addition to whatever
it already had for adminka's own `admin_*` tables and shaverma's
`services` table) -- step 4 of the wizard uses that same connection to
create each new service's own database and user
(`app/provisioning/database_provisioning.py`). This is a real widening
of what a leaked `SYSTEM_DATABASE_URL` could do (create/alter databases
and users server-wide, not just within `system_db`); a separate,
narrowly-scoped credential used only for this one action was considered
and deliberately not done -- revisit that if the wider blast radius ever
becomes a concern:

```sql
GRANT CREATE, CREATE USER, GRANT OPTION ON *.* TO 'your_system_db_user'@'%';
FLUSH PRIVILEGES;
```

`service.status` (read-only `systemctl show`), the credential
provisioning script, and `npm install`/`npm run build` (see above) need
no elevated privilege at all. Everything else that touches a root-owned
path or a systemd/nginx service needs sudo, via a narrowly scoped
allow-list, e.g. `/etc/sudoers.d/shaverma-admin-systemctl`:

```
shaverma-admin ALL=(root) NOPASSWD: \
  /usr/bin/systemctl start *-backend.service, \
  /usr/bin/systemctl stop *-backend.service, \
  /usr/bin/systemctl enable --now *-backend.service, \
  /usr/bin/systemctl reload nginx, \
  /opt/shaverma_adminka/backend/scripts/env_file_helper.py read *, \
  /opt/shaverma_adminka/backend/scripts/env_file_helper.py write *, \
  /opt/shaverma_adminka/backend/scripts/instance_files_helper.py create_tree *, \
  /opt/shaverma_adminka/backend/scripts/instance_files_helper.py install_backend *, \
  /opt/shaverma_adminka/backend/scripts/instance_files_helper.py install_dist *, \
  /opt/shaverma_adminka/backend/scripts/nginx_config_helper.py read, \
  /opt/shaverma_adminka/backend/scripts/nginx_config_helper.py write, \
  /usr/sbin/nginx -t, \
  /opt/shaverma_adminka/backend/scripts/systemd_unit_helper.py write *, \
  /opt/shaverma_adminka/backend/scripts/seed_helper.py list *, \
  /opt/shaverma_adminka/backend/scripts/seed_helper.py read_data *, \
  /opt/shaverma_adminka/backend/scripts/seed_helper.py write_data *, \
  /opt/shaverma_adminka/backend/scripts/seed_helper.py run_db *
```

(sudoers doesn't actually support line continuations inside a single
rule the way shown above for readability -- write it as one line, or as
separate `Cmnd_Alias`/rule entries; either way, validate before
installing: `visudo -c -f /etc/sudoers.d/shaverma-admin-systemctl`.)

This grants exactly what's listed — nothing else, and every helper
script argument is either a fixed literal (`nginx_config_helper.py`
takes none at all) or a `system_name`/unit name/pair_key matched against
`unit_name_for()`'s own validation (`app/system/service_control.py`) or
`seed_helper.py`'s own `PAIR_KEY_RE` on the application side first.
Before installing the rule, deploy **all five helper scripts** as
**root-owned, mode `700`**, so `shaverma-admin` can never read or modify
them directly (only invoke them, elevated, via this exact grant):

```bash
for helper in env_file_helper instance_files_helper nginx_config_helper systemd_unit_helper seed_helper; do
  sudo install -o root -g root -m 700 \
    "backend/scripts/${helper}.py" \
    "/opt/shaverma_adminka/backend/scripts/${helper}.py"
done
```

Then edit each script's own hardcoded constant(s) to match your real
deployment:

| script                       | constant(s)                       | must match                     |
|-------------------------------|------------------------------------|---------------------------------|
| `env_file_helper.py`           | `PROJECT_ROOT`                    | `INSTANCES_ROOT_DIR`            |
| `instance_files_helper.py`     | `PROJECT_ROOT`, `STAGING_ROOT`, `WORK_USER` | `INSTANCES_ROOT_DIR`, `INSTANCE_STAGING_DIR`, `SERVICE_WORK_USER` |
| `nginx_config_helper.py`       | `CONFIG_PATH`                     | `NGINX_CONFIG_PATH`             |
| `systemd_unit_helper.py`       | `UNIT_DIR`                        | fixed at `/etc/systemd/system`, not an `.env` setting -- edit the constant directly if it ever needs to differ |
| `seed_helper.py`               | `PROJECT_ROOT`, `WORK_USER`, `VENV_DIR` | `INSTANCES_ROOT_DIR`, `SERVICE_WORK_USER`, `SERVICE_VENV_DIR` |

These constants -- never anything the caller sends -- are what actually
confine every read/write; a mismatch with the `.env` setting it's paired
with is safe (the helper just looks in the wrong place and fails, or the
app shows/computes a stale path), **except** `INSTANCES_ROOT_DIR`, which
by the time the new-service wizard writes a fresh nginx block or systemd
unit is baked directly into that service's own config -- see the
callout in "New-service provisioning wizard" above.

Also create the parent instances-root folder once, ahead of time, root-
owned and **world-traversable** (nginx and adminka's own unprivileged
status checks both need to reach into it):

```bash
sudo mkdir -p /opt/shaverma-instances
sudo chown root:root /opt/shaverma-instances
sudo chmod 755 /opt/shaverma-instances
```

**If `deploy/shaverma-adminka.service` uses `ProtectSystem=strict`** (it
does by default): that mounts the *entire* filesystem read-only for this
unit's process tree, and a privileged helper invoked from inside it via
`sudo` still inherits that same read-only view -- sudo changes uid/gid,
not the mount namespace. Without `ReadWritePaths=` naming every real
write target (`INSTANCES_ROOT_DIR`, `INSTANCE_STAGING_DIR`,
`NGINX_CONFIG_PATH`'s directory, `UNIT_DIR`, **and the three entries
below**), the `.env` editor and every write step of the new-service
wizard fail with a permission error at runtime, even though each one is
correctly privileged at the application layer -- see the comments in
`deploy/shaverma-adminka.service` itself, which already lists all
seven.

Three entries on that list aren't app paths at all -- they're *other
tools'* own runtime state, needed regardless of what this app itself
writes, and each produces its own specific, easy-to-misdiagnose failure
if missing:

- **`/run/sudo`** -- sudo's own per-user auth timestamp cache
  (`/run/sudo/ts/<uid>`), written on *every* sudo call regardless of
  `NOPASSWD`. Missing it: `sudo` logs `unable to open
  /run/sudo/ts/<uid>: Read-only file system`, then falls through to
  demanding an interactive password (which of course isn't available
  under systemd) -- so the app-level error just says something generic
  failed, and it's *every* sudo-elevated action in the app that breaks
  this way, not the one you happened to trigger first.
- **`/run/nginx.pid`** -- `nginx -t` (the `nginx.test` action) opens
  this as part of validating a config, even just to *test* it, not only
  when actually starting nginx. Missing it: `nginx -t rejected the new
  config (rolled back): ... open() "/run/nginx.pid" failed (30:
  Read-only file system)` on every nginx config write in the wizard
  (safely rolled back each time, per "nginx: never a partial edit"
  below, but still failing). If your `nginx.conf` sets a non-default
  `pid` directive, use that path instead.
- **`/var/log/nginx`** -- `nginx -t` also opens every `error_log`/
  `access_log` path referenced anywhere in `nginx.conf` while
  validating, same as the pid file above -- and that's the *entire*
  config, not just this app's own generated blocks, so any other site
  already on this nginx instance can be what fails the test if its own
  log path isn't writable. The whole directory is granted rather than
  just the two default log files, since any site's config can point log
  directives elsewhere under it.

More paths belonging to other tools invoked via `sudo` may surface the
same way as new actions are added later -- same fix each time: add the
specific path to `ReadWritePaths=`.

**If the service fails to start with `journalctl` showing something
like `Invalid environment variable name evaluates to an empty string:
127.0.0.1`, followed by uvicorn rejecting a port number as an
"unexpected extra argument"**: this is `${APP_HOST}`/`${APP_PORT}`
substitution in `ExecStart=` failing silently. systemd's own
`EnvironmentFile=` parser is *stricter* than the app's own
python-dotenv-based `.env` reader (`pydantic-settings`) and can reject a
line as malformed even though the app itself reads it just fine --
which is exactly why `uvicorn` run by hand (no `EnvironmentFile=`
involved at all) works while the same `.env` under systemd doesn't. The
current unit file sidesteps this entirely by hardcoding host/port
directly in `ExecStart=` rather than sourcing them from `.env` (neither
is read anywhere else in the app) -- if you're running an older copy of
the unit file that still does `--host ${APP_HOST} --port ${APP_PORT}`,
either update it the same way or find and fix whatever line in `.env`
systemd is choking on (`cat -A backend/.env` to reveal a stray line
break or `\r` a text editor may have introduced).

If `SYSTEMCTL_PATH`/`SUDO_PATH`/`ENV_HELPER_PATH`/
`INSTANCE_FILES_HELPER_PATH`/`NGINX_CONFIG_HELPER_PATH`/
`SYSTEMD_UNIT_HELPER_PATH`/`NGINX_BINARY_PATH` are overridden from their
defaults, update the sudoers rule to match.

## Updating an already-deployed service's files

`POST /api/v1/services/{id}/update` (multipart, field `file`) replaces
an already-deployed instance's backend and/or built frontend from a
freshly uploaded zip -- the same "stop the service, `rm -rf` the old
folder, move the new one in, start it again" an admin would otherwise do
by hand over SSH, done here from the panel instead. It's reachable from
the ".env" page for a service (`service-env.html?id=...`), below the
`.env` table.

The zip may contain a top-level `backend/`, `frontend/` (pre-build --
rebuilt here with `npm install && npm run build`, exactly like the
new-service wizard's own frontend step, using the service's *current*
`.env`'s `VITE_`-prefixed values), or both; an archive with neither is
rejected (422). Whichever folder(s) are present get replaced -- the rest
of the deployment (`.env`, the nginx block, the systemd unit) is left
completely untouched:

- **backend present** -> `instance.install_backend` (full
  replace, same privileged action the wizard's upload step uses), then
  the service is **restarted** so the new code actually takes effect.
- **frontend present** -> built in adminka's own unprivileged staging
  area (never as root, same as the wizard), then `instance.install_dist`
  (full replace). No restart, and systemd is never touched at all for a
  frontend-only update -- nginx serves the new static files directly off
  disk on the very next request.

**No new sudoers grant is needed for this feature.** It's built entirely
out of actions already listed in the sudoers rule above:
`instance.install_backend`/`instance.install_dist` (already granted for
the wizard), and the restart is deliberately **`systemctl stop` followed
by `systemctl start`**, not a single `systemctl restart` -- reusing the
two verbs already granted rather than adding a third rule just for this
(`ServiceControlService.restart`, `app/system/service_control.py`).

The restart step is best-effort and never turns a successful file
replacement into a failed request: if the unit doesn't exist, or the
restart command itself fails, the response still comes back `200` with
`restarted: false` in the body (mirrors how a failed start/stop above is
already reported: "the request itself succeeded; the command failed") --
check the service's status from the dashboard afterwards if that
happens. A failure *before* that point (a malformed archive, a failed
`instance.install_backend`/`instance.install_dist`, or a failed
`npm install`/`npm run build`) does fail the request (422/502), same as
the equivalent wizard step.

This intentionally does **not** run any dependency install step for the
backend (no `pip install`) -- every deployed instance's backend runs
against one shared virtualenv (`SERVICE_VENV_DIR` in `.env`,
`service_venv_dir` in `app/core/config.py`), exactly as the new-service
wizard already assumes; if an update's backend code needs a new
dependency, install it into that shared venv by hand, same as you would
for any other change to it.

## Seeding a service's database

Background: some deployed instances' `backend/app/seed/` folder holds
one or more *pairs* of scripts an operator otherwise runs by hand (`cd
backend && python -m app.seed.seed_db...`, in the shared venv) to
populate a fresh database -- `seed_data<suffix>.py` (the data, imported
by the other file) and `seed_db<suffix>.py` (the script that does the
actual DB writes), sharing a `<suffix>` (empty for the base
`seed_data.py`/`seed_db.py` pair, or e.g. `_mrgiros`, `_venue2`, one pair
per venue/franchise the same backend code serves). The panel exposes
exactly that same manual workflow -- pick a pair, edit its data file raw,
run its db script -- in two places, both backed by the exact same three
endpoints below:

- the ".env" page, below the file-update panel, for any already-deployed
  service (initial seeding done outside the wizard, or re-seeding
  later);
- the new-service wizard's own success screen (`new-service.html`,
  `app/success-stage` in the JS), offered right after a brand-new
  service finishes all 6 required provisioning steps. Deliberately
  **not** one of the wizard's required `provisioningKeys` -- it's
  optional and repeatable, so it never blocks or gates reaching the
  success screen; it only becomes reachable there because that's the
  first point a newly-created service is guaranteed to already have a
  working `.env` (and therefore a `DATABASE_URL` the seed script needs),
  which the required env step (03) already produced by then.

- `GET /api/v1/services/{id}/seed/pairs` -- lists the pairs for which
  *both* halves currently exist on disk (an orphan `seed_data_x.py` with
  no matching `seed_db_x.py`, or vice versa, is never offered). Empty is
  a normal result (no seed/ folder at all, or an older deployment that
  never had one), not an error.
- `GET /api/v1/services/{id}/seed/data?pair_key=...` /
  `POST .../seed/data` (body `{pair_key, content}`) -- read/replace the
  chosen pair's `seed_data<suffix>.py`, raw, no parsing of any kind
  (unlike the `.env` editor's KEY=VALUE table, this is a plain textarea
  over a plain-text Python file). `pair_key` is `""` for the base pair.
  The write endpoint deliberately can only *replace* a data file that
  already exists -- it never creates a new pair out of nothing, unlike
  the `.env` editor's "brand new file" case; a pair only becomes
  selectable by having been part of the backend code that was uploaded
  (initially, or via the update-files panel above).
- `POST /api/v1/services/{id}/seed/run` (body `{pair_key}`) -- runs that
  pair's `seed_db<suffix>.py` and returns its full, unfiltered
  stdout/stderr/exit code for the admin to read. **Whether it's safe to
  run more than once is entirely the seed script's own responsibility**
  -- nothing here checks for or prevents a duplicate run; the frontend
  only asks for an `window.confirm()` before submitting.

**A new privileged helper, `backend/scripts/seed_helper.py`, and four
new sudoers entries were needed for this** (`list`/`read_data`/
`write_data`/`run_db`) -- unlike the file-update feature above, this one
could *not* be built out of already-granted actions. Two separate
reasons converge here: `backend/app/seed/*.py` lives inside the
root/`WORK_USER`-owned instance tree (same category as `.env` -- nothing
outside a privileged helper touches it, on principle, whatever a given
deployment's file permissions happen to allow in practice), **and**
`run_db` needs to execute as a *different* OS user (`WORK_USER`) than
adminka's own process runs as, which categorically requires either sudo
or a setuid mechanism -- there's no way around a new grant for that part
specifically.

`run_db` drops privileges (`os.initgroups`/`setgid`/`setuid` to
`WORK_USER`, matching the deployed service's own systemd `User=`) before
`os.execve`-ing into the seed script -- admin-edited application code
never runs as root here, even though the helper itself starts out that
way (via sudo). `os.execve` replaces the helper process entirely, so the
seed script's own stdout/stderr/exit code become the command's -- exit
code `3` after that point is genuinely ambiguous (it's simultaneously
`seed_helper.py`'s own "db script not found" code *and* a valid exit
code a seed script could choose for its own reasons) and this layer
deliberately does not try to tell them apart; see
`SeedControlService.run_db`'s docstring. The forwarded stderr text is
what actually disambiguates it for a human either way.

No new `ReadWritePaths=` entry is needed in
`deploy/shaverma-adminka.service` for this -- `seed_helper.py`'s own
writes (replacing a `seed_data` file) stay inside `PROJECT_ROOT`
(`/opt/shaverma-instances` by default), already covered by the existing
entry. If a particular seed script itself writes to disk (not just the
database) for its own reasons, it inherits the same `ProtectSystem=strict`
restrictions as everything else invoked from this unit -- same fix as
always if that ever surfaces: add the specific path.

## Security notes

- Passwords: Argon2id only (`pwdlib`), never compared/stored any other way.
- Tokens (session, OTP verification): generated with `secrets`, compared
  with `hmac.compare_digest`.
- OTP codes are never stored in plaintext, only as an HMAC-SHA256 digest
  keyed by `ADMIN_OTP_SECRET`; each challenge is single-use and capped
  at `ADMIN_OTP_MAX_ATTEMPTS` guesses.
- `/auth/login/start` and `/auth/login/verify` return the same generic
  error regardless of whether the username exists, so the endpoint can't
  be used to enumerate admins.
- Basic in-process rate limiting on both login endpoints
  (`app/core/rate_limit.py`). This is a single-process, in-memory
  limiter — good enough for a two-admin system running as one process,
  but **not** sufficient if this service is ever scaled to multiple
  instances; swap in a shared (e.g. Redis-backed) limiter first if that
  ever happens.
- CORS is restricted to `FRONTEND_ORIGIN`.
- The session cookie is only `Secure` when `APP_ENV=production` -- check
  this is actually set before going live, it's easy to miss since
  `.env.example` defaults it to `development` for local checkouts.
- No string-concatenated SQL anywhere (SQLAlchemy ORM/Core only), no
  shell execution of unsanitized input (see the system layer above).
- Every request gets a correlation id (`X-Request-ID` header), also
  attached to its audit log entries.
- `services.system_name` is validated against a safe identifier pattern
  before it is ever turned into a unit name or passed to
  `CommandExecutor` -- defense in depth on top of the fact that
  `CommandExecutor` never uses a shell in the first place, so there is
  no injection surface even for a value that failed that check.
- `service.start`/`service.stop` refuse to run against a unit that
  `service.status` reports as not installed (`LoadState=not-found`),
  so a bad or stale `system_name` can't reach `sudo` at all.
- `/services/{id}/start` and `/services/{id}/stop` require the same
  session + CSRF header as `/auth/logout`; both outcomes (success or a
  non-zero exit code) are audit-logged with the resolved unit name,
  exit code, and duration.
- `env_file_helper.py` never accepts a filesystem path -- only
  `system_name`, validated against the same safe-identifier pattern,
  confined to a `PROJECT_ROOT` constant hardcoded in the script itself
  (not passed by the caller). The sudoers grant only ever invokes that
  one script with `read`/`write`; there is no `sudo cat`/`sudo tee`
  anywhere, which would otherwise let the grant be used to read or
  overwrite any root-owned file, not just a `services` `.env`.
- `CommandExecutor` gives a child **no** stdin (`DEVNULL`) unless a spec
  explicitly provides one, rather than inheriting the server's own --
  `env.write` is the only action that ever supplies stdin content
  (the new file, never logged).
- `env.write` rejects a key that isn't a valid environment variable name
  or a value containing a newline/carriage-return/NUL before it ever
  reaches the helper script; the audit trail for a successful write
  records which key *names* were added/removed/changed, never values.
- The `.env` editor UI masks values by default (password-style inputs,
  opt-in "show values" toggle) and confirms before saving if the edit
  would remove any variable.
- `instance_files_helper.py`, `nginx_config_helper.py`, and
  `systemd_unit_helper.py` all follow `env_file_helper.py`'s pattern: no
  filesystem path ever accepted from the caller, every path built from a
  constant hardcoded in the script itself, `system_name` (where
  applicable) validated against the same safe-identifier pattern.
- Uploaded zip archives are extracted in-process with Python's
  `zipfile` -- never via a subprocess (`unzip`), so a zip's contents
  have no command-injection surface at all. Extraction validates every
  member's path (rejects `..`/absolute paths/symlinks) and enforces a
  total-size and entry-count cap *before* extracting anything, so a
  crafted archive can't traverse outside the target directory or exhaust
  disk as a zip bomb.
- `npm install`/`npm run build` run only in adminka's own unprivileged
  staging directory, never as root and never inside the root-owned
  instance tree (see "npm install privilege model" above); the fixed
  credential-provisioning script is likewise unprivileged.
- The nginx config is never left in a state that failed `nginx -t`, even
  transiently -- an invalid write is rolled back to the previous content
  before the request returns an error (see "nginx: never a partial
  edit" above).
- `service.enable_now` and `nginx.reload` are new sudo-elevated actions;
  `nginx.reload` and `nginx_config_helper.py read`/`write` take **no
  parameters at all** -- the safest possible shape of sudo grant, since
  there is nothing for a caller to influence.
- `database_name`/`database_user` (the new-service wizard's DB step)
  can't be parameterized as SQL identifiers the way a value can, so they
  are validated against a strict allowlist pattern *before* ever being
  interpolated into DDL text -- see
  `app/provisioning/database_provisioning.py`. The generated password is
  never logged or audited (only the database/user names are); this is
  the one privileged capability in this app that isn't mediated by a
  narrowly-scoped OS-level helper, since it's SQL-level, not
  filesystem/systemd/nginx -- see the MySQL grant note above.

## Tests

```bash
cd backend
.venv/bin/pytest
```

Covers password hashing, OTP challenge lifecycle (success, wrong code,
expiry, exhausted attempts, reuse-after-success), sessions (creation,
expiry, revocation, logout), the full HTTP auth flow (with the Telegram
client mocked — no network calls), audit log writing (including that
sensitive keys are stripped), the `CommandExecutor` (stdout, stderr,
exit code, timeout, output truncation, `cwd`/env handling -- these only
ever run the test's own Python interpreter, never a real administrative
command), and the service-control layer end to end: `unit_name_for`
validation, `service.status`/`start`/`stop` CommandSpec construction
(status never uses sudo, start/stop always do), not-found handling, and
the full HTTP flow including auth/CSRF enforcement and audit logging;
and the `.env` editor layer: parsing/rendering round-trips (comments and
blank lines preserved), the add/change/remove diff, key/value
validation, `EnvFileControlService` (missing file vs. missing instance
directory), the `env.read`/`env.write` CommandSpec construction, and the
full HTTP flow (including that a successful read/write is audit-logged
with key names only, never values).

The new-service wizard is covered at every layer: domain/punycode
building and validation, DB-row creation and uniqueness checks, zip
upload validation (path traversal, symlinks, size/entry-count limits,
missing `frontend`/`backend`, safe retry), the credential-provisioning
script's argv/env construction and output parsing, `npm install`/`build`
invocation and `dist/` promotion, nginx template rendering and the
idempotent-insert-vs-replace logic in isolation, the nginx
read/write/validate/**rollback-on-failure**/reload orchestration in
isolation (`NginxControlService`), and finally the complete HTTP flow
end to end (`test_provisioning_api.py`) -- create, dirs, upload, env,
frontend build, nginx, systemd, `GET .../provision/status` after each
step, CSRF/auth enforcement, and audit log content, including that a
rejected nginx config really does get rolled back and that duplicate
`url`/`system_name`/`bot_entry_key` are rejected with 409.

All of the above (including this new layer) run against a single
`FakeSystemctl` test double (`tests/conftest.py`) that answers
`systemctl show`/`start`/`stop`/`enable`, `nginx -t`/`reload`, `ss
-Hltn`, the credential-provisioning script, `npm`, and all four
privileged helpers' `read`/`write`/`create_tree`/`install_*` from
in-memory state (mirroring real directories under a temp
`INSTANCES_ROOT_DIR` where the wizard's own status checks need to see
them) -- so none of it needs a real systemd, sudo, nginx, or root-owned
files on the machine running the tests. The four helper scripts
themselves (`backend/scripts/*_helper.py`) were verified manually
end-to-end (path confinement, atomic writes, ownership/mode
preservation, `daemon-reload`) rather than via the test suite, since
they're standalone privileged scripts outside the app's own import path.
