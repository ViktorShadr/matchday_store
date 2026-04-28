#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --log-level "${GUNICORN_LOG_LEVEL:-info}" \
  --access-logfile - \
  --error-logfile - \
  --capture-output \
  --access-logformat '%({X-Request-ID}i)s %(h)s "%(r)s" %(s)s %(b)s %(D)sus'
