# Matchday Store MVP

Django MVP интернет-магазина клубной атрибутики с каталогом, корзиной, checkout по самовывозу, ручной оплатой и staff-dashboard для обработки заказов.

## Что уже входит в MVP

- каталог и карточки товаров
- корзина для гостя и авторизованного пользователя
- регистрация, логин, подтверждение email
- checkout только для самовывоза
- создание заказа из корзины со списанием остатков
- история заказов пользователя
- dashboard для обработки заказов и ручной отметки оплаты
- email-уведомления по ключевым событиям заказа

## Локальный запуск через Docker Compose

1. Скопируйте `.env.example` в `.env` и заполните секреты и email-настройки.
2. Запустите приложение:

```bash
docker compose up --build
```

3. Откройте `http://localhost:8000`.

По умолчанию поднимаются `nginx`, `web`, `db` и `redis`.

## Запуск worker при необходимости

Celery worker не обязателен для MVP: уведомления умеют уходить через sync fallback. Если нужен фоновой worker:

```bash
docker compose --profile worker up --build
```

Это дополнительно поднимет `worker` (redis уже запущен как shared cache/queue backend).

## CI/CD

GitHub Actions:

- CI: `.github/workflows/ci.yml`
  - Poetry metadata/lock check
  - Black, isort, flake8
  - проверка миграций
  - `manage.py check`
  - Django tests на PostgreSQL 16 и Redis 7
  - Docker image build
- CD: `.github/workflows/cd.yml`
  - сборка и публикация Docker-образа в GitHub Container Registry (`ghcr.io`) на `main`, `master`, `v*.*.*` tags и ручной запуск

Локальная проверка перед push:

```bash
poetry check --lock
find config store users orders payments delivery -name '*.py' -exec .venv/bin/black --check --target-version py312 {} \;
.venv/bin/black --check --target-version py312 manage.py
poetry run isort --check-only config store users orders payments delivery manage.py
poetry run flake8 config store users orders payments delivery manage.py --exclude=.git,.venv,__pycache__,staticfiles,media,*/migrations/* --max-line-length=119 --extend-ignore=E203,W503
poetry run python manage.py makemigrations --check --dry-run
poetry run python manage.py check
```

## Стек runtime

- `nginx` принимает HTTP на `localhost:8000`
- `nginx` раздает `/static/` и `/media/`
- `nginx` проксирует приложение в `gunicorn`
- `web` применяет миграции, собирает статику и запускает Django
- `db` хранит данные
- `redis` используется как shared cache и брокер очередей
- `worker` поднимается только через профиль `worker`

Основные файлы:

- entrypoint: [docker/web-entrypoint.sh](/home/viktor-shadrin/PycharmProjects/matchday_store/docker/web-entrypoint.sh:1)
- nginx config: [docker/nginx/default.conf](/home/viktor-shadrin/PycharmProjects/matchday_store/docker/nginx/default.conf:1)

## Переменные окружения

Обязательные:

- `SECRET_KEY`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`

Рекомендуемые:

- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `SITE_URL`
- `EMAIL_CONFIRMATION_TOKEN_TTL_HOURS`
- `DEFAULT_FROM_EMAIL`
- `STORE_SUPPORT_EMAIL`
- `STORE_BRAND_NAME`
- `STORE_PICKUP_LOCATION_NAME`
- `STORE_PICKUP_ADDRESS`
- `STORE_PICKUP_HOURS`
- `STORE_PICKUP_PHONE`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `STAFF_ORDER_NOTIFICATION_EMAILS` (comma-separated email сотрудников для уведомлений о новых заказах)
- `CACHE_URL` (shared Redis cache для rate limiting между несколькими worker-процессами)
- `RATELIMIT_*` (лимиты для login/registration/resend/checkout)
- `CSP_ENFORCE` (`True` для production, `False` только для временной диагностики)
- `METRIKA_ENABLED`, `METRIKA_COUNTER_ID` для Яндекс.Метрики в production
- `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE`

Для логирования:

- `LOG_LEVEL` (`INFO` по умолчанию)
- `LOG_JSON` (`True` в production, `False` в debug)
- `GUNICORN_LOG_LEVEL` (`info` по умолчанию)

Для временного деплоя по HTTP/IP без TLS:

- `ALLOWED_HOSTS=37.1.80.117`
- `CSRF_TRUSTED_ORIGINS=http://37.1.80.117`
- `SITE_URL=http://37.1.80.117`
- `CSRF_COOKIE_SECURE=False`
- `SESSION_COOKIE_SECURE=False`

Для production за HTTPS-доменом:

- `CSRF_TRUSTED_ORIGINS=https://your-domain.example`
- `SITE_URL=https://your-domain.example`
- `CSRF_COOKIE_SECURE=True`
- `SESSION_COOKIE_SECURE=True`
- `USE_X_FORWARDED_PROTO=True`, если TLS завершается на внешнем reverse proxy

В production каждый ответ включает `X-Request-ID`; тот же идентификатор прокидывается в Celery-задачи и попадает в логи.

## Яндекс.Метрика

Интеграция изолирована в `analytics`: настройки читаются из env, base template вызывает один template tag, а ecommerce payload передается через безопасный JSON (`json_script`) и статический loader `static/js/metrika.js`.

Метрика загружается только если одновременно выполнены условия:

- `DEBUG=False`
- `METRIKA_ENABLED=True`
- `METRIKA_COUNTER_ID` заполнен числовым ID счетчика

Где менять счетчик:

- production `.env`: `METRIKA_COUNTER_ID=12345678`
- не менять ID в шаблонах и JS вручную

Как отключить:

- поставить `METRIKA_ENABLED=False`
- или оставить `DEBUG=True` в local/dev, тогда счетчик не загрузится даже при заполненном ID

Что отправляется в ecommerce `dataLayer`:

- просмотр товара: `detail`
- добавление в корзину после успешного server-side POST: `add`
- открытие checkout: `checkout` / `begin_checkout`
- успешный заказ: `purchase` с `order.number`, `total_amount`, SKU, category, quantity и line totals

PII покупателя (`email`, `phone`, ФИО) в ecommerce events не передается.

Проверка:

1. Включить Ecommerce в настройках счетчика Яндекс.Метрики, data container: `dataLayer`.
2. На production открыть страницу с параметром `?_ym_debug=2`.
3. Проверить в debug panel события `detail`, `add`, `checkout`, `purchase`.
4. В DevTools убедиться, что есть один запрос `https://mc.yandex.ru/metrika/tag.js` и нет дублей `ym(..., "init", ...)`.

Consent compatibility:

- сейчас `METRIKA_REQUIRE_CONSENT=False`, счетчик грузится сразу после server-side gating;
- для будущего consent banner можно поставить `METRIKA_REQUIRE_CONSENT=True`, тогда loader дождется `localStorage.cookie_consent=accepted` или события `matchday:cookie-consent-changed`.

CSP:

- при активной Метрике Django settings добавляют домены Яндекса в `script-src`, `img-src`, `connect-src`, `child-src`, `frame-src`, `frame-ancestors`;
- WebVisor/click maps требуют возможности iframe-просмотра страниц из интерфейса Яндекса, поэтому в режиме активной Метрики проект не добавляет `X-Frame-Options: DENY` и полагается на `frame-ancestors` CSP;
- при отключенной Метрике прежний `X-Frame-Options: DENY` остается.

## Backup и restore check

- backup script: [ops/db/backup.sh](/home/viktor-shadrin/PycharmProjects/matchday_store/ops/db/backup.sh:1)
- restore verify: [ops/db/restore_verify.sh](/home/viktor-shadrin/PycharmProjects/matchday_store/ops/db/restore_verify.sh:1)
- cron шаблон: [ops/db/cron.example](/home/viktor-shadrin/PycharmProjects/matchday_store/ops/db/cron.example:1)

## Проверка перед деплоем

- создать суперпользователя
- проверить `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL`
- проверить отправку email
- проверить, что `nginx` отдает `/static/` и проксирует запросы в `web`
- пройти сценарий: checkout -> ready -> paid -> issued

Подробный production runbook: [RUNBOOK.md](/home/viktor-shadrin/PycharmProjects/matchday_store/RUNBOOK.md:1)
