#!/bin/sh
set -e

# Remove stale prometheus multiprocess metric files from previous container
# lifecycle so they are not double-counted after a restart.
if [ -n "${PROMETHEUS_MULTIPROC_DIR}" ]; then
    find "${PROMETHEUS_MULTIPROC_DIR}" -maxdepth 1 -type f -delete
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --log-level "${GUNICORN_LOG_LEVEL:-info}" \
  --config /app/docker/gunicorn.conf.py \
  --access-logfile - \
  --error-logfile - \
  --capture-output \
  --access-logformat '%({X-Request-ID}i)s %(h)s "%(r)s" %(s)s %(b)s %(D)sus'
