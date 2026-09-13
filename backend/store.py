"""In-memory project state store for tranche-1 backend routes.

PR-14 store hygiene:

- **Copy-on-read / copy-on-write**: ``get`` and ``set`` hand out and store
  deep copies, so a caller mutating nested state without ``set()`` can no
  longer silently corrupt the shared store.
- **Per-project locks**: each project id gets its own lock, so concurrent
  requests for *different* projects do not serialize on one global mutex.
- **Disk autosave journal**: when a journal directory is configured, every
  successful ``set``/``put`` atomically snapshots the full state
  (``<project_id>.msjournal``, pickle) so a crash or restart can restore
  workspaces losslessly — including live ``ThermalDataset`` objects that
  the ``.scopezip`` archive format cannot round-trip.  ``get``/``set``
  lazily restore from the journal when memory has no entry.
"""

from __future__ import annotations

import copy
import logging
import os
import pickle
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_JOURNAL_VERSION = 1
_JOURNAL_SUFFIX = ".msjournal"


def _default_journal_dir() -> Path | None:
    """Resolve the autosave journal directory from the environment.

    Explicit override: ``MATERIALSCOPE_JOURNAL_DIR``.  Otherwise the app
    home (``MATERIALSCOPE_HOME`` / legacy ``THERMOANALYZER_HOME``) gets a
    ``journal/`` subfolder.  With no configured home we do not guess a
    location — autosave simply stays off (keeps bare ``ProjectStore()``
    instances, e.g. in tests, hermetic).
    """
    explicit = os.getenv("MATERIALSCOPE_JOURNAL_DIR")
    if explicit:
        return Path(explicit)
    root = os.getenv("MATERIALSCOPE_HOME") or os.getenv("THERMOANALYZER_HOME")
    if root:
        return Path(root) / "journal"
    return None


class ProjectStore:
    """Thread-safe project state store with copy-on-read and autosave journal.

    Parameters
    ----------
    journal_dir:
        Directory for autosave snapshots.  ``None`` resolves
        ``MATERIALSCOPE_JOURNAL_DIR`` then ``<MATERIALSCOPE_HOME>/journal``.
    autosave:
        ``True`` forces the journal on (requires a resolvable directory),
        ``False`` disables it, ``None`` (default) enables it only when a
        directory is configured.
    """

    def __init__(
        self,
        journal_dir: str | Path | None = None,
        autosave: bool | None = None,
    ) -> None:
        self._locks_guard = threading.Lock()
        self._locks: dict[str, threading.RLock] = {}
        self._projects: dict[str, dict[str, Any]] = {}

        resolved = Path(journal_dir) if journal_dir else _default_journal_dir()
        self._journal_dir: Path | None = resolved if autosave is not False else None
        if autosave is True and self._journal_dir is None:
            raise ValueError(
                "autosave=True requires a journal directory "
                "(journal_dir, MATERIALSCOPE_JOURNAL_DIR, or MATERIALSCOPE_HOME)."
            )
        if self._journal_dir is not None:
            try:
                self._journal_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.warning("Autosave journal disabled: cannot create %s (%s)", self._journal_dir, exc)
                self._journal_dir = None

    # ------------------------------------------------------------------
    # Locking
    # ------------------------------------------------------------------

    def _lock_for(self, project_id: str) -> threading.RLock:
        with self._locks_guard:
            lock = self._locks.get(project_id)
            if lock is None:
                lock = threading.RLock()
                self._locks[project_id] = lock
            return lock

    # ------------------------------------------------------------------
    # Journal I/O
    # ------------------------------------------------------------------

    @property
    def journal_enabled(self) -> bool:
        return self._journal_dir is not None

    def journal_path(self, project_id: str) -> Path | None:
        if self._journal_dir is None:
            return None
        safe = "".join(c for c in project_id if c.isalnum() or c in "-_")
        return self._journal_dir / f"{safe}{_JOURNAL_SUFFIX}"

    def _write_journal(self, project_id: str, state: dict[str, Any]) -> None:
        path = self.journal_path(project_id)
        if path is None:
            return
        payload = {
            "journal_version": _JOURNAL_VERSION,
            "project_id": project_id,
            "saved_at_utc": datetime.now(timezone.utc).isoformat(),
            "state": state,
        }
        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "wb") as tmp_file:
                pickle.dump(payload, tmp_file, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp_name, path)
        except Exception as exc:  # autosave is best-effort, never fatal
            logger.warning("Autosave journal write failed for %s: %s", project_id, exc)
            try:
                os.unlink(tmp_name)
            except OSError:
                pass

    def _read_journal(self, project_id: str) -> dict[str, Any] | None:
        path = self.journal_path(project_id)
        if path is None or not path.exists():
            return None
        try:
            with open(path, "rb") as journal_file:
                payload = pickle.load(journal_file)
        except Exception as exc:
            logger.warning("Autosave journal unreadable for %s (%s): %s", project_id, path, exc)
            return None
        if not isinstance(payload, dict) or payload.get("project_id") != project_id:
            logger.warning("Autosave journal %s does not match project %s; ignored.", path, project_id)
            return None
        state = payload.get("state")
        return state if isinstance(state, dict) else None

    def _restore_if_needed(self, project_id: str) -> None:
        """Lazily hydrate a project from its journal after a restart."""
        if project_id in self._projects:
            return
        state = self._read_journal(project_id)
        if state is not None:
            self._projects[project_id] = state
            logger.info("Restored project %s from autosave journal.", project_id)

    # ------------------------------------------------------------------
    # Public API (same contract as before, now with copy semantics)
    # ------------------------------------------------------------------

    def put(self, project_state: dict[str, Any]) -> str:
        project_id = uuid.uuid4().hex
        with self._lock_for(project_id):
            self._projects[project_id] = copy.deepcopy(project_state)
            self._write_journal(project_id, self._projects[project_id])
        return project_id

    def get(self, project_id: str) -> dict[str, Any] | None:
        with self._lock_for(project_id):
            self._restore_if_needed(project_id)
            state = self._projects.get(project_id)
            return copy.deepcopy(state) if state is not None else None

    def set(self, project_id: str, project_state: dict[str, Any]) -> bool:
        with self._lock_for(project_id):
            self._restore_if_needed(project_id)
            if project_id not in self._projects:
                return False
            self._projects[project_id] = copy.deepcopy(project_state)
            self._write_journal(project_id, self._projects[project_id])
            return True
