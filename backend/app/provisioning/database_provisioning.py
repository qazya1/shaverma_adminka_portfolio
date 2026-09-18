"""New sub-step of the new-service wizard's "generate .env" step:
creates a MySQL database and a dedicated user for the new service on
the same MySQL server adminka's own `SYSTEM_DATABASE_URL` connection
lives on, and returns a freshly generated password for env_template to
embed into DATABASE_URL.

Runs as whatever MySQL user `SYSTEM_DATABASE_URL` authenticates as --
that user needs `CREATE`, `CREATE USER`, and `GRANT OPTION` privileges
for this to work. That is a real widening from what adminka's own
read/write of its `admin_*` tables and shaverma's `services` table would
otherwise need -- see the README's "New-service provisioning wizard"
section, which documents granting it explicitly (the alternative -- a
second, narrowly-scoped MySQL credential used only for this action --
was considered and deliberately not taken).

CREATE DATABASE/CREATE USER/GRANT are DDL, so none of this is
transactional in MySQL regardless (each statement auto-commits) -- same
"each step independently retryable, no all-or-nothing rollback" posture
as every other wizard step. A retry always issues a *fresh* password
(via ALTER USER ... IDENTIFIED BY RANDOM PASSWORD if the user already
exists) rather than silently no-op'ing on an existing user -- MySQL
never lets a generated password be recovered after the fact, so a retry
that skipped regenerating it would leave DATABASE_URL permanently wrong
if the original CREATE USER's result was ever lost (e.g. because a
later step in the same request failed before it reached the .env file).

`db_name`/`db_user` can never be parameterized as SQL identifiers (bind
parameters only ever substitute values, not identifiers), so both are
validated against a strict allowlist pattern *before* ever being
interpolated into SQL text -- that check is the only real defense here;
backtick/quote-wrapping alone would not be safe for a value that failed
it.

Caveat: the exact result-set shape of `... IDENTIFIED BY RANDOM
PASSWORD` (MySQL 8.0.18+; not available on MariaDB or older MySQL) is
read defensively below (by column name, not position), but was not
possible to verify against a live server while building this -- smoke-
test the "generate .env" step once against a real database before
relying on it broadly.
"""

import re

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

# MySQL's own identifier limits: 64 bytes for a database name, 32
# characters for a user name (the historical, still-common default for
# mysql.user.User; some servers raise this via a server variable, but 32
# is always safe). Starting with a letter avoids any ambiguity with a
# purely-numeric identifier.
_DB_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_DB_USER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")

_GRANT_PRIVILEGES = "SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES"

# MySQL's ER_CANNOT_USER -- what CREATE USER fails with when the name
# already exists.
_ER_CANNOT_USER = 1396


class InvalidDatabaseIdentifierError(ValueError):
    """Raised when a database or user name doesn't match the strict
    identifier pattern required before it's safe to interpolate into
    DDL text."""


class DatabaseProvisioningError(RuntimeError):
    """Raised for any MySQL-side failure -- most commonly, the
    connection adminka uses for SYSTEM_DATABASE_URL not actually having
    CREATE/CREATE USER/GRANT OPTION. Never includes the password."""


def validate_database_name(name: str) -> None:
    if not _DB_NAME_RE.fullmatch(name):
        raise InvalidDatabaseIdentifierError(f"database name must match {_DB_NAME_RE.pattern!r}: {name!r}")


def validate_database_user(name: str) -> None:
    if not _DB_USER_RE.fullmatch(name):
        raise InvalidDatabaseIdentifierError(f"database user must match {_DB_USER_RE.pattern!r}: {name!r}")


def _generated_password(row) -> str:
    mapping = row._mapping  # noqa: SLF001 -- SQLAlchemy's own documented Row API
    key = next((k for k in mapping if "password" in str(k).lower()), None)
    if key is None:
        raise DatabaseProvisioningError(
            "MySQL did not return a generated password column -- "
            "is IDENTIFIED BY RANDOM PASSWORD supported on this server (MySQL 8.0.18+)?"
        )
    return mapping[key]


def provision_service_database(engine: Engine, db_name: str, db_user: str) -> str:
    """Creates `db_name` (if it doesn't already exist) and
    `db_user`@localhost (creating it, or rotating its password if it
    already exists), grants the fixed privilege set on `db_name`.* to
    it, and returns the freshly generated password.

    Callers must validate `db_name`/`db_user` first (validate_database_name/
    validate_database_user) -- this function trusts them to already be
    safe to interpolate into SQL text.
    """

    try:
        with engine.begin() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}`"))

            try:
                result = conn.execute(text(f"CREATE USER '{db_user}'@'localhost' IDENTIFIED BY RANDOM PASSWORD"))
            except DBAPIError as exc:
                if getattr(exc.orig, "args", [None])[0] != _ER_CANNOT_USER:
                    raise
                # Already exists (e.g. a retry after a later step failed
                # before the password reached .env) -- rotate it rather
                # than silently keeping whatever password was generated,
                # and lost, last time.
                result = conn.execute(text(f"ALTER USER '{db_user}'@'localhost' IDENTIFIED BY RANDOM PASSWORD"))

            row = result.fetchone()
            if row is None:
                raise DatabaseProvisioningError("MySQL did not return a generated password row")
            password = _generated_password(row)

            conn.execute(text(f"GRANT {_GRANT_PRIVILEGES} ON `{db_name}`.* TO '{db_user}'@'localhost'"))
            conn.execute(text("FLUSH PRIVILEGES"))
    except DBAPIError as exc:
        raise DatabaseProvisioningError(f"MySQL database/user provisioning failed for {db_name!r}/{db_user!r}") from exc

    return password
