#!/usr/bin/env bash
set -euo pipefail
: "${RENDER_EXTERNAL_HOSTNAME:?Render must supply its external hostname}"
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-$RENDER_EXTERNAL_HOSTNAME}"
python backend/manage.py migrate --noinput
python backend/manage.py createcachetable
python backend/manage.py check --deploy
exec gunicorn --chdir backend config.wsgi:application --bind "0.0.0.0:${PORT:-10000}" --workers 2 --timeout 120 --access-logfile - --error-logfile -
