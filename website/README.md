# MaterialScope landing page

This folder contains the static landing page for MaterialScope — a self-contained
`index.html` (embedded CSS + vanilla JS, no build step) that describes the project,
its techniques, workflow, and install instructions.

## Preview locally

```bash
python -m http.server 8080 --directory website
# → http://127.0.0.1:8080
```

## Deploy

Any static host works (GitHub Pages, Netlify, Vercel, Cloudflare Pages). Just point
the host at this `website/` folder; the page has no external runtime dependencies
other than Google Fonts (with system-font fallbacks).

## Maintenance notes

- Colors and fonts intentionally mirror the Dash app theme
  (`dash_app/theme.py` and `dash_app/assets/style.css`): IBM Plex Sans/Mono and
  the warm ivory/gold accent palette.
- The page supports light/dark mode automatically via `prefers-color-scheme`,
  with a manual toggle; the choice is stored in `localStorage`.
- Feature copy is kept intentionally generic so it stays accurate as the
  project evolves; re-check the modality cards if capabilities change.
