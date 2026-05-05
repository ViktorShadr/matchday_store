FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && pip install --no-cache-dir poetry \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false

RUN poetry install --only main --no-interaction --no-ansi --no-root

COPY . .

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home /home/app --shell /usr/sbin/nologin app \
    && mkdir -p /app/logs /app/staticfiles /app/media \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["sh", "/app/docker/web-entrypoint.sh"]
