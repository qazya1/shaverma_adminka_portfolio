from pydantic import BaseModel, Field

from app.schemas.env_file import EnvEntry


class NewServiceRequest(BaseModel):
    label: str = Field(min_length=1, max_length=63, description="Third-level domain label, e.g. 'индия'")
    name: str = Field(min_length=1, max_length=120)
    system_name: str = Field(min_length=1, max_length=30)
    is_active: bool = True
    channels: list[str] = Field(default_factory=lambda: ["telegram", "max"])
    bot_entry_key: str | None = None
    client_bot_entry_key: str | None = None


class NewServiceResponse(BaseModel):
    id: int
    name: str
    system_name: str
    url: str
    backend_base_url: str
    is_active: bool


class ProvisionEnvRequest(BaseModel):
    database_name: str = Field(min_length=1, max_length=64)
    database_user: str = Field(min_length=1, max_length=32)
    yookassa_recurring_payments_enabled: bool = False
    # Both optional -- entered by hand, exactly like the template this
    # was built from marks them ("entered by hand, optional"). Left
    # blank in .env (as before) when not given.
    yookassa_shop_id: str | None = None
    yookassa_secret_key: str | None = None
    # The wizard's "Local Telegram Web SDK" checkbox, on by default --
    # whether this service's frontend builds should copy in
    # telegram-web-app.js (see app.provisioning.frontend_build).
    telegram_web_app_local_sdk_enabled: bool = True


class ProvisionEnvResponse(BaseModel):
    entries: list[EnvEntry]


class ProvisionNginxResponse(BaseModel):
    port: int


class ProvisionSystemdRequest(BaseModel):
    port: int


class ProvisionStepStatus(BaseModel):
    done: bool
    detail: str | None = None


class ProvisionStatusResponse(BaseModel):
    dirs: ProvisionStepStatus
    backend_uploaded: ProvisionStepStatus
    env_generated: ProvisionStepStatus
    frontend_built: ProvisionStepStatus
    nginx: ProvisionStepStatus
    systemd: ProvisionStepStatus
