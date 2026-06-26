# Matchday Store

[![CI/CD](https://github.com/ViktorShadr/matchday_store/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/ViktorShadr/matchday_store/actions/workflows/ci-cd.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.x-37814A)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

🇷🇺 Russian version: [README.ru.md](README.ru.md)

---

## Overview

Matchday Store is a production-oriented Django MVP for a football club merchandise store.

The project models a realistic ecommerce workflow with transactional checkout, stock reservation, account recovery, persistent notification delivery, staff tooling, operational monitoring, S3 backups, and production-style deployment infrastructure.

The main engineering focus is not CRUD functionality, but consistency, reliability, observability, security, and maintainability under real operational conditions.

---

## Highlights

- Transaction-safe checkout with stock reservation
- Idempotent order processing
- Concurrency protection with `select_for_update`
- Async email pipeline with Celery and a persistent notification outbox
- Structured JSON logging with request tracing
- Dockerized production deployment
- GitHub Actions CI/CD pipeline
- Background job processing with retries
- Staff dashboard with notification logs, manual resend, and printable order views
- Safe warehouse deletion guards for products, variants, and categories used by active orders
- Account password reset flow with rate limiting and production-safe links
- S3 backup workflow for PostgreSQL and media files with retention policy
- 390+ automated tests including concurrency and email-delivery scenarios

---

## Features

### Ecommerce & Checkout

- Product catalog with categories, variants, SKU support, pricing, stock visibility, and product images
- Guest and authenticated carts with session merge on login
- User registration, email confirmation, profile management, and password reset
- Pickup checkout workflow
- Reservation-based stock handling
- Duplicate-submit protection with idempotent checkout flow
- Manual payment workflow synchronized with order statuses
- Order lifecycle transitions with staff-controlled issue flow
- Automatic release of reserved stock on cancellation or expiration

### Staff & Operations

- Warehouse/staff dashboard
- Order filtering and moderation workflows
- Product, variant, category, and image management for the warehouse catalog
- Safe delete protection for warehouse entities that participate in active orders or reservations
- Payment status management
- Order detail workspace with staff guidance, transition history, and notification timeline
- Manual notification resend/retry workflow for managers
- Printable staff order view for pickup operations
- Internal order notes and transition history
- Role-based staff access with Django permissions

### Infrastructure & Reliability

- Dockerized runtime environment
- Nginx reverse proxy + Gunicorn application server
- Redis + Celery background processing
- Dedicated email worker queue
- DB-backed order notification outbox
- Idempotent email delivery with deduplication and attempts tracking
- Healthchecks and operational scripts
- S3-compatible backup workflow for PostgreSQL dumps and media archives
- Daily, weekly, and monthly backup tiers with automated retention cleanup
- GitHub Actions CI/CD pipeline
- Automated Docker image publishing to GHCR

### Security & Stability

- Transactional stock consistency
- Race-condition protection
- Rate limiting for critical endpoints
- Rate-limited password reset requests
- CSP and secure cookie configuration
- CSRF protection
- Expiring hashed guest order access tokens
- Safe redirect validation
- Sensitive-data masking in logs
- Environment-based production settings

### Observability

- Structured JSON logging
- Request tracing with `X-Request-ID`
- Prometheus metrics with `/metrics` endpoint
- Grafana dashboards with Loki log aggregation
- Audit logging
- Celery request propagation
- Order notification delivery logs with task IDs, attempts, recipient snapshots, and sanitized errors
- Health endpoints
- Ecommerce analytics integration

---

# Architecture

## High-Level Architecture

```mermaid
flowchart LR
    Browser --> Nginx
    Nginx --> Django[Gunicorn + Django]
    Django --> PostgreSQL[(PostgreSQL)]
    Django --> Media[(Media Volume)]
    Django --> Redis[(Redis)]
    Redis --> Celery[Celery Workers]
    Beat[Celery Beat] --> Redis
    Celery --> SMTP[SMTP Provider]
    Backup[Backup Script] --> PostgreSQL
    Backup --> Media
    Backup --> S3[(S3 Object Storage)]
    Django -. metrics .-> Prometheus
    Celery -. metrics .-> Prometheus
    Prometheus --> Grafana
```

The project uses a modular Django monolith architecture with explicit separation between:

- HTTP layer
- application workflows
- domain services
- repositories
- query services
- presenters
- infrastructure concerns

The public surface is intentionally server-rendered for simplicity and operational reliability, while critical business workflows are isolated in service-layer logic.

---

## Why a Modular Monolith?

The project intentionally uses a modular monolith instead of microservices because:

- transactional consistency is easier to guarantee,
- infrastructure remains operationally simple,
- local development is significantly faster,
- deployment complexity stays manageable,
- business workflows remain easier to reason about.

Background workloads are isolated through Celery queues rather than separate deployable services.

---

# Engineering Challenges

## Preventing Overselling

One of the main technical challenges was guaranteeing stock consistency during concurrent checkout attempts.

The solution combines:

- `transaction.atomic()`
- `select_for_update()`
- conditional `F()` updates
- deterministic lock ordering
- idempotent checkout tokens
- database constraints
- concurrency tests using `TransactionTestCase`

This ensures that parallel checkout requests cannot oversell inventory.

---

## Reliable Checkout Flow

The checkout system was designed to tolerate:

- page refreshes,
- duplicate form submits,
- network retries,
- parallel browser requests,
- asynchronous email failures.

The final workflow uses scoped idempotency keys and transaction-aware reservation logic to safely return an already-created order instead of creating duplicates.

---

## Background Processing Reliability

Email delivery and scheduled maintenance tasks run asynchronously through Celery.

Order notification events are persisted as `OrderNotificationLog` outbox records before Celery delivery. Delivery tasks claim records with database locking, skip already sent or already sending records, persist task IDs, attempts and sanitized errors, and support manager-triggered retries from the dashboard.

Special attention was paid to:

- retry safety,
- exponential backoff,
- transient SMTP handling,
- queue isolation,
- idempotent notification delivery,
- failure visibility through logs, dashboard status, and Prometheus alerting.

---

# Tech Stack

| Area | Technologies |
| --- | --- |
| Backend | Python 3.12, Django 5.2 |
| Database | PostgreSQL 16 |
| Async | Celery 5.x, Redis 7 |
| Infrastructure | Docker, Docker Compose, Nginx, Gunicorn |
| CI/CD | GitHub Actions, GHCR |
| Monitoring | Structured logs, Prometheus, Grafana, Loki, healthchecks |
| Security | django-csp, django-ratelimit, CSRF protection |
| Frontend | Django Templates, Bootstrap, Vanilla JS |
| Testing | Django TestCase, TransactionTestCase |

---

# Project Structure

```text
.
├── analytics/
├── config/
├── docs/
├── docker/
├── ops/
├── orders/
├── payments/
├── store/
├── support/
├── users/
├── .github/workflows/
├── docker-compose.yaml
├── docker-compose.prod.yml
├── Dockerfile
└── pyproject.toml
```

---

# Key Engineering Decisions

## Service Layer Instead of Fat Views

Business workflows are isolated inside dedicated services:

- `CheckoutService`
- `OrderCancellationService`
- `OrderIssueService`
- `PaymentWorkflowService`
- `DashboardOrderFlowService`

Views remain thin and handle only HTTP concerns.

This keeps critical workflows testable and independent from Django request objects.

---

## Explicit Reservation Model

The system separates:

- physical stock (`quantity`)
- reserved stock (`reserved_quantity`)

This models a realistic pickup-order warehouse flow:

- checkout reserves items,
- cancellation releases reservation,
- order issue consumes physical inventory.

---

## Safe Warehouse Deletes

Warehouse catalog entities are protected from unsafe deletion:

- categories cannot be deleted while their products are used by active orders,
- products cannot be deleted while they participate in active orders,
- variants cannot be deleted while active reservations still exist.

Deletion checks run inside transactions and surface manager-facing errors instead of silently breaking active warehouse workflows.

---

## Request-Scoped Logging

Every request receives an `X-Request-ID`.

The same identifier propagates through:

- Django logs,
- Celery tasks,
- Grafana (via Loki).

Production logs support JSON formatting with masking of passwords, tokens, cookies, emails, and phone numbers.

---

## Queue Separation

The Compose stack separates workloads into:

- `web`
- `worker`
- `email-worker`
- `beat`

This avoids email delivery slowing down application processing and makes operational troubleshooting simpler.

---

## Persistent Notification Outbox

Order emails are not treated as fire-and-forget side effects.

The notification pipeline stores delivery intent and status in `OrderNotificationLog` records:

- customer events: `created`, `cancelled`, `ready`, `paid`,
- staff event: `staff_created`,
- recipient snapshots and message snapshots,
- delivery status: `pending`, `sending`, `sent`, `failed`,
- Celery task ID, attempts count, sanitized error message,
- idempotency key per order, event, and recipient type.

This gives staff visibility into email delivery and allows manual retry without duplicating already delivered notifications.

---

## S3 Backup Workflow

Operational backups are handled by `ops/backup/s3_backup.sh`.

The workflow creates and uploads:

- PostgreSQL dumps,
- media file archives.

It supports `daily`, `weekly`, and `monthly` backup tiers, loads secrets from `ops/backup/s3_backup.env` or `BACKUP_ENV_FILE`, and removes old objects according to the retention policy:

| Tier | Retention |
| --- | --- |
| daily | 14 days |
| weekly | 8 weeks |
| monthly | 6 months |

The repository includes:

- `docs/backup_s3.md` for setup, verification, and restore instructions,
- `ops/backup/s3_backup.env.example` for required variables,
- `ops/backup/cron.example` for scheduled execution.

---

# Checkout & Stock Flow

```text
Cart
   ↓
Checkout Submit
   ↓
Order + Payment
   ↓
Stock Reservation
   ↓
Staff Processing
   ↓
Order Issued
   ↓
Physical Stock Reduced
```

Stock lifecycle:

| Event | quantity | reserved_quantity |
| --- | ---: | ---: |
| Checkout placed | unchanged | increases |
| Order cancelled | unchanged | decreases |
| Order issued | decreases | decreases |

Critical checkout protections include:

- atomic database transactions,
- row locking,
- conditional updates,
- idempotency keys,
- duplicate-submit handling,
- guest active-order limits by email, phone, session, and IP to protect stock reservations,
- transactional cleanup of purchased cart items.

---

# Security

The project includes multiple production-oriented security controls:

- CSRF protection
- Secure cookies
- CSP with nonce-based scripts
- Rate limiting for auth and checkout endpoints
- Safe redirect validation
- Image upload validation
- Password reset tokens generated through Django's built-in token flow
- Public password reset links built from `SITE_URL`
- Environment-driven production settings
- Sensitive-data masking in logs
- Docker non-root runtime
- HSTS-ready configuration
- Nginx request limits
- Anti-overselling database constraints

---

# Observability & Monitoring

Operational visibility was treated as a first-class concern.

Implemented features include:

- request tracing with `X-Request-ID`
- structured JSON logging
- audit logger for business events
- Prometheus metrics endpoint (`/metrics`)
- Grafana dashboards with Loki log aggregation
- Docker healthchecks
- Celery task metadata logging
- dashboard-visible order notification attempts
- sensitive-data masking
- ecommerce analytics events

Planned improvements:

- Prometheus metrics
- Grafana dashboards
- operational KPI tracking

---

# Account Recovery

Password reset is implemented through custom Django auth views and templates.

The flow includes:

- `/users/password-reset/`
- `/users/password-reset/done/`
- `/users/password-reset/confirm/<uidb64>/<token>/`
- `/users/password-reset/complete/`

Requests are rate-limited by IP and submitted email. Reset emails use `SITE_URL`, so production deployments must set it to the public HTTPS origin.

---

# Background Tasks

Celery uses Redis as both broker and result backend.

Current asynchronous workflows include:

- registration emails
- customer order notifications
- staff new-order notifications
- persistent notification outbox delivery
- manager-triggered notification resend
- support notifications
- scheduled order auto-cancellation
- configurable product thumbnail generation
- email retries with exponential backoff

Queues are separated between general tasks and email delivery tasks.

---

# Testing

The project currently contains 390+ automated Django tests.

Covered areas include:

- checkout validation
- stock reservation
- cancellation flows
- idempotent checkout
- payment synchronization
- concurrency handling
- dashboard permissions
- password reset flow and rate limiting
- warehouse delete protection for active orders and reservations
- notification outbox, deduplication, retry, and manual resend
- printable staff order views
- email retry logic
- logging and observability
- security validation
- smoke end-to-end flows

Run tests locally:

```bash
poetry run python manage.py test
```

Or inside Docker:

```bash
docker compose exec web python manage.py test
```

---

# CI/CD

GitHub Actions pipeline includes:

- Black
- isort
- flake8
- migration validation
- Django system checks
- PostgreSQL + Redis test environment
- Docker image build
- GHCR publishing
- SSH-based production deployment

Deployment flow:

```text
Push to main
    ↓
GitHub Actions
    ↓
Run tests
    ↓
Build Docker image
    ↓
Push to GHCR
    ↓
Deploy to production server
```

---

# Local Development

## Clone Repository

```bash
git clone https://github.com/ViktorShadr/matchday_store.git
cd matchday_store
```

## Configure Environment

```bash
cp .env.example .env
```

## Start Application

```bash
docker compose up --build -d
```

Application:

```text
http://localhost:8000
```

## Create Superuser

```bash
docker compose exec web python manage.py createsuperuser
```

## Run Tests

```bash
docker compose exec web python manage.py test
```

---

# Deployment

Local deployment:

```bash
docker compose up --build -d
```

Production deployment:

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

---

# Backups

Configure S3-compatible backups:

```bash
cp ops/backup/s3_backup.env.example ops/backup/s3_backup.env
chmod 600 ops/backup/s3_backup.env
```

Run a manual backup:

```bash
BACKUP_ENV_FILE=ops/backup/s3_backup.env ./ops/backup/s3_backup.sh daily
```

For production scheduling and restore verification, see `docs/backup_s3.md`.

---

# Future Improvements

- Online payment providers
- DRF-based public API
- Warehouse/ERP integrations
- Delivery providers
- Object storage + CDN for serving media
- Prometheus + Grafana monitoring
- Coverage reporting
- Telegram/SMS notifications
- Sales analytics dashboard

---

# Production-Oriented Approach

This project was built not only as a feature demo, but as an operationally maintainable backend service.

Special attention was paid to:

- consistency under concurrency,
- failure handling,
- retry safety,
- observability,
- deployment automation,
- secure defaults,
- maintainable architecture.

The goal was to build a compact but realistic ecommerce MVP that demonstrates backend engineering practices commonly found in production systems.
