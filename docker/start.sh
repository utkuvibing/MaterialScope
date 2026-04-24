#!/bin/sh
set -eu

exec python -m dash_app.server --host 0.0.0.0 --port "${PORT:-8050}"
