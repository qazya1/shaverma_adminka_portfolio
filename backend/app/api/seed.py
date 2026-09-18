"""Endpoints for listing/editing a shaverma instance's DB-seed script
pairs and running one of them against its own database.

Background: each deployed instance's `backend/app/seed/` folder can hold
zero or more *pairs* of scripts an operator currently runs by hand
(`cd backend && python -m app.seed.seed_db...`, in the shared venv) to
populate a fresh database -- `seed_data<suffix>.py` (edited here, raw)
and `seed_db<suffix>.py` (run here, unedited -- see
app.system.seed_control for the full naming rules). Every endpoint here
is authenticated; the two that change something (write/run) are also
CSRF-protected and audit-logged, same as the .env editor and the
service-update endpoint above it in this package.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.audit import service as audit_service
from app.auth.dependencies import get_current_admin, require_csrf
from app.core.database import get_db
from app.external.models import ManagedService
from app.models.admin import AdminUser
from app.schemas.seed import (
    SeedDataResponse,
    SeedDataUpdateRequest,
    SeedPairsResponse,
    SeedRunRequest,
    SeedRunResponse,
)
from app.system.exceptions import InvalidSystemNameError, SystemExecutionError
from app.system.registry import registry as system_registry
from app.system.seed_control import InvalidPairKeyError, SeedControlService, SeedPairNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services", tags=["seed"])


def _get_row_or_404(db: Session, service_id: int) -> ManagedService:
    row = db.get(ManagedService, service_id)
    if row is None or not row.system_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return row


def _request_context(request: Request) -> tuple[str | None, str | None]:
    request_id = getattr(request.state, "request_id", None)
    ip = request.client.host if request.client else None
    return request_id, ip


def _invalid_identifier_response(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/{service_id}/seed/pairs", response_model=SeedPairsResponse)
async def list_seed_pairs(
    service_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> SeedPairsResponse:
    row = _get_row_or_404(db, service_id)
    control = SeedControlService(system_registry)

    try:
        pairs = await control.list_pairs(row.system_name)
    except InvalidSystemNameError as exc:
        raise _invalid_identifier_response(exc) from None
    except SystemExecutionError:
        logger.exception("seed.list failed for system_name=%s", row.system_name)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to list seed script pairs") from None

    return SeedPairsResponse(pairs=pairs)


@router.get("/{service_id}/seed/data", response_model=SeedDataResponse)
async def get_seed_data(
    service_id: int,
    pair_key: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> SeedDataResponse:
    row = _get_row_or_404(db, service_id)
    request_id, ip = _request_context(request)
    control = SeedControlService(system_registry)

    try:
        content = await control.read_data(row.system_name, pair_key)
    except (InvalidSystemNameError, InvalidPairKeyError) as exc:
        raise _invalid_identifier_response(exc) from None
    except SeedPairNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seed pair not found") from None
    except SystemExecutionError:
        logger.exception("seed.read_data failed for system_name=%s pair_key=%s", row.system_name, pair_key)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to read seed data file") from None

    # Reading a seed data file exposes its full content -- audited on
    # success too, not just failure, same reasoning as the .env editor's
    # GET (app.api.services.get_service_env): seed data isn't guaranteed
    # to be free of anything an admin would consider sensitive.
    audit_service.record_event(
        db,
        action="seed.read_data",
        status="success",
        admin_id=admin.id,
        target=row.system_name,
        parameters={"pair_key": pair_key},
        request_id=request_id,
        request_ip=ip,
    )
    db.commit()

    return SeedDataResponse(pair_key=pair_key, content=content)


@router.post("/{service_id}/seed/data", response_model=SeedDataResponse)
async def update_seed_data(
    service_id: int,
    payload: SeedDataUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),
) -> SeedDataResponse:
    row = _get_row_or_404(db, service_id)
    request_id, ip = _request_context(request)
    control = SeedControlService(system_registry)

    try:
        await control.write_data(row.system_name, payload.pair_key, payload.content)
    except (InvalidSystemNameError, InvalidPairKeyError) as exc:
        raise _invalid_identifier_response(exc) from None
    except SeedPairNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seed pair not found") from None
    except SystemExecutionError:
        logger.exception(
            "seed.write_data failed for system_name=%s pair_key=%s", row.system_name, payload.pair_key
        )
        audit_service.record_event(
            db,
            action="seed.write_data",
            status="failure",
            admin_id=admin.id,
            target=row.system_name,
            parameters={"pair_key": payload.pair_key},
            request_id=request_id,
            request_ip=ip,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to save seed data file") from None

    audit_service.record_event(
        db,
        action="seed.write_data",
        status="success",
        admin_id=admin.id,
        target=row.system_name,
        parameters={"pair_key": payload.pair_key},
        request_id=request_id,
        request_ip=ip,
    )
    db.commit()

    return SeedDataResponse(pair_key=payload.pair_key, content=payload.content)


@router.post("/{service_id}/seed/run", response_model=SeedRunResponse)
async def run_seed_db(
    service_id: int,
    payload: SeedRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),
) -> SeedRunResponse:
    row = _get_row_or_404(db, service_id)
    request_id, ip = _request_context(request)
    control = SeedControlService(system_registry)

    try:
        result = await control.run_db(row.system_name, payload.pair_key)
    except (InvalidSystemNameError, InvalidPairKeyError) as exc:
        raise _invalid_identifier_response(exc) from None

    succeeded = result.exit_code == 0 and not result.timed_out
    audit_service.record_event(
        db,
        action="seed.run_db",
        status="success" if succeeded else "failure",
        admin_id=admin.id,
        target=row.system_name,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        parameters={"pair_key": payload.pair_key, "timed_out": result.timed_out},
        request_id=request_id,
        request_ip=ip,
    )
    db.commit()

    return SeedRunResponse(
        pair_key=payload.pair_key,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        timed_out=result.timed_out,
    )
