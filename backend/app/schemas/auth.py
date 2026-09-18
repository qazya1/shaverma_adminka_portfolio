from datetime import datetime

from pydantic import BaseModel, Field


class LoginStartRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginStartResponse(BaseModel):
    challenge_id: int
    expires_at: datetime


class LoginVerifyRequest(BaseModel):
    challenge_id: int
    code: str = Field(min_length=1, max_length=16)


class AdminPublic(BaseModel):
    id: int
    username: str
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


class LoginVerifyResponse(BaseModel):
    admin: AdminPublic


class MeResponse(BaseModel):
    admin: AdminPublic


class LogoutResponse(BaseModel):
    detail: str = "logged out"
