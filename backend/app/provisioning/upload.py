"""Safely extracts an admin-uploaded zip (expected to contain top-level
`frontend/` and `backend/` folders) into adminka's own unprivileged
staging area.

Extraction is done entirely in-process with Python's `zipfile` -- never
by shelling out to `unzip` -- so there's no command-injection surface at
all here, only the usual zip-parsing hazards this module defends
against explicitly: path traversal, symlinks, and zip bombs (excessive
total size or entry count).
"""

import os
import shutil
import zipfile
from dataclasses import dataclass

_MAX_TOTAL_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # 500 MB
_MAX_ENTRY_COUNT = 20_000

# The only two top-level folders this module ever extracts into
# something the rest of the app acts on. The new-service wizard's own
# upload step requires both (its default); the later file-update feature
# (see app.api.services.update_service_files) allows either one alone,
# or both together -- but never neither.
_ALLOWED_TOP_LEVEL_DIRS = ("frontend", "backend")

# A symlink in a zip entry is flagged in the upper 16 bits of
# external_attr (the Unix file mode); 0o120000 is S_IFLNK.
_ZIP_SYMLINK_MODE_MASK = 0o170000
_ZIP_SYMLINK_MODE = 0o120000


class InvalidUploadError(ValueError):
    """Raised for anything wrong with the uploaded archive -- bad
    structure, a dangerous entry, or exceeding the size/count limits.
    Never partially extracts; validates the whole archive up front."""


@dataclass(frozen=True)
class ExtractedUpload:
    frontend_dir: str
    backend_dir: str


def _is_safe_member_path(name: str) -> bool:
    if name.startswith("/") or name.startswith("\\"):
        return False
    if ":" in name:  # e.g. a Windows drive letter
        return False
    normalized = os.path.normpath(name)
    if normalized.startswith("..") or normalized.startswith(f"..{os.sep}"):
        return False
    if os.path.isabs(normalized):
        return False
    return True


def _validate_and_plan(zf: zipfile.ZipFile, required_top_level_dirs: tuple[str, ...]) -> list[zipfile.ZipInfo]:
    infos = zf.infolist()
    if len(infos) > _MAX_ENTRY_COUNT:
        raise InvalidUploadError(f"archive has too many entries (> {_MAX_ENTRY_COUNT})")

    total_size = 0
    top_level_dirs: set[str] = set()

    for info in infos:
        name = info.filename
        if not _is_safe_member_path(name):
            raise InvalidUploadError(f"unsafe path in archive: {name!r}")

        if (info.external_attr >> 16) & _ZIP_SYMLINK_MODE_MASK == _ZIP_SYMLINK_MODE:
            raise InvalidUploadError(f"archive contains a symlink, which is not allowed: {name!r}")

        total_size += info.file_size
        if total_size > _MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise InvalidUploadError(
                f"archive exceeds the maximum total uncompressed size ({_MAX_TOTAL_UNCOMPRESSED_BYTES} bytes)"
            )

        top = name.split("/", 1)[0]
        if top:
            top_level_dirs.add(top)

    missing = [d for d in required_top_level_dirs if d not in top_level_dirs]
    if missing:
        raise InvalidUploadError(
            f"archive must contain top-level folders {required_top_level_dirs!r}, missing: {missing!r}"
        )
    # required_top_level_dirs can legitimately be empty (the file-update
    # feature: either folder alone is fine) -- but an archive with
    # *neither* recognized folder at all is never useful to extract here,
    # regardless of what was explicitly required.
    if not top_level_dirs & set(_ALLOWED_TOP_LEVEL_DIRS):
        raise InvalidUploadError(f"archive must contain at least one of {_ALLOWED_TOP_LEVEL_DIRS!r}")

    return infos


def extract_upload(
    zip_path: str,
    destination_dir: str,
    *,
    required_top_level_dirs: tuple[str, ...] = _ALLOWED_TOP_LEVEL_DIRS,
) -> ExtractedUpload:
    """Validate `zip_path` and extract it into `destination_dir`
    (created fresh -- any existing content there is removed first, same
    "retry gives a clean result" philosophy as the privileged helpers).

    `required_top_level_dirs` defaults to requiring both `frontend/` and
    `backend/` (the new-service wizard's own upload step). Pass `()` for
    the file-update feature, where either one alone is accepted -- the
    "at least one" check above still applies regardless.

    The returned `ExtractedUpload.frontend_dir`/`.backend_dir` are always
    the two possible paths under `destination_dir`, whether or not this
    particular archive actually contained that folder -- callers that
    allow a subset must check `os.path.isdir(...)` themselves to see
    which one(s) were actually extracted.
    """

    if os.path.isdir(destination_dir):
        shutil.rmtree(destination_dir)
    os.makedirs(destination_dir, exist_ok=False)

    try:
        with zipfile.ZipFile(zip_path) as zf:
            infos = _validate_and_plan(zf, required_top_level_dirs)
            zf.extractall(destination_dir, members=infos)
    except zipfile.BadZipFile as exc:
        raise InvalidUploadError("uploaded file is not a valid zip archive") from exc

    return ExtractedUpload(
        frontend_dir=os.path.join(destination_dir, "frontend"),
        backend_dir=os.path.join(destination_dir, "backend"),
    )
