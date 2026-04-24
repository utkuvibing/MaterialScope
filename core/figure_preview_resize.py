"""Downscale PNG bytes for lightweight previews (Slice 6).

If Pillow is missing or the payload is not a valid PNG, returns the original bytes.
"""

from __future__ import annotations

import io


def maybe_downscale_png_to_max_edge(png_bytes: bytes, max_edge: int) -> bytes:
    """If max(width, height) > max_edge, resize proportionally so the long edge is max_edge."""
    if max_edge < 1 or not png_bytes:
        return png_bytes
    try:
        from PIL import Image
    except ImportError:
        return png_bytes
    try:
        src = io.BytesIO(png_bytes)
        im = Image.open(src)
        im.load()
    except Exception:
        return png_bytes
    w, h = im.size
    if max(w, h) <= max_edge:
        return png_bytes
    scale = max_edge / float(max(w, h))
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.LANCZOS  # type: ignore[attr-defined]
    resized = im.resize((nw, nh), resample)
    out = io.BytesIO()
    if resized.mode == "P":
        resized = resized.convert("RGBA")
    resized.save(out, format="PNG", optimize=True)
    return out.getvalue()
