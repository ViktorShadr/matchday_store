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

По умолчанию поднимаются `nginx`, `web` и `db`.

## Запуск worker при необходимости

Celery не обязателен для MVP: уведомления умеют уходить через sync fallback. Если нужен фоновой worker:

```bash
docker compose --profile worker up --build
```

Это дополнительно поднимет `redis` и `worker`.

## Стек runtime

- `nginx` принимает HTTP на `localhost:8000`
- `nginx` раздает `/static/` и `/media/`
- `nginx` проксирует приложение в `gunicorn`
- `web` применяет миграции, собирает статику и запускает Django
- `db` хранит данные
- `worker` и `redis` поднимаются только через профиль `worker`

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

Для логирования:

- `LOG_LEVEL` (`INFO` по умолчанию)
- `LOG_JSON` (`True` в production, `False` в debug)
- `GUNICORN_LOG_LEVEL` (`info` по умолчанию)

В production каждый ответ включает `X-Request-ID`; тот же идентификатор прокидывается в Celery-задачи и попадает в логи.

## Проверка перед деплоем

- создать суперпользователя
- проверить `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL`
- проверить отправку email
- проверить, что `nginx` отдает `/static/` и проксирует запросы в `web`
- пройти сценарий: checkout -> ready -> paid -> issued

Подробный production runbook: [RUNBOOK.md](/home/viktor-shadrin/PycharmProjects/matchday_store/RUNBOOK.md:1)
