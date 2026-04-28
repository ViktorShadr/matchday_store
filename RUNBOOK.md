# Production Runbook (Matchday Store)

Этот документ фиксирует минимальную операционную процедуру для production-запуска MVP.

## 1. Pre-deploy checklist

- `DEBUG=False`
- `SECRET_KEY` длинный и случайный (50+ символов)
- корректные `ALLOWED_HOSTS`
- корректные `CSRF_TRUSTED_ORIGINS` c `https://...`
- `SITE_URL` указывает на боевой HTTPS-домен
- настроены SMTP-переменные (`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`)
- настроен `CACHE_URL` (общий Redis cache, чтобы rate limits работали консистентно между web-процессами)
- настроены `RATELIMIT_*` и корректный `RATELIMIT_IP_META_KEY` для reverse proxy
- включен enforce-режим CSP (`CSP_ENFORCE=True`)
- задан `SENTRY_DSN` и окружение `SENTRY_ENVIRONMENT`
- внешний reverse proxy/ingress терминирует TLS
- есть регулярный backup PostgreSQL и проверка восстановления
- определены ответственные за релиз и rollback

## 2. Deploy (Docker Compose)

1. Подготовить `.env` на базе `.env.prod`.
2. Собрать и запустить:

```bash
docker compose up -d --build
```

Если это первый релиз после перехода на non-root runtime, разово выровнять права на volume:

```bash
docker compose run --rm --user 0:0 web sh -c "chown -R 10001:10001 /app/staticfiles /app/media"
```

3. При необходимости поднять worker:

```bash
docker compose --profile worker up -d --build
```

4. Проверить состояние сервисов и healthchecks:

```bash
docker compose ps
curl -fsS http://127.0.0.1:8000/healthz/
```

## 3. Smoke test (обязательно после релиза)

1. Регистрация пользователя.
2. Подтверждение email по ссылке из письма.
3. Добавление товара в корзину и checkout.
4. Проверка заказа в личном кабинете.
5. Смена статусов заказа в staff dashboard.
6. Проверка, что email-уведомления отправляются.

## 4. Rollback

1. Вернуть предыдущий образ/коммит.
2. Перезапустить сервисы:

```bash
docker compose up -d --build
```

3. Проверить доступность `/healthz/`.
4. Повторить smoke test на критическом пути (вход, корзина, checkout).

## 5. Backup / restore

Минимум: ежедневный backup PostgreSQL + периодическая проверка восстановления.

Использовать скрипты проекта:

```bash
./ops/db/backup.sh
```

Проверка восстановления на временную БД:

```bash
./ops/db/restore_verify.sh /path/to/postgres_YYYYMMDDTHHMMSSZ.sql.gz
```

Шаблон cron для automation: [ops/db/cron.example](/home/viktor-shadrin/PycharmProjects/matchday_store/ops/db/cron.example:1)
