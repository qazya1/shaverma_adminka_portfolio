from pydantic import BaseModel


class ServiceStatusPublic(BaseModel):
    """Live systemd state, as of the moment the request was handled."""

    exists: bool
    load_state: str | None = None
    active_state: str | None = None
    sub_state: str | None = None
    unit_file_state: str | None = None


class ServiceListItem(BaseModel):
    id: int
    name: str
    system_name: str
    # Null when system_name doesn't pass unit_name_for()'s safe-identifier
    # check -- shaverma's own services.system_name has no format
    # constraint, so a stray value (not something adminka itself ever
    # writes) is possible; the row still shows up, just without a unit
    # name, rather than the whole list failing.
    unit_name: str | None
    # The shaverma-side business "enabled" flag (services.is_active) --
    # the single source of truth the list view renders from, without
    # touching systemd at all. Kept in sync by the admin panel itself:
    # start/stop update it to match the action just taken, and
    # "check status" updates it to match reality if the two disagree.
    # It can still lag reality between those, e.g. if the unit was
    # started/stopped outside the panel (directly over SSH).
    is_active: bool
    # Live systemd state as of the moment the request was handled --
    # null from the plain list (never checked there), populated by
    # start/stop/check-status, which all touch systemd directly.
    status: ServiceStatusPublic | None = None


class ServiceUpdateResponse(BaseModel):
    """Result of replacing an already-deployed service's backend and/or
    frontend files (app.api.services.update_service_files)."""

    service: ServiceListItem
    backend_updated: bool
    frontend_updated: bool
    # False either because the update was frontend-only (no restart
    # needed -- nginx serves the new static files directly, no process
    # to reload) or because a backend update's restart attempt itself
    # failed -- the file replacement can still have fully succeeded
    # either way, see the module docstring on why this never turns into
    # a failed HTTP response by itself.
    restarted: bool
