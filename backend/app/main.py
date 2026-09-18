"""ASGI application entrypoint.

Auth (login/OTP/session) plus the real system-modifying capabilities
built on top of it: starting/stopping shaverma backend systemd units,
and reading/writing a shaverma instance's .env file (see
app/api/services.py, app/system/).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.middleware.request_id import RequestIdMiddleware
from app.system.bootstrap import register_default_actions
from app.system.executor import CommandExecutor
from app.system.registry import registry as system_registry

settings = get_settings()

app = FastAPI(
    title="Shaverma Adminka",
    version="0.1.0",
    description="Administrative control-plane for the shaverma project.",
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

app.include_router(api_router)

# The complete, reviewed set of real system actions this process is
# capable of -- see app/system/bootstrap.py. Nothing else in the
# codebase registers an action into system_registry.
register_default_actions(system_registry, settings, CommandExecutor())
