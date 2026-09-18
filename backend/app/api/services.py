"""Endpoints for listing and controlling shaverma backend systemd
services, and for reading/writing each service's root-owned .env file.

Both are real system-modifying capabilities the admin panel exposes:
starting/stopping a systemd unit, and rewriting a config file outside
this process's own ownership. Every state-changing call here is
authenticated, CSRF-protected, and audit-logged exactly like the auth
endpoints; nothing here accepts a raw command, unit string, or
filesystem path from the client -- both are always derived server-side
from services.system_name.

`GET /services` deliberately does *not* touch systemd at all -- it just
returns each row's stored `is_active`, so listing stays a plain DB read
even with many services onboarded. The live systemd state is only ever
checked on demand: by `start`/`stop` (which need it to act), and by
`POST /{id}/check-status`, a read-only-in-intent action the admin
triggers by hand to confirm reality and, if it disagrees with the
stored flag, correct `is_active` to match.

`POST /{id}/update` is the third: replacing an already-deployed
service's backend and/or built frontend from a freshly uploaded zip,
reusing the exact same instance.install_backend/instance.install_dist
privileged actions (full rm -rf-then-replace, see
instance_files_helper.py) the new-service wizard's own upload/frontend
steps already use -- so this needs no sudoers grant beyond what
provisioning already requires, restart included (see
ServiceControlService.restart).
"""

import logging
import os
import shutil
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.audit import service as audit_service
from app.auth.dependencies import get_current_admin, require_csrf
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.external.models import ManagedService
from app.models.admin import AdminUser
from app.provisioning import env_template, frontend_build
from app.provisioning.upload import InvalidUploadError, extract_upload
from app.schemas.env_file import EnvEntry, ServiceEnvResponse, ServiceEnvUpdateRequest
from app.schemas.services import ServiceListItem, ServiceStatusPublic, ServiceUpdateResponse
from app.system.env_file_control import (
    EnvFileControlService,
    EnvLine,
    InstanceDirectoryNotFoundError,
    InvalidEnvKeyError,
    InvalidEnvValueError,
    entries_from_lines,
    validate_system_name,
)
from app.system.exceptions import InvalidSystemNameError, ServiceNotFoundError, SystemExecutionError
from app.system.executor import CommandExecutor
from app.system.registry import registry as system_registry
from app.system.service_control import ServiceControlService, UnitStatus, unit_name_for

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services", tags=["services"])


def _status_to_schema(unit_status: UnitStatus) -> ServiceStatusPublic:
    return ServiceStatusPublic(
        exists=unit_status.exists,
        load_state=unit_status.load_state,
        active_state=unit_status.active_state,
        sub_state=unit_status.sub_state,
        unit_file_state=unit_status.unit_file_state,
    )


def _to_item(row: ManagedService, unit_status: UnitStatus | None) -> ServiceListItem:
    assert row.system_name is not None
    try:
        unit_name = unit_name_for(row.system_name)
    except InvalidSystemNameError:
        # shaverma's own services.system_name has no format constraint of
        # its own -- a stray value there (not something adminka ever
        # wrote) must not take down the whole list. Surface the row with
        # unit_name unset rather than 500ing every other service too.
        unit_name = None
    return ServiceListItem(
        id=row.id,
        name=row.name,
        system_name=row.system_name,
        unit_name=unit_name,
        is_active=row.is_active,
        status=_status_to_schema(unit_status) if unit_status is not None else None,
    )


def _managed_rows(db: Session) -> list[ManagedService]:
    return (
        db.query(ManagedService)
        .filter(ManagedService.system_name.is_not(None))
        .order_by(ManagedService.name)
        .all()
    )


def _get_row_or_404(db: Session, service_id: int) -> ManagedService:
    row = db.get(ManagedService, service_id)
    if row is None or not row.system_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return row


def _request_context(request: Request) -> tuple[str | None, str | None]:
    request_id = getattr(request.state, "request_id", None)
    ip = request.client.host if request.client else None
    return request_id, ip


@router.get("", response_model=list[ServiceListItem])
async def list_services(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[ServiceListItem]:
    # No systemd calls here on purpose -- see the module docstring.
    # `status` comes back null; the panel colors each row from
    # `is_active` alone and the admin confirms it against reality with
    # "check status" (or start/stop) when they want to.
    return [_to_item(row, None) for row in _managed_rows(db)]


async def _control_service(service_id: int, verb: str, request: Request, db: Session, admin: AdminUser) -> ServiceListItem:
    row = _get_row_or_404(db, service_id)
    request_id, ip = _request_context(request)

    try:
        unit_name = unit_name_for(row.system_name)
    except InvalidSystemNameError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="services.system_name is not a valid identifier",
        ) from None

    control = ServiceControlService(system_registry)

    try:
        if verb == "start":
            new_status, result = await control.start(row.system_name)
        else:
            new_status, result = await control.stop(row.system_name)
    except ServiceNotFoundError:
        audit_service.record_event(
            db,
            action=f"service.{verb}",
            status="failure",
            admin_id=admin.id,
            target=unit_name,
            parameters={"reason": "unit_not_found"},
            request_id=request_id,
            request_ip=ip,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="systemd unit does not exist") from None

    succeeded = result.exit_code == 0 and not result.timed_out
    if succeeded:
        # Single source of truth: is_active is what the admin panel told
        # systemd to do, kept in sync right here instead of drifting as
        # an independent "business" flag that only shaverma itself sets.
        row.is_active = verb == "start"

    audit_service.record_event(
        db,
        action=f"service.{verb}",
        status="success" if succeeded else "failure",
        admin_id=admin.id,
        target=unit_name,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        request_id=request_id,
        request_ip=ip,
    )
    db.commit()

    return _to_item(row, new_status)


@router.post("/{service_id}/start", response_model=ServiceListItem)
async def start_service(
    service_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),
) -> ServiceListItem:
    return await _control_service(service_id, "start", request, db, admin)


@router.post("/{service_id}/stop", response_model=ServiceListItem)
async def stop_service(
    service_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),
) -> ServiceListItem:
    return await _control_service(service_id, "stop", request, db, admin)


@router.post("/{service_id}/check-status", response_model=ServiceListItem)
async def check_service_status(
    service_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),
) -> ServiceListItem:
    """Read-only towards systemd, but writes to our own DB when it
    disagrees with what's actually running -- the only place besides
    start/stop that `is_active` is ever changed."""

    row = _get_row_or_404(db, service_id)
    request_id, ip = _request_context(request)

    try:
        unit_name = unit_name_for(row.system_name)
    except InvalidSystemNameError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="services.system_name is not a valid identifier",
        ) from None

    control = ServiceControlService(system_registry)
    unit_status = await control.get_status(row.system_name)
    live_active = unit_status.exists and unit_status.active_state == "active"
    corrected = row.is_active != live_active
    if corrected:
        row.is_active = live_active

    audit_service.record_event(
        db,
        action="service.check_status",
        status="success",
        admin_id=admin.id,
        target=unit_name,
        parameters={"corrected": corrected, "active_state": unit_status.active_state},
        request_id=request_id,
        request_ip=ip,
    )
    db.commit()

    return _to_item(row, unit_status)


# --- file update (already-deployed service) -----------------------------


def _audit_step(
    db: Session,
    admin: AdminUser,
    action_name: str,
    system_name: str,
    success: bool,
    request_id: str | None,
    ip: str | None,
    parameters: dict | None = None,
) -> None:
    audit_service.record_event(
        db,
        action=action_name,
        status="success" if success else "failure",
        admin_id=admin.id,
        target=system_name,
        parameters=parameters,
        request_id=request_id,
        request_ip=ip,
    )


@router.post("/{service_id}/update", response_model=ServiceUpdateResponse)
async def update_service_files(
    service_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
    _csrf: None = Depends(require_csrf),
) -> ServiceUpdateResponse:
    """Replaces an already-deployed service's backend and/or frontend
    files from an uploaded zip -- the rm -rf-then-move an admin would
    otherwise do by hand over SSH, done here through the same
    instance.install_backend/instance.install_dist privileged actions
    the new-service wizard's own upload/frontend steps already use: both
    fully replace the target directory's contents (see
    instance_files_helper.py), so this needs no sudoers grant beyond what
    provisioning already requires. The zip may contain a top-level
    `backend/`, `frontend/` (pre-build -- rebuilt here with `npm install`
    + `npm run build`, same as the wizard, using the service's current
    .env for the VITE_ build-time vars), or both; whichever is present
    gets replaced, the rest of the deployment (env, nginx, systemd unit)
    is left untouched.

    A backend update restarts the service afterwards (stop, then start
    -- see ServiceControlService.restart for why not a single `systemctl
    restart`) so the new code actually takes effect; a frontend-only
    update never touches systemd at all -- nginx serves the new static
    files on the very next request, no reload needed. The restart is
    best-effort: if it fails, or the unit doesn't even exist, the file
    replacement has still fully succeeded -- reported via
    `restarted: false` rather than failing the whole request, the same
    "the request itself succeeded; the command failed" spirit as
    start/stop above.
    """

    row = _get_row_or_404(db, service_id)
    request_id, ip = _request_context(request)
    system_name = row.system_name

    try:
        validate_system_name(system_name)
    except InvalidSystemNameError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="services.system_name is not a valid identifier",
        ) from None

    staging_dir = os.path.join(settings.instance_staging_dir, system_name)
    os.makedirs(settings.instance_staging_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(dir=settings.instance_staging_dir, suffix=".zip", delete=False) as tmp:
        tmp_path = tmp.name
        shutil.copyfileobj(file.file, tmp)

    try:
        try:
            # required_top_level_dirs=() -- unlike the wizard's own
            # upload step, either folder alone is accepted here; the
            # "must have at least one" rule still applies underneath.
            extracted = extract_upload(tmp_path, staging_dir, required_top_level_dirs=())
        except InvalidUploadError as exc:
            _audit_step(db, admin, "service.update_upload", system_name, False, request_id, ip, {"reason": str(exc)})
            db.commit()
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    has_backend = os.path.isdir(extracted.backend_dir)
    has_frontend = os.path.isdir(extracted.frontend_dir)
    _audit_step(
        db,
        admin,
        "service.update_upload",
        system_name,
        True,
        request_id,
        ip,
        {"has_backend": has_backend, "has_frontend": has_frontend},
    )
    db.commit()

    if has_backend:
        action = system_registry.get("instance.install_backend")
        result = await action.run(system_name=system_name)
        _audit_step(db, admin, "service.update_install_backend", system_name, result.exit_code == 0, request_id, ip)
        db.commit()
        if result.exit_code != 0:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to install updated backend")

    if has_frontend:
        env_control = EnvFileControlService(system_registry)
        current_lines = await env_control.read(system_name)
        frontend_env_content = env_template.extract_frontend_vars(current_lines)
        telegram_web_app_local_sdk_enabled = env_template.extract_telegram_web_app_local_sdk_enabled(current_lines)

        executor = CommandExecutor()
        try:
            await frontend_build.build_frontend(
                executor,
                settings.node_bin_dir,
                extracted.frontend_dir,
                frontend_env_content,
                settings.system_command_timeout_seconds * 10,  # npm install/build legitimately takes longer
                telegram_web_app_js_path=settings.telegram_web_app_js_path,
                telegram_web_app_local_sdk_enabled=telegram_web_app_local_sdk_enabled,
            )
            frontend_build.promote_dist(system_name, settings.instance_staging_dir)
        except frontend_build.FrontendBuildError as exc:
            _audit_step(
                db, admin, "service.update_build_frontend", system_name, False, request_id, ip, {"reason": str(exc)}
            )
            db.commit()
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from None

        action = system_registry.get("instance.install_dist")
        result = await action.run(system_name=system_name)
        _audit_step(db, admin, "service.update_install_dist", system_name, result.exit_code == 0, request_id, ip)
        db.commit()
        if result.exit_code != 0:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to install built frontend")

    # Everything staged for this update has now been moved into the
    # privileged tree (or the update failed and returned already) --
    # nothing left here is needed, same "clean slate for next time"
    # philosophy as the wizard's own post-install_dist cleanup.
    frontend_build.cleanup_staging(system_name, settings.instance_staging_dir)

    restarted = False
    unit_status: UnitStatus | None = None
    if has_backend:
        control = ServiceControlService(system_registry)
        try:
            unit_status, restart_result = await control.restart(system_name)
        except ServiceNotFoundError:
            _audit_step(
                db, admin, "service.update_restart", system_name, False, request_id, ip, {"reason": "unit_not_found"}
            )
            db.commit()
        else:
            restarted = restart_result.exit_code == 0 and not restart_result.timed_out
            if restarted:
                # Single source of truth, same as start/stop above.
                row.is_active = True
            _audit_step(db, admin, "service.update_restart", system_name, restarted, request_id, ip)
            db.commit()

    return ServiceUpdateResponse(
        service=_to_item(row, unit_status),
        backend_updated=has_backend,
        frontend_updated=has_frontend,
        restarted=restarted,
    )


# --- .env editor -------------------------------------------------------


def _env_path_hint(system_name: str, settings: Settings) -> str | None:
    """Display-only: the resolved .env path, if INSTANCES_ROOT_DIR is
    configured. Never used to decide what gets read/written -- that is
    entirely up to env_file_helper.py's own PROJECT_ROOT constant."""

    if not settings.instances_root_dir:
        return None
    return f"{settings.instances_root_dir.rstrip('/')}/{system_name}/.env"


def _entries_to_schema(lines: list[EnvLine]) -> list[EnvEntry]:
    return [EnvEntry(key=key, value=value) for key, value in entries_from_lines(lines)]


@router.get("/{service_id}/env", response_model=ServiceEnvResponse)
async def get_service_env(
    service_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
) -> ServiceEnvResponse:
    row = _get_row_or_404(db, service_id)
    request_id, ip = _request_context(request)
    env_control = EnvFileControlService(system_registry)

    try:
        lines = await env_control.read(row.system_name)
    except InvalidSystemNameError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="services.system_name is not a valid identifier",
        ) from None
    except SystemExecutionError:
        logger.exception("env.read failed for system_name=%s", row.system_name)
        audit_service.record_event(
            db,
            action="env.read",
            status="failure",
            admin_id=admin.id,
            target=row.system_name,
            request_id=request_id,
            request_ip=ip,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to read environment file") from None

    # Reading a service's .env exposes whatever secrets live in it --
    # audited on success too, not just on failure, unlike a plain
    # systemd status read.
    audit_service.record_event(
        db,
        action="env.read",
        status="success",
        admin_id=admin.id,
        target=row.system_name,
        request_id=request_id,
        request_ip=ip,
    )
    db.commit()

    return ServiceEnvResponse(
        service_id=row.id,
        name=row.name,
        system_name=row.system_name,
        path=_env_path_hint(row.system_name, settings),
        entries=_entries_to_schema(lines),
    )


@router.post("/{service_id}/env", response_model=ServiceEnvResponse)
async def update_service_env(
    service_id: int,
    payload: ServiceEnvUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
    _csrf: None = Depends(require_csrf),
) -> ServiceEnvResponse:
    row = _get_row_or_404(db, service_id)
    request_id, ip = _request_context(request)
    desired = [(entry.key, entry.value) for entry in payload.entries]

    env_control = EnvFileControlService(system_registry)

    try:
        diff = await env_control.write(row.system_name, desired)
    except InvalidSystemNameError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="services.system_name is not a valid identifier",
        ) from None
    except (InvalidEnvKeyError, InvalidEnvValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except InstanceDirectoryNotFoundError:
        audit_service.record_event(
            db,
            action="env.write",
            status="failure",
            admin_id=admin.id,
            target=row.system_name,
            parameters={"reason": "instance_directory_not_found"},
            request_id=request_id,
            request_ip=ip,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Instance directory does not exist") from None
    except SystemExecutionError:
        logger.exception("env.write failed for system_name=%s", row.system_name)
        audit_service.record_event(
            db,
            action="env.write",
            status="failure",
            admin_id=admin.id,
            target=row.system_name,
            request_id=request_id,
            request_ip=ip,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to write environment file") from None

    # Key names only -- values (potentially secrets) never reach the
    # audit log, see app/audit/service.py's own defensive filtering too.
    audit_service.record_event(
        db,
        action="env.write",
        status="success",
        admin_id=admin.id,
        target=row.system_name,
        parameters={
            "added": sorted(diff.added),
            "removed": sorted(diff.removed),
            "changed": sorted(diff.changed),
        },
        request_id=request_id,
        request_ip=ip,
    )
    db.commit()

    return ServiceEnvResponse(
        service_id=row.id,
        name=row.name,
        system_name=row.system_name,
        path=_env_path_hint(row.system_name, settings),
        entries=_entries_to_schema(diff.lines),
    )
