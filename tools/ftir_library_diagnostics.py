#!/usr/bin/env python3
"""Developer diagnostics: spectral reference library path (FTIR / Raman / XRD).

Prints and appends NDJSON to ``.cursor/debug-d4f4ca.log`` (session d4f4ca) for debug workflows.

Usage:
  python tools/ftir_library_diagnostics.py
  python tools/ftir_library_diagnostics.py --modality RAMAN --json

Environment (see also ``core/library_cloud_client.py`` and ``core/reference_library.py``):

- ``MATERIALSCOPE_LIBRARY_CLOUD_URL`` / legacy ``THERMOANALYZER_LIBRARY_CLOUD_URL``
- ``MATERIALSCOPE_LIBRARY_CLOUD_ENABLED`` / legacy (empty = enabled; ``0``/``false`` disables)
- ``MATERIALSCOPE_LIBRARY_DEV_CLOUD_AUTH`` — local trial token override for cloud auth
- ``MATERIALSCOPE_LIBRARY_HOSTED_ROOT`` — backend hosted catalog root (server-side); client uses cloud URL only
- ``MATERIALSCOPE_LIBRARY_MIRROR_ROOT`` — offline package mirror for ``ReferenceLibraryManager``

Literature compare uses ``/v1/results/.../literature`` and external providers; it does **not** use
``/v1/library/search/ftir`` — so literature can succeed while spectral library matching fails.

**Checklist — FTIR cloud library healthy**

1. Client (Dash / ``analysis_run`` host): set ``MATERIALSCOPE_LIBRARY_CLOUD_URL`` to the backend base URL
   (same host as ``/v1/library/auth/token``). Leave ``MATERIALSCOPE_LIBRARY_CLOUD_ENABLED`` unset or ``1``/``true``.
2. License: trial or activated license (or ``MATERIALSCOPE_LIBRARY_DEV_CLOUD_AUTH=1`` for local dev token override).
3. Backend: process must serve ``/v1/library/search/ftir``; hosted root must contain ``manifest.json`` and at least
   one **active** FTIR dataset (``HostedLibraryCatalog.live_provider_count("FTIR") > 0``), or cloud search returns
   rows from embedded ranking only when references exist.
4. Offline fallback: set ``MATERIALSCOPE_LIBRARY_MIRROR_ROOT`` and ``ReferenceLibraryManager.sync()`` FTIR packages
   (e.g. ``openspecy_ftir_core``) so ``count_installed_candidates("FTIR") > 0``.
5. Re-run this script after changing env or syncing mirrors; optionally run
   ``pytest tests/test_batch_runner.py -k ftir`` to validate batch behavior.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEBUG_LOG = PROJECT_ROOT / ".cursor" / "debug-d4f4ca.log"
SESSION_ID = "d4f4ca"


def _log_ndjson(payload: dict) -> None:
    payload = {**payload, "sessionId": SESSION_ID, "timestamp": int(time.time() * 1000)}
    line = json.dumps(payload, ensure_ascii=False)
    DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
    with DEBUG_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--modality",
        default="FTIR",
        help="FTIR, RAMAN, or XRD (default: FTIR).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the diagnostics payload as JSON to stdout (no human summary).",
    )
    parser.add_argument(
        "--skip-health-probe",
        action="store_true",
        help="Skip HTTP GET /health (offline scripting).",
    )
    args = parser.parse_args()

    load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

    from core.library_combined_bootstrap import sanitize_library_path_env_vars
    from core.library_cloud_client import reset_library_cloud_client

    for line in sanitize_library_path_env_vars():
        print(line, file=sys.stderr, flush=True)
    reset_library_cloud_client()

    from core.spectral_library_diagnostics import collect_spectral_library_runtime_diagnostics

    snap = collect_spectral_library_runtime_diagnostics(
        analysis_type=str(args.modality),
        include_health_probe=not args.skip_health_probe,
    )

    summary = {
        "hypothesisId": "diagnostic-tool",
        "location": "tools.ftir_library_diagnostics:main",
        "message": "FTIR library path static/runtime snapshot",
        "data": snap,
    }
    _log_ndjson(summary)

    if args.json:
        print(json.dumps(snap, indent=2, ensure_ascii=False))
        print(f"# NDJSON appended to: {DEBUG_LOG}", file=sys.stderr)
        return

    probe = snap.get("cloud_health_probe") or {}
    status = snap.get("reference_library_status") or {}
    ctx = snap.get("library_context") or {}

    print("=== Spectral reference library diagnostics ===")
    print(f"  modality: {snap.get('modality')}")
    print(f"  MATERIALSCOPE_LIBRARY_CLOUD_URL (raw env): {snap.get('raw_cloud_url_env')!r}")
    print(f"  effective cloud URL (client): {snap.get('effective_cloud_url')!r}")
    print(f"  get_library_cloud_client().configured: {snap.get('cloud_client_configured')}")
    print(f"  get_library_cloud_client().enabled_by_env: {snap.get('cloud_client_enabled_by_env')}")
    print(f"  health_probe: {probe}")
    print(f"  cloud last_error (snip): {str(snap.get('cloud_last_error') or '')[:200]!r}")
    print(f"  ReferenceLibraryManager.status()['library_mode']: {status.get('library_mode')}")
    print(f"  library_context()['library_mode']: {ctx.get('library_mode')}")
    print(f"  installed candidate rows (sum entry_count): {snap.get('installed_candidate_count')}")
    print(f"  effective hosted root (resolve_hosted_root): {snap.get('effective_hosted_root')}")
    print(f"  HostedLibraryCatalog.root: {snap.get('hosted_catalog_root_used')}")
    print(f"  hosted manifest exists: {snap.get('hosted_manifest_exists')}")
    print(f"  hosted live_provider_count: {snap.get('hosted_live_provider_count')}")
    print(f"  hosted load_entries count: {snap.get('hosted_load_entries_count')}")
    print(f"  hosted missing_modalities (FTIR,RAMAN,XRD): {snap.get('hosted_missing_modalities')}")
    print("  batch resolution order (see core.batch_runner fallback):")
    for row in snap.get("batch_resolution_order") or []:
        print(f"    - {row}")
    print(f"  NDJSON appended to: {DEBUG_LOG}")


if __name__ == "__main__":
    main()
