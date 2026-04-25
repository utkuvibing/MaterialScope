#!/bin/sh
set -eu

export MATERIALSCOPE_API_URL="${MATERIALSCOPE_API_URL:-http://127.0.0.1:${PORT:-8050}}"

exec python -m dash_app.server --host 0.0.0.0 --port "${PORT:-8050}"
