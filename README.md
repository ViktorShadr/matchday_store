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
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `STAFF_ORDER_NOTIFICATION_EMAILS` (comma-separated email сотрудников для уведомлений о новых заказах)
- `CACHE_URL` (shared Redis cache для rate limiting между несколькими worker-процессами)
- `RATELIMIT_*` (лимиты для login/registration/resend/checkout)
- `CSP_ENFORCE` (`True` для production, `False` только для временной диагностики)
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
