"""Safe archive extraction for remotely fetched library packages.

Both the ingest tooling (``tools/library_ingest/common.py``) and the runtime
library installer (``core/reference_library.py``) unpack archives downloaded
from remote feed sources. Plain ``extractall`` trusts member names, which
allows ZipSlip/tar-slip writes outside the target directory plus link and
device members. The helpers here validate every member before anything is
written.

Validation is manual (not ``tarfile`` ``filter="data"``) because the
``filter`` keyword exists only on Python 3.12+ while this project supports
``>=3.11``; manual checks behave identically on both CI legs.
"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath


def _reject_unsafe_name(member: str) -> None:
    """Raise ValueError unless ``member`` is a portable relative archive path."""
    if not member:
        raise ValueError("Archive member has unsafe path: <empty>")
    if "\x00" in member:
        raise ValueError(f"Archive member has unsafe path: {member!r}")
    if PurePosixPath(member).is_absolute():
        raise ValueError(f"Archive member has unsafe path: {member}")
    windows = PureWindowsPath(member)
    if windows.drive or windows.root:
        raise ValueError(f"Archive member has unsafe path: {member}")
    if any(part == ".." for part in windows.parts):
        raise ValueError(f"Archive member has unsafe path: {member}")


def _resolve_within(target_dir: Path, member: str) -> Path:
    """Resolve ``member`` under ``target_dir``; raise ValueError on escape."""
    root = target_dir.resolve()
    resolved = (root / member).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Archive member escapes target directory: {member}")
    return resolved


def safe_extract_zip(archive: zipfile.ZipFile, target_dir: Path) -> None:
    """Extract ``archive`` into ``target_dir`` after validating every member."""
    for info in archive.infolist():
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError(f"Archive member is a link: {info.filename}")
        _reject_unsafe_name(info.filename)
        _resolve_within(target_dir, info.filename)
    archive.extractall(target_dir)


def safe_extract_tar(archive: tarfile.TarFile, target_dir: Path) -> None:
    """Extract ``archive`` into ``target_dir`` after validating every member."""
    for member in archive.getmembers():
        _reject_unsafe_name(member.name)
        _resolve_within(target_dir, member.name)
        if not (member.isdir() or member.isreg()):
            raise ValueError(f"Archive member has unsafe type: {member.name}")
    archive.extractall(target_dir)
