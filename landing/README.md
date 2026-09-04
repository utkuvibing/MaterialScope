# MaterialScope — landing page & waitlist

Public marketing site for MaterialScope with a waitlist endpoint. Deliberately
self-contained: nothing in this directory is imported by the product, and the
product is not imported here.

## Run

```bash
python -m landing.server --host 127.0.0.1 --port 8090
# → http://127.0.0.1:8090
```

Dependencies are the same FastAPI/uvicorn already required by the project.

## Layout

```
landing/
  server.py      FastAPI app factory: serves web/ + POST /api/waitlist
  store.py       WaitlistStore — append-only JSONL file + dedupe (swap-out seam)
  gen_traces.py  Regenerates web/traces.js from sample_data/ (real curves)
  web/           Static site: index.html, landing.css, landing.js, traces.js
  web/fonts/     Self-hosted IBM Plex Sans/Mono woff2 (OFL — see LICENSE.txt)
```

`data/` (created at runtime) holds `waitlist.jsonl` and is gitignored —
submissions never enter the repository.

## Waitlist contract

`POST /api/waitlist`

```json
{ "email": "you@lab.org", "role": "research", "company": "" }
```

- `201` new entry · `200` `{"status": "already" | "discarded"}` — duplicates are
  idempotent; the `company` field is a honeypot and is never stored.
- `422` invalid email · `429` rate-limited (6/min/IP) · `503` storage failure.

`POST /api/waitlist/form` accepts the same fields form-encoded and renders a
minimal HTML result page — the no-JavaScript fallback for the signup form.

To persist somewhere real (database, Airtable, CRM webhook), replace
`landing.store.WaitlistStore` with an object exposing `join(email, role) ->
"joined" | "already"`; no other code changes.

## Hero traces

`web/traces.js` is generated from the repository's sample datasets
(`python -m landing.gen_traces`) so every plotted curve and annotation is real
material data — the page displays no fabricated measurements.

## Accessibility & motion

Semantic landmarks, visible focus rings, labelled form fields with
`role=status` feedback, and full `prefers-reduced-motion` support (entrance
animations, trace drawing, and parallax all disable). Light/dark themes mirror
the Dash app tokens (`dash_app/assets/style.css`).
