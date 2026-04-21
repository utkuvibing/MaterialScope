"""Heuristics for library-related filesystem paths in cross-platform dev environments."""

from __future__ import annotations

import re
import sys


def library_filesystem_env_looks_like_windows_leak(raw: str | None) -> bool:
    """Return True when a *library path* env value looks like a Windows path used on POSIX.

    Typical failure mode: a ``.env`` copied from Windows contains ``C:\\...`` or a mangled
    ``.../C:thermoanalyzer...`` segment. Treating that as a Linux path breaks hosted/mirror
    resolution and yields empty manifests.
    """
    if sys.platform == "win32" or raw is None:
        return False
    token = str(raw).strip()
    if not token or "://" in token:
        return False
    if "\\" in token:
        return True
    # ``C:\Users\...`` style pasted into a POSIX shell/.env
    if re.match(r"^[A-Za-z]:\\", token):
        return True
    # Mangled paste: ``.../C:thermoanalyzer...`` (drive letter mid-path, not ``D:/unix``)
    if re.search(r"/[A-Za-z]:[^/]", token):
        return True
    # ``C:thermo...`` without leading slash (non-UNC Windows path fragment)
    if re.match(r"^[A-Za-z]:[^/\\]", token):
        return True
    return False
