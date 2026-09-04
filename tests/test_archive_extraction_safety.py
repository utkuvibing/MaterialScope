"""Track A (PR-5): hostile archives are rejected; installs are failure-atomic."""

from __future__ import annotations

import io
import os
import tarfile
import zipfile
from pathlib import Path

import pytest

from core.archive_safety import safe_extract_tar, safe_extract_zip
from core.reference_library import LibraryPackage, ReferenceLibraryManager
from tools.library_ingest.common import _extract_archive

HOSTILE_NAMES = [
    "../evil.txt",
    "a/../../evil.txt",
    "/abs.txt",
    "\\rooted\\evil.txt",
    "C:evil.txt",
    "C:/evil.txt",
    "C:\\evil.txt",
    "\\\\server\\share\\evil.txt",
]


def _zip_bytes(names: list[str], *, symlink: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, b"evil")
        if symlink is not None:
            info = zipfile.ZipInfo(symlink)
            info.create_system = 3
            info.external_attr = (0o120777 << 16)
            archive.writestr(info, "target.txt")
    return buffer.getvalue()


def _tar_bytes(names: list[str], *, link: tuple[str, str] | None = None, fifo: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name in names:
            payload = b"evil"
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        if link is not None:
            kind, linkname = link
            info = tarfile.TarInfo("link.txt")
            info.type = tarfile.SYMTYPE if kind == "sym" else tarfile.LNKTYPE
            info.linkname = linkname
            archive.addfile(info)
        if fifo is not None:
            info = tarfile.TarInfo(fifo)
            info.type = tarfile.FIFOTYPE
            archive.addfile(info)
    return buffer.getvalue()


def _write_archive(tmp_path: Path, filename: str, raw: bytes) -> Path:
    path = tmp_path / filename
    path.write_bytes(raw)
    return path


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_hostile_zip_member_rejected_without_escape(tmp_path: Path, name: str) -> None:
    archive_path = _write_archive(tmp_path, "payload.zip", _zip_bytes([name]))
    target = tmp_path / "extracted"
    with pytest.raises(ValueError):
        _extract_archive(archive_path, target)
    assert list(tmp_path.rglob("*evil*")) == []


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_hostile_tar_member_rejected_without_escape(tmp_path: Path, name: str) -> None:
    archive_path = _write_archive(tmp_path, "payload.tar", _tar_bytes([name]))
    target = tmp_path / "extracted"
    with pytest.raises(ValueError):
        _extract_archive(archive_path, target)
    assert list(tmp_path.rglob("*evil*")) == []


def test_zip_symlink_member_rejected(tmp_path: Path) -> None:
    archive_path = _write_archive(tmp_path, "payload.zip", _zip_bytes(["ok.txt"], symlink="link.txt"))
    with pytest.raises(ValueError, match="link"):
        _extract_archive(archive_path, tmp_path / "extracted")
    assert list(tmp_path.rglob("link*")) == []


@pytest.mark.parametrize("kind", ["sym", "hard"])
def test_tar_link_members_rejected(tmp_path: Path, kind: str) -> None:
    archive_path = _write_archive(tmp_path, "payload.tar", _tar_bytes(["ok.txt"], link=(kind, "ok.txt")))
    with pytest.raises(ValueError, match="unsafe type"):
        _extract_archive(archive_path, tmp_path / "extracted")


def test_tar_fifo_member_rejected(tmp_path: Path) -> None:
    archive_path = _write_archive(tmp_path, "payload.tar", _tar_bytes(["ok.txt"], fifo="pipe"))
    with pytest.raises(ValueError, match="unsafe type"):
        _extract_archive(archive_path, tmp_path / "extracted")


def test_benign_archives_roundtrip(tmp_path: Path) -> None:
    zip_raw = _zip_bytes(["folder/", "folder/nested.txt", "top.txt"])
    zip_target = tmp_path / "zip_out"
    with zipfile.ZipFile(io.BytesIO(zip_raw), "r") as archive:
        safe_extract_zip(archive, zip_target)
    assert (zip_target / "folder" / "nested.txt").read_bytes() == b"evil"
    assert (zip_target / "top.txt").read_bytes() == b"evil"

    tar_raw = _tar_bytes(["folder/nested.txt", "top.txt"])
    tar_target = tmp_path / "tar_out"
    with tarfile.open(fileobj=io.BytesIO(tar_raw), mode="r") as archive:
        safe_extract_tar(archive, tar_target)
    assert (tar_target / "folder" / "nested.txt").read_bytes() == b"evil"
    assert (tar_target / "top.txt").read_bytes() == b"evil"


def _test_package() -> LibraryPackage:
    return LibraryPackage(
        package_id="testpkg",
        analysis_type="XRD",
        provider="test",
        version="v1",
        archive_name="testpkg.zip",
        sha256="0" * 64,
        entry_count=0,
    )


def test_hostile_replacement_keeps_working_install(tmp_path: Path) -> None:
    manager = ReferenceLibraryManager(root=tmp_path / "lib", feed_source="")
    package = _test_package()
    manager._install_package(package, _zip_bytes(["sentinel.txt"]))
    sentinel = manager._installed_root() / "testpkg" / "v1" / "sentinel.txt"
    assert sentinel.read_bytes() == b"evil"

    with pytest.raises(ValueError):
        manager._install_package(package, _zip_bytes(["../evil.txt"]))
    assert sentinel.read_bytes() == b"evil"
    assert list(tmp_path.rglob("*evil*")) == []


def test_promotion_failure_restores_previous_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = ReferenceLibraryManager(root=tmp_path / "lib", feed_source="")
    package = _test_package()
    manager._install_package(package, _zip_bytes(["sentinel.txt"]))
    extract_dir = manager._installed_root() / "testpkg" / "v1"
    assert (extract_dir / "sentinel.txt").read_bytes() == b"evil"

    real_replace = os.replace

    def _flaky_replace(src: Path, dst: Path, *args: object, **kwargs: object) -> None:
        if Path(dst) == extract_dir and Path(src).name == "staged":
            raise RuntimeError("injected promotion failure")
        real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", _flaky_replace)
    with pytest.raises(RuntimeError, match="injected promotion failure"):
        manager._install_package(package, _zip_bytes(["replacement.txt"]))

    assert (extract_dir / "sentinel.txt").read_bytes() == b"evil"
    assert not (extract_dir / "replacement.txt").exists()
    assert not extract_dir.with_name("v1.bak").exists()
