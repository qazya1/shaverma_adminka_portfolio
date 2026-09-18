from pydantic import BaseModel, Field


class EnvEntry(BaseModel):
    key: str
    value: str


class ServiceEnvResponse(BaseModel):
    service_id: int
    name: str
    system_name: str
    # Informational only -- see Settings.instances_root_dir.
    path: str | None = None
    entries: list[EnvEntry]


class ServiceEnvUpdateRequest(BaseModel):
    # The complete desired set of entries -- a key missing from this list
    # is deleted, a new key is added, an existing key with a different
    # value is updated. Order is preserved for newly added keys.
    entries: list[EnvEntry] = Field(default_factory=list)
