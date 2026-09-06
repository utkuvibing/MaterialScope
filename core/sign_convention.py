"""Sign-convention canon for MaterialScope thermal data.

PR-8 canon: one enum, applied once at ingest, with event labels derived
post-inversion.  Three binding design rules (see ``docs/roadmap.md``,
PR-8 pre-implementation clarifications):

1. Unknown polarity stays unresolved.  ``UNKNOWN`` is never silently
   handled or described as ``CANONICAL``; endo/exo labels are withheld
   and exo/endo summary counts must not claim unknown-polarity events.
   A backward-compatibility assumption that treats unknown polarity as
   exo-up would be permitted only if recorded explicitly in metadata;
   this module implements no such assumption.
2. Declaration parsing and header-hint inspection are separate surfaces.
   ``parse_declared`` accepts only values a user or API caller explicitly
   declared.  ``inspect_header_hints`` returns evidence used exclusively
   for warnings and provenance records; it can never set, choose, or
   flip a convention.
3. Canonicalization preserves raw provenance.  ``apply_canonicalization``
   returns an inversion record beside the working signal so callers can
   persist the originally declared convention and whether the working
   signal is a sign-flip of the imported frame.

Canonical frame: ``EXO_UP`` — positive deviation above the baseline is
exothermic, negative deviation is endothermic.  This matches the
documented contract in ``core/baseline.py``, DTA's physical ΔT direction,
and the pre-PR-8 detector hardcode, so results for declared exo-up data
remain valid.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, Union

import numpy as np

__all__ = [
    "SignConvention",
    "CANONICAL",
    "CANONICAL_SIGNAL_CONVENTION",
    "CANONICAL_METHOD_CONTEXT_ID",
    "UNKNOWN_METHOD_CONTEXT_ID",
    "parse_declared",
    "is_declared",
    "inspect_header_hints",
    "apply_canonicalization",
    "label_from_direction",
    "direction_tag_from_label",
    "canonical_frame_label",
    "provenance_record",
    "summarize_provenance",
]


class SignConvention(str, Enum):
    """Polarity convention of a heat-flow-like thermal signal.

    Values are the declared tokens used in metadata, API payloads, and
    project archives.
    """

    EXO_UP = "exo_up"
    ENDO_UP = "endo_up"
    UNKNOWN = "unknown"


CANONICAL: SignConvention = SignConvention.EXO_UP
CANONICAL_SIGNAL_CONVENTION: str = SignConvention.EXO_UP.value

# Method-context ids used by processing records (enforced canon, not prose).
CANONICAL_METHOD_CONTEXT_ID = "materialscope.canonical_exo_up"
UNKNOWN_METHOD_CONTEXT_ID = "materialscope.unknown_polarity"

_DECLARED_VALUES = frozenset(item.value for item in SignConvention)

_UP_LABELS: Dict[SignConvention, str] = {
    SignConvention.EXO_UP: "exotherm",
    SignConvention.ENDO_UP: "endotherm",
    SignConvention.UNKNOWN: "unknown",
}
_DOWN_LABELS: Dict[SignConvention, str] = {
    SignConvention.EXO_UP: "endotherm",
    SignConvention.ENDO_UP: "exotherm",
    SignConvention.UNKNOWN: "unknown",
}


def parse_declared(
    value: Union[SignConvention, str, None],
    *,
    default: SignConvention | None = None,
) -> SignConvention:
    """Parse an explicitly declared sign-convention value.

    Accepts ``SignConvention`` instances or the exact declared tokens
    ``exo_up`` / ``endo_up`` / ``unknown`` (case-insensitive, surrounding
    whitespace ignored).  Anything else raises ``ValueError``: values that
    merely *hint* at a convention (header text, vendor strings) must never
    reach this parser — route them through :func:`inspect_header_hints`
    instead.

    ``default`` is returned when ``value`` is ``None`` or empty, letting
    callers distinguish "nothing declared" from "invalid declaration".
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        if default is None:
            raise ValueError("No sign convention was declared and no default was provided.")
        return default
    if isinstance(value, SignConvention):
        return value
    token = str(value).strip().lower()
    if token in _DECLARED_VALUES:
        return SignConvention(token)
    raise ValueError(
        f"Unsupported sign_convention {value!r}; expected one of "
        f"{', '.join(sorted(_DECLARED_VALUES))}."
    )


def is_declared(convention: SignConvention) -> bool:
    """True when the convention resolves heat-flow polarity."""
    return convention in (SignConvention.EXO_UP, SignConvention.ENDO_UP)


def inspect_header_hints(text: Any) -> Dict[str, Any]:
    """Inspect free header text for endo/exo polarity evidence.

    Evidence-only surface (PR-8 clarification 2): the returned dict is
    intended for import warnings and provenance records.  It must never
    be used to set, choose, or flip the sign convention.

    Returns a JSON-serializable dict::

        endo_token: bool      # text contains an 'endo' token
        exo_token: bool       # text contains an 'exo' token
        implied: str | None   # 'endo_up'/'exo_up' when exactly one event
                              # family plus a direction word is present,
                              # else None
    """
    lowered = str(text or "").lower()
    has_endo = "endo" in lowered
    has_exo = "exo" in lowered
    implied: str | None = None
    if has_endo != has_exo:  # exactly one event family named
        base = "endo" if has_endo else "exo"
        if re.search(r"\bup\b", lowered):
            implied = f"{base}_up"
        elif re.search(r"\bdown\b", lowered):
            implied = "exo_up" if base == "endo" else "endo_up"
    return {"endo_token": has_endo, "exo_token": has_exo, "implied": implied}


def provenance_record(
    convention: SignConvention,
    *,
    declared_by: str = "not_recorded",
) -> Dict[str, Any]:
    """Build the raw-provenance metadata block for a canonicalized dataset.

    The record makes it unambiguous whether the working signal was
    inverted and what the originally declared convention was (PR-8
    clarification 3).
    """
    declared = is_declared(convention)
    return {
        "raw_signal_convention": convention.value,
        "canonical_signal_convention": CANONICAL_SIGNAL_CONVENTION if declared else None,
        "signal_inverted_at_import": bool(declared and convention is not CANONICAL),
        "sign_convention_declared_by": str(declared_by or "not_recorded"),
    }


def apply_canonicalization(
    signal: Union[np.ndarray, Any],
    convention: SignConvention,
    *,
    declared_by: str = "not_recorded",
) -> tuple[np.ndarray, Dict[str, Any]]:
    """Canonicalize a raw thermal signal to the canonical frame.

    Returns ``(canonical_signal, provenance_record)``.  Declared
    ``ENDO_UP`` inputs are inverted exactly once; declared ``EXO_UP``
    inputs are copied unchanged; ``UNKNOWN`` inputs are returned
    unresolved (no inversion, no polarity assumption — PR-8
    clarification 1).
    """
    values = np.asarray(signal, dtype=float)
    if not is_declared(convention):
        return values, provenance_record(convention, declared_by=declared_by)
    if convention is CANONICAL:
        canonical = values.copy()
    else:
        canonical = -values
    return canonical, provenance_record(convention, declared_by=declared_by)


def label_from_direction(
    direction: str,
    convention: Union[SignConvention, str, None] = CANONICAL,
) -> str:
    """Derive an event label from a sign direction in the given frame.

    ``direction`` is the sign direction of the detected peak relative to
    the passed signal ('up' or 'down'; the tokens 'exo'/'exotherm' and
    'endo'/'endotherm' are accepted as aliases).  For ``UNKNOWN`` frames
    the label is ``'unknown'`` — scientific uncertainty is preserved, so
    callers must not present such peaks as endothermic or exothermic.
    """
    resolved = parse_declared(convention, default=CANONICAL)
    token = str(direction or "").strip().lower()
    if token in {"up", "exo", "exotherm"}:
        return _UP_LABELS[resolved]
    if token in {"down", "endo", "endotherm"}:
        return _DOWN_LABELS[resolved]
    return "unknown"


def canonical_frame_label(convention: SignConvention) -> str:
    """Human-readable description of the working signal frame."""
    if is_declared(convention):
        return "Exotherm up / Endotherm down (canonical)"
    return "Unknown polarity (endo/exo labels withheld)"


def direction_tag_from_label(label: str) -> str:
    """Compact ``direction`` tag derived from a canon event label.

    Returns ``'exo'`` / ``'endo'`` for canon-derived labels and
    ``'unknown'`` otherwise.  Deriving the serialized ``direction``
    attribute from the SAME label as ``peak_type`` makes the two fields
    structurally incapable of disagreeing (PR-8 blocker fix).
    """
    label_token = str(label or "").strip().lower()
    if label_token == "exotherm":
        return "exo"
    if label_token == "endotherm":
        return "endo"
    return "unknown"


def summarize_provenance(metadata: Any) -> Dict[str, Any]:
    """Build the serialized provenance block for result records/exports.

    Backward-safe: datasets that predate the canon (or non-thermal
    modalities) resolve to an explicit ``unknown``/``not_recorded`` state
    rather than silently inheriting the canonical frame.
    """
    meta = metadata or {}
    raw = str((meta.get("raw_signal_convention") or "")).strip().lower()
    declared = raw in {SignConvention.EXO_UP.value, SignConvention.ENDO_UP.value}
    return {
        "declared": raw if declared else SignConvention.UNKNOWN.value,
        "canonical": CANONICAL_SIGNAL_CONVENTION if declared else None,
        "inverted_at_import": bool(meta.get("signal_inverted_at_import", False)) if declared else False,
        "declared_by": str(meta.get("sign_convention_declared_by") or "not_recorded"),
    }
