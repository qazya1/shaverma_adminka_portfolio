from pydantic import BaseModel


class SeedPairsResponse(BaseModel):
    """`pairs` is a list of pair_key values (see app.system.seed_control)
    -- "" for the base seed_data.py/seed_db.py pair, otherwise the
    filename suffix (e.g. "mrgiros" for seed_data_mrgiros.py)."""

    pairs: list[str]


class SeedDataResponse(BaseModel):
    pair_key: str
    content: str


class SeedDataUpdateRequest(BaseModel):
    pair_key: str
    content: str


class SeedRunRequest(BaseModel):
    pair_key: str


class SeedRunResponse(BaseModel):
    """The seed_db script's raw outcome -- deliberately unfiltered (full
    stdout/stderr) so the admin can see exactly what it did or why it
    failed; see SeedControlService.run_db for why exit_code isn't
    reinterpreted into a more specific error here."""

    pair_key: str
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
