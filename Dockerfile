# Stage 1: builder — compile dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

# Build-time system dependencies only
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only dependency files first for layer caching
COPY pyproject.toml poetry.lock ./

# Install pinned poetry, export deps, install them to /install prefix
RUN pip install --no-cache-dir "poetry==2.3.2" "poetry-plugin-export==1.9.0" \
    && poetry export --without-hashes --without dev -f requirements.txt -o requirements.txt \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: production image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Runtime-only system dependency
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Non-root user matching compose user: 10001
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home /home/app --shell /usr/sbin/nologin app \
    && mkdir -p /app/logs /app/staticfiles /app/media \
    && chown -R app:app /app

COPY --chown=app:app . .

USER app

EXPOSE 8000

CMD ["sh", "/app/docker/web-entrypoint.sh"]
