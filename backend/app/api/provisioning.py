"""New-service provisioning wizard: one endpoint per step (see
app/provisioning/__init__.py for why this isn't one all-or-nothing
transaction). Every step is authenticated, CSRF-protected, and
audit-logged; a GET status endpoint reports each step's live state by
checking reality (filesystem, .env contents, nginx config, systemd) --
never a cached "done" flag -- so any step is safe to just call again.
"""

import logging
import os
import shutil
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from app.audit import service as audit_service
from app.auth.dependencies import get_current_admin, require_csrf
from app.core.config import Settings, get_settings
from app.core.database import engine as system_db_engine
from app.core.database import get_db
from app.core.security import generate_secure_token
from app.external.models import ManagedService
from app.models.admin import AdminUser
from app.provisioning import database_provisioning, env_template, frontend_build, port_allocation
from app.provisioning.credentials_script import CredentialProvisioningError, provision_gateway_credentials
from app.provisioning.database_provisioning import DatabaseProvisioningError, InvalidDatabaseIdentifierError
from app.provisioning.domain import InvalidDomainLabelError, domain_from_url
from app.provisioning.nginx_template import has_block, render_block
from app.provisioning.service_creation import (
    DuplicateFieldError,
    InvalidSystemNameError,
    NewServiceInput,
    create_service,
)
from app.provisioning.systemd_template import render_unit
from app.provisioning.upload import InvalidUploadError, extract_upload
from app.schemas.provisioning import (
    NewServiceRequest,
    NewServiceResponse,
    ProvisionEnvRequest,
    ProvisionEnvResponse,
    ProvisionNginxResponse,
    ProvisionStatusResponse,
    ProvisionStepStatus,
    ProvisionSystemdRequest,
)
from app.schemas.env_file import EnvEntry
from app.system.env_file_control import EnvFileControlService, InstanceDirectoryNotFoundError, entries_from_lines
from app.system.env_file_control import validate_system_name as _validate_system_name_or_raise
from app.system.exceptions import InvalidSystemNameError as SystemInvalidSystemNameError
from app.system.exceptions import SystemExecutionError
from app.system.executor import CommandExecutor
from app.system.nginx_control import NginxConfigInvalidError, NginxControlService
from app.system.registry import registry as system_registry
from app.system.service_control import ServiceControlService, unit_name_for

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services", tags=["provisioning"])


def _request_context(request: Request) -> tuple[str | None, str | None]:
    request_id = getattr(request.state, "request_id", None)
    ip = request.client.host if request.client else None
    return request_id, ip


def _get_row_or_404(db: Session, service_id: int) -> ManagedService:
    row = db.get(ManagedService, service_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return row


def _get_row_with_system_name_or_404(db: Session, service_id: int) -> ManagedService:
    row = _get_row_or_404(db, service_id)
    if not row.system_name:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Service has no system_name configured")
    try:
        _validate_system_name_or_raise(row.system_name)
    except SystemInvalidSystemNameError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return row


# --- Step 1: create the DB record --------------------------------------


@router.post("", response_model=NewServiceResponse, status_code=status.HTTP_201_CREATED)
def create_new_service(
    payload: NewServiceRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
    _csrf: None = Depends(require_csrf),
) -> NewServiceResponse:
    request_id, ip = _request_context(request)
    data = NewServiceInput(
        label=payload.label,
        name=payload.name,
        system_name=payload.system_name,
        is_active=payload.is_active,
        supported_channels=payload.channels,
        bot_entry_key=payload.bot_entry_key,
        client_bot_entry_key=payload.client_bot_entry_key,
    )

    try:
        row = create_service(db, data, settings.service_domain_zone)
    except DuplicateFieldError as exc:
        # Must be checked before the generic ValueError branch below --
        # DuplicateFieldError is itself a ValueError subclass.
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except (InvalidDomainLabelError, InvalidSystemNameError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None

    audit_service.record_event(
        db,
        action="service.create",
        status="success",
        admin_id=admin.id,
        target=row.system_name,
        parameters={"service_id": row.id},
        request_id=request_id,
        request_ip=ip,
    )
    db.commit()

    return NewServiceResponse(
        id=row.id,
        name=row.name,
        system_name=row.system_name,
        url=row.url,
        backend_base_url=row.backend_base_url,
        is_active=row.is_active,
    )


# --- Step 2: instance directory tree ------------------------------------


@router.post("/{service_id}/provision/dirs", status_code=status.HTTP_204_NO_CONTENT)
async def provision_dirs(
    service_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),
) -> None:
    row = _get_row_with_system_name_or_404(db, service_id)
    request_id, ip = _request_context(request)

    action = system_registry.get("instance.create_tree")
    result = await action.run(system_name=row.system_name)

    _audit_step(db, admin, "instance.create_tree", row.system_name, result.exit_code == 0, request_id, ip)
    db.commit()

    if result.exit_code != 0:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to create instance directory")


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


# --- Step 3: upload + place backend source ------------------------------


@router.post("/{service_id}/provision/upload", status_code=status.HTTP_204_NO_CONTENT)
async def provision_upload(
    service_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
    _csrf: None = Depends(require_csrf),
) -> None:
    row = _get_row_with_system_name_or_404(db, service_id)
    request_id, ip = _request_context(request)
    system_name = row.system_name

    staging_dir = os.path.join(settings.instance_staging_dir, system_name)
    os.makedirs(settings.instance_staging_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(dir=settings.instance_staging_dir, suffix=".zip", delete=False) as tmp:
        tmp_path = tmp.name
        shutil.copyfileobj(file.file, tmp)

    try:
        try:
            extract_upload(tmp_path, staging_dir)
        except InvalidUploadError as exc:
            _audit_step(db, admin, "instance.upload", system_name, False, request_id, ip, {"reason": str(exc)})
            db.commit()
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    action = system_registry.get("instance.install_backend")
    result = await action.run(system_name=system_name)

    _audit_step(db, admin, "instance.install_backend", system_name, result.exit_code == 0, request_id, ip)
    db.commit()

    if result.exit_code != 0:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to install backend source")


# --- Step 4: bot credentials + generate .env ----------------------------


@router.post("/{service_id}/provision/env", response_model=ProvisionEnvResponse)
async def provision_env(
    service_id: int,
    payload: ProvisionEnvRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
    _csrf: None = Depends(require_csrf),
) -> ProvisionEnvResponse:
    row = _get_row_with_system_name_or_404(db, service_id)
    request_id, ip = _request_context(request)
    system_name = row.system_name

    try:
        database_provisioning.validate_database_name(payload.database_name)
        database_provisioning.validate_database_user(payload.database_user)
    except InvalidDatabaseIdentifierError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None

    db_audit_params = {"database_name": payload.database_name, "database_user": payload.database_user}
    try:
        database_password = database_provisioning.provision_service_database(
            system_db_engine, payload.database_name, payload.database_user
        )
    except DatabaseProvisioningError as exc:
        _audit_step(db, admin, "service.provision_database", system_name, False, request_id, ip, db_audit_params)
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from None

    _audit_step(db, admin, "service.provision_database", system_name, True, request_id, ip, db_audit_params)

    # Same physical MySQL server SYSTEM_DATABASE_URL already connects to
    # -- just a different database/user, freshly created above.
    database_url = URL.create(
        drivername="mysql+pymysql",
        username=payload.database_user,
        password=database_password,
        host=system_db_engine.url.host,
        port=system_db_engine.url.port or 3306,
        database=payload.database_name,
    ).render_as_string(hide_password=False)

    executor = CommandExecutor()
    try:
        gateway_api_key, gateway_signing_secret = await provision_gateway_credentials(
            executor,
            settings.service_venv_dir,
            settings.bot_project_dir,
            service_id,
            settings.system_command_timeout_seconds,
        )
    except CredentialProvisioningError as exc:
        _audit_step(db, admin, "service.provision_credentials", system_name, False, request_id, ip)
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from None

    _audit_step(db, admin, "service.provision_credentials", system_name, True, request_id, ip)

    lines = env_template.render_new_service_env(
        system_name=system_name,
        display_name=row.name,
        frontend_url=row.url,
        backend_url=row.backend_base_url or "",
        telegram_bot_token=settings.service_telegram_bot_token,
        telegram_bot_username=settings.service_telegram_bot_username,
        max_bot_token=settings.service_max_bot_token,
        max_entry_secret=settings.service_max_entry_secret,
        max_bot_deep_link_id=settings.service_max_bot_deep_link_id,
        system_gateway_base_url=settings.system_gateway_base_url,
        gateway_api_key=gateway_api_key,
        gateway_signing_secret=gateway_signing_secret,
        session_secret=generate_secure_token(32),
        database_url=database_url,
        yookassa_recurring_payments_enabled=payload.yookassa_recurring_payments_enabled,
        yookassa_shop_id=payload.yookassa_shop_id or "",
        yookassa_secret_key=payload.yookassa_secret_key or "",
        telegram_web_app_local_sdk_enabled=payload.telegram_web_app_local_sdk_enabled,
    )

    env_control = EnvFileControlService(system_registry)
    try:
        diff = await env_control.write(system_name, [(line.key, line.value) for line in lines if line.kind == "kv"])
    except InstanceDirectoryNotFoundError:
        _audit_step(db, admin, "env.write", system_name, False, request_id, ip, {"reason": "instance_directory_not_found"})
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Instance directory does not exist") from None

    _audit_step(
        db,
        admin,
        "env.write",
        system_name,
        True,
        request_id,
        ip,
        {"added": sorted(diff.added), "removed": sorted(diff.removed), "changed": sorted(diff.changed)},
    )
    db.commit()

    return ProvisionEnvResponse(entries=[EnvEntry(key=key, value=value) for key, value in entries_from_lines(diff.lines)])


# --- Step 5: build frontend, install dist -------------------------------


@router.post("/{service_id}/provision/frontend", status_code=status.HTTP_204_NO_CONTENT)
async def provision_frontend(
    service_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
    _csrf: None = Depends(require_csrf),
) -> None:
    row = _get_row_with_system_name_or_404(db, service_id)
    request_id, ip = _request_context(request)
    system_name = row.system_name

    env_control = EnvFileControlService(system_registry)
    current_lines = await env_control.read(system_name)
    frontend_env_content = env_template.extract_frontend_vars(current_lines)
    telegram_web_app_local_sdk_enabled = env_template.extract_telegram_web_app_local_sdk_enabled(current_lines)

    frontend_dir = os.path.join(settings.instance_staging_dir, system_name, "frontend")
    if not os.path.isdir(frontend_dir):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No uploaded frontend source found -- run the upload step first",
        )

    executor = CommandExecutor()
    try:
        await frontend_build.build_frontend(
            executor,
            settings.node_bin_dir,
            frontend_dir,
            frontend_env_content,
            settings.system_command_timeout_seconds * 10,  # npm install/build legitimately takes longer
            telegram_web_app_js_path=settings.telegram_web_app_js_path,
            telegram_web_app_local_sdk_enabled=telegram_web_app_local_sdk_enabled,
        )
        frontend_build.promote_dist(system_name, settings.instance_staging_dir)
    except frontend_build.FrontendBuildError as exc:
        _audit_step(db, admin, "instance.frontend_build", system_name, False, request_id, ip, {"reason": str(exc)})
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from None

    action = system_registry.get("instance.install_dist")
    result = await action.run(system_name=system_name)

    if result.exit_code == 0:
        frontend_build.cleanup_staging(system_name, settings.instance_staging_dir)

    _audit_step(db, admin, "instance.install_dist", system_name, result.exit_code == 0, request_id, ip)
    db.commit()

    if result.exit_code != 0:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to install built frontend")


# --- Step 6: nginx -------------------------------------------------------


@router.post("/{service_id}/provision/nginx", response_model=ProvisionNginxResponse)
async def provision_nginx(
    service_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
    _csrf: None = Depends(require_csrf),
) -> ProvisionNginxResponse:
    row = _get_row_with_system_name_or_404(db, service_id)
    request_id, ip = _request_context(request)
    system_name = row.system_name

    nginx_control = NginxControlService(system_registry)

    if row.server_local_port is not None:
        # Retrying this step: reuse the port already assigned to this
        # service instead of picking a new one, so repeated calls stay
        # idempotent and never orphan a systemd unit that is already
        # listening on the first port chosen.
        port = row.server_local_port
    else:
        executor = CommandExecutor()
        used_ports = {
            p
            for (p,) in db.query(ManagedService.server_local_port)
            .filter(ManagedService.server_local_port.is_not(None))
            .all()
        }
        port = await port_allocation.allocate_port(
            executor,
            settings.ss_path,
            settings.system_command_timeout_seconds,
            used_ports,
            settings.service_port_range_start,
        )

    dist_root = f"{(settings.instances_root_dir or '').rstrip('/')}/{system_name}/dist/"
    block = render_block(
        system_name,
        domain_from_url(row.url),
        domain_from_url(row.backend_base_url or ""),
        dist_root,
        port,
        settings.nginx_ssl_certificate,
        settings.nginx_ssl_certificate_key,
    )

    try:
        await nginx_control.upsert_service_block(system_name, block)
    except NginxConfigInvalidError as exc:
        _audit_step(db, admin, "nginx.upsert", system_name, False, request_id, ip, {"reason": str(exc)})
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from None
    except SystemExecutionError as exc:
        _audit_step(db, admin, "nginx.upsert", system_name, False, request_id, ip)
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from None

    row.server_local_port = port
    _audit_step(db, admin, "nginx.upsert", system_name, True, request_id, ip, {"port": port})
    db.commit()

    return ProvisionNginxResponse(port=port)


# --- Step 7: systemd unit ------------------------------------------------


@router.post("/{service_id}/provision/systemd", status_code=status.HTTP_204_NO_CONTENT)
async def provision_systemd(
    service_id: int,
    payload: ProvisionSystemdRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
    _csrf: None = Depends(require_csrf),
) -> None:
    row = _get_row_with_system_name_or_404(db, service_id)
    request_id, ip = _request_context(request)
    system_name = row.system_name

    instance_dir = f"{(settings.instances_root_dir or '').rstrip('/')}/{system_name}"
    unit_content = render_unit(system_name, settings.service_work_user, settings.service_venv_dir, instance_dir, payload.port)

    write_action = system_registry.get("systemd.write_unit")
    write_result = await write_action.run(system_name=system_name, content=unit_content.encode("utf-8"))

    if write_result.exit_code != 0:
        _audit_step(db, admin, "systemd.write_unit", system_name, False, request_id, ip)
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to write systemd unit")

    # The unit file just written is the ultimate ground truth for what
    # port the process listens on -- keep server_local_port in sync even
    # if the admin overrode the port field in the wizard by hand.
    row.server_local_port = payload.port

    enable_action = system_registry.get("service.enable_now")
    enable_result = await enable_action.run(unit_name=unit_name_for(system_name))

    _audit_step(
        db,
        admin,
        "systemd.write_unit",
        system_name,
        True,
        request_id,
        ip,
    )
    _audit_step(
        db,
        admin,
        "service.enable_now",
        system_name,
        enable_result.exit_code == 0,
        request_id,
        ip,
        {"port": payload.port},
    )
    db.commit()

    if enable_result.exit_code != 0:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to start/enable the new service")


# --- Status ---------------------------------------------------------------


@router.get("/{service_id}/provision/status", response_model=ProvisionStatusResponse)
async def provision_status(
    service_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
) -> ProvisionStatusResponse:
    row = _get_row_with_system_name_or_404(db, service_id)
    system_name = row.system_name
    root = settings.instances_root_dir

    def _dir_status(*parts: str) -> ProvisionStepStatus:
        if not root:
            return ProvisionStepStatus(done=False, detail="INSTANCES_ROOT_DIR not configured")
        path = os.path.join(root, system_name, *parts)
        exists = os.path.isdir(path) and bool(os.listdir(path))
        return ProvisionStepStatus(done=exists, detail=path)

    if root:
        dirs_status = ProvisionStepStatus(done=os.path.isdir(os.path.join(root, system_name)))
    else:
        dirs_status = ProvisionStepStatus(done=False, detail="INSTANCES_ROOT_DIR not configured")
    backend_status = _dir_status("backend")
    frontend_status = _dir_status("dist")

    env_control = EnvFileControlService(system_registry)
    env_lines = await env_control.read(system_name)
    env_values = dict(entries_from_lines(env_lines))
    env_status = ProvisionStepStatus(done=bool(env_values.get("SYSTEM_GATEWAY_API_KEY")))

    nginx_control = NginxControlService(system_registry)
    nginx_config = await nginx_control.read_config()
    nginx_status = ProvisionStepStatus(done=has_block(nginx_config, system_name))

    service_control = ServiceControlService(system_registry)
    unit_status = await service_control.get_status(system_name)
    systemd_status = ProvisionStepStatus(
        done=unit_status.exists and unit_status.active_state == "active",
        detail=unit_status.active_state,
    )

    return ProvisionStatusResponse(
        dirs=dirs_status,
        backend_uploaded=backend_status,
        env_generated=env_status,
        frontend_built=frontend_status,
        nginx=nginx_status,
        systemd=systemd_status,
    )
