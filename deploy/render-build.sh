#!/usr/bin/env bash
set -euo pipefail
python -m pip install -r backend/requirements-lock.txt
python -m pip install 'gunicorn==23.0.0'
# Schema/cache setup runs at startup, not during a secret-bearing build.
python backend/manage.py collectstatic --noinput
