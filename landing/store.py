"""Waitlist persistence for the MaterialScope landing page.

The product has no user database, so the waitlist keeps its own tiny,
replaceable storage boundary: an append-only JSONL file with an in-memory
dedupe index.  ``WaitlistStore`` is the single seam to swap out when a real
database (or CRM/webhook) is introduced — the FastAPI layer never touches
disk directly.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

# Deliberately pragmatic: RFC-5322-grade grammar is overkill for a signup
# field; this catches the real-world mistakes while accepting exotic-but-valid
# local parts.  The server, not the browser, is the enforcement point.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")

MAX_EMAIL_LEN = 254
MAX_ROLE_LEN = 64

ROLES = (
    "research",
    "qc_rd_lab",
    "graduate",
    "testing",
    "industry",
    "other",
)


def normalize_email(raw: str | None) -> str:
    return (raw or "").strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(email) and len(email) <= MAX_EMAIL_LEN and _EMAIL_RE.match(email) is not None


def normalize_role(raw: str | None) -> str:
    role = (raw or "").strip().lower()
    return role if role in ROLES else ""


class WaitlistStore:
    """Thread-safe append-only waitlist store backed by one JSONL file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._seen: set[str] = set()
        self._count = 0
        self._load_existing()

    def _load_existing(self) -> None:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    email = str(record.get("email") or "")
                except json.JSONDecodeError:
                    continue
                if email:
                    self._seen.add(email)
                    self._count += 1

    def join(self, email: str, role: str = "") -> str:
        """Record an email; returns ``"joined"`` or ``"already"`` for repeats."""
        email = normalize_email(email)
        role = normalize_role(role)
        if not is_valid_email(email):
            raise ValueError("invalid email")
        with self._lock:
            if email in self._seen:
                return "already"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "email": email,
                "role": role,
                "joined_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._seen.add(email)
            self._count += 1
            return "joined"

    @property
    def count(self) -> int:
        with self._lock:
            return self._count
