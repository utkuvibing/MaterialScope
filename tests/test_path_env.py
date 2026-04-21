from __future__ import annotations

import sys

import pytest

from core.path_env import library_filesystem_env_looks_like_windows_leak


@pytest.mark.skipif(sys.platform == "win32", reason="Windows-leak heuristic is POSIX-only")
def test_detects_backslash_windows_path_on_posix():
    assert library_filesystem_env_looks_like_windows_leak(r"C:\thermoanalyzer\build\reference_library_hosted") is True


@pytest.mark.skipif(sys.platform == "win32", reason="Windows-leak heuristic is POSIX-only")
def test_detects_mangled_drive_mid_path():
    assert (
        library_filesystem_env_looks_like_windows_leak(
            "/home/dev/proj/C:thermoanalyzerbuildreference_library_hosted",
        )
        is True
    )


@pytest.mark.skipif(sys.platform == "win32", reason="Windows-leak heuristic is POSIX-only")
def test_plain_unix_path_is_not_flagged():
    assert library_filesystem_env_looks_like_windows_leak("/home/dev/materialscope/build/reference_library_hosted") is False


@pytest.mark.skipif(sys.platform == "win32", reason="Windows-leak heuristic is POSIX-only")
def test_http_url_is_not_flagged():
    assert library_filesystem_env_looks_like_windows_leak("http://127.0.0.1:8050/v1") is False


@pytest.mark.skipif(sys.platform == "win32", reason="hosted-root sanitation is POSIX-focused in tests")
def test_resolve_hosted_root_falls_back_when_env_is_windows_leak(monkeypatch):
    from core.hosted_library import DEFAULT_HOSTED_ROOT, resolve_hosted_root

    monkeypatch.setenv("MATERIALSCOPE_LIBRARY_HOSTED_ROOT", "/home/user/proj/C:thermoanalyzerbuildhosted")
    resolved = resolve_hosted_root()
    assert resolved.resolve() == DEFAULT_HOSTED_ROOT.resolve()


@pytest.mark.skipif(sys.platform == "win32", reason="mirror feed skip is POSIX-focused in tests")
def test_configured_library_feed_ignores_windows_mirror_on_posix(monkeypatch):
    from core.reference_library import configured_library_feed_source

    monkeypatch.setenv("MATERIALSCOPE_LIBRARY_MIRROR_ROOT", r"C:\materialscope\build\mirror")
    assert configured_library_feed_source() is None
