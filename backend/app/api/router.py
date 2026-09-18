from fastapi import APIRouter

from app.api import auth as auth_api
from app.api import provisioning as provisioning_api
from app.api import seed as seed_api
from app.api import services as services_api

api_router = APIRouter(prefix="/api/v1")


@api_router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


api_router.include_router(auth_api.router)
api_router.include_router(services_api.router)
api_router.include_router(provisioning_api.router)
api_router.include_router(seed_api.router)
