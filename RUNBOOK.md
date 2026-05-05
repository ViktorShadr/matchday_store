# Production Runbook (Matchday Store)

Этот документ фиксирует минимальную операционную процедуру для production-запуска MVP.

## 1. Pre-deploy checklist

- `DEBUG=False`
- `SECRET_KEY` длинный и случайный (50+ символов)
- корректные `ALLOWED_HOSTS`
- корректные `CSRF_TRUSTED_ORIGINS` c `https://...`
- `SITE_URL` указывает на боевой HTTPS-домен
- `CSRF_COOKIE_SECURE=True` и `SESSION_COOKIE_SECURE=True`
- `USE_X_FORWARDED_PROTO=True`, если TLS завершается на внешнем reverse proxy
- настроены SMTP-переменные (`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`)
- настроен `CACHE_URL` (общий Redis cache, чтобы rate limits работали консистентно между web-процессами)
- настроены `RATELIMIT_*` и корректный `RATELIMIT_IP_META_KEY` для reverse proxy
- включен enforce-режим CSP (`CSP_ENFORCE=True`)
- задан `SENTRY_DSN` и окружение `SENTRY_ENVIRONMENT`
- внешний reverse proxy/ingress терминирует TLS
- есть регулярный backup PostgreSQL и проверка восстановления
- определены ответственные за релиз и rollback

Для временной проверки по HTTP/IP без TLS допустимо ставить `CSRF_COOKIE_SECURE=False` и
`SESSION_COOKIE_SECURE=False`. Для боевого домена это нужно вернуть в `True`.

## 2. Deploy (Docker Compose)

1. Подготовить `.env` на базе `.env.prod`.
2. Дождаться успешного CI на целевом коммите.
3. Собрать и запустить:

```bash
docker compose up -d --build
```

Если это первый релиз после перехода на non-root runtime, разово выровнять права на volume:

```bash
docker compose run --rm --user 0:0 web sh -c "chown -R 10001:10001 /app/staticfiles /app/media"
```

4. При необходимости поднять worker:
3. При необходимости поднять worker-профиль. Он запускает Celery worker и Celery beat; beat нужен для регулярной автоотмены просроченных заказов самовывоза.

```bash
docker compose --profile worker up -d --build
```

5. Проверить состояние сервисов и healthchecks:

```bash
docker compose ps
curl -fsS http://127.0.0.1:8000/healthz/
```

## 2.1. CD Image Publishing

Workflow `.github/workflows/cd.yml` публикует production-образ в GitHub Container Registry:

- `ghcr.io/<owner>/<repo>:<branch>`
- `ghcr.io/<owner>/<repo>:<tag>` для `v*.*.*`
- `ghcr.io/<owner>/<repo>:sha-<short_sha>`

Для pull на сервере нужен доступ к GHCR и версия образа, которую планируется выкатывать. Сам деплой на конкретный хост намеренно оставлен в runbook: способ зависит от инфраструктуры сервера, TLS/reverse proxy и политики хранения `.env`.

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
