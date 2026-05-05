# Технический аудит проекта Matchday Store (28.04.2026)

## 1) Executive summary

Проект в целом выглядит как **рабочий MVP интернет-магазина на Django** с уже реализованными базовыми потоками (каталог, корзина, checkout, заказы, дашборд, email-подтверждение). По структуре код аккуратно разнесён по приложениям и слоям (`application/services/repositories/presenters`).

При этом перед production-развёртыванием на хосте есть ряд важных пунктов:

- нужно обязательно запускать с `DEBUG=False` и корректным `ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS`;
- добавить/проверить инфраструктурные меры (TLS, бэкапы, мониторинг, healthchecks, ограничения ресурсов);
- закрыть несколько security-пробелов (политика секретов, срок жизни email-токена, анти-абуз);
- формализовать runbook деплоя и отката.

---

## 2) Что именно проверено

### Статический просмотр конфигурации и кода
- `config/settings.py`
- `docker-compose.yaml`
- `Dockerfile`
- `docker/nginx/default.conf`
- `docker/web-entrypoint.sh`
- `orders/views.py`, `orders/forms.py`, `orders/services.py`, `orders/models.py`
- `store/views/views_cart.py`, `store/views/views_dashboard.py`, `store/services/cart_service.py`, `store/mixins/auth_mixins.py`
- `users/views.py`, `users/models.py`, `users/application/email_confirmation_service.py`
- `.env.example`, `.gitignore`, `README.md`

### Прогоны проверок
- `python -m py_compile $(rg --files -g '*.py' -g '!staticfiles/**')` ✅
- `python manage.py check --deploy` с временными env-переменными ✅ (получены предупреждения W009 и W021)
- `docker compose config -q` ⚠️ (в текущем окружении отсутствует бинарник `docker`)

---

## 3) Рекомендации по запуску на хосте (конкретный план)

## Вариант A (рекомендуется): Docker Compose + reverse proxy с TLS

1. **Подготовить сервер**
   - Ubuntu 22.04/24.04 LTS
   - Установить Docker Engine + Docker Compose plugin
   - Открыть firewall: `80/tcp`, `443/tcp`, `22/tcp`

2. **Секреты и env**
   - На базе `.env.example` сделать боевой `.env`.
   - Обязательно:
     - `DEBUG=False`
     - длинный случайный `SECRET_KEY` (50+ символов)
     - `ALLOWED_HOSTS=your-domain.com,www.your-domain.com`
     - `CSRF_TRUSTED_ORIGINS=https://your-domain.com,https://www.your-domain.com`
     - `SITE_URL=https://your-domain.com`
   - Не хранить `.env` в git.

3. **Деплой**
   - `docker compose up -d --build`
   - Если нужен worker:
     - `docker compose --profile worker up -d --build`

4. **После деплоя (обязательно)**
   - Проверить миграции и статику (entrypoint уже делает это автоматически).
   - Создать superuser.
   - Пройти smoke-тест: регистрация → подтверждение email → checkout → смена статусов заказа в dashboard.

5. **TLS/HTTPS**
   - Терминировать TLS на внешнем прокси (Nginx/Caddy/Traefik).
   - Проксировать в текущий nginx-контейнер или напрямую в `web`.
   - Проверить редирект HTTP→HTTPS.

6. **Эксплуатация**
   - Включить мониторинг (минимум: uptime + контейнерные логи + алерты 5xx).
   - Включить регулярные бэкапы PostgreSQL + проверка восстановления.

---

## Вариант B: Managed PaaS (Railway/Render/Fly/Hetzner managed k8s)

Если нужен быстрый запуск без DevOps-команды:

- вынести БД в managed PostgreSQL;
- хранить `media` в S3-совместимом хранилище (чтобы не терять файлы при пересоздании контейнера);
- задать env-секреты через секрет-менеджер платформы;
- настроить отдельный процесс/службу под Celery worker при необходимости.

---

## 4) Найденные проблемы и риски

## 🔴 Критические / High

1. **Небезопасный дефолт `DEBUG=True` в settings.**  
   Риск: случайный запуск в debug-режиме в проде (утечки stack trace/чувствительных данных).  
   Где: `config/settings.py`.

2. **Email-токен подтверждения без срока жизни (TTL).**  
   Риск: старые ссылки могут оставаться валидными неопределённо долго при утечке почты/логов.  
   Где: `users/models.py`, `users/views.py`, `users/application/email_confirmation_service.py`.

3. **Приложение запускается в контейнере от root-пользователя.**  
   Риск: повышенные последствия при RCE/компрометации контейнера.  
   Где: `Dockerfile`, `docker/web-entrypoint.sh`.

## 🟠 Средние / Medium

4. **Нет явных healthcheck’ов для `web` и `nginx` сервисов в compose.**  
   Риск: оркестратор не видит «поломанный, но запущенный» контейнер; сложнее авто-восстановление.  
   Где: `docker-compose.yaml`.

5. **Не хватает anti-abuse на подтверждение email по IP/UA.**  
   Сейчас есть cooldown на пользователя (60 сек), но нет ограничителей на уровне IP / endpoint throttling.  
   Где: `users/application/email_confirmation_service.py`, `users/views.py`.

6. **Часть security-заголовков не зафиксирована явно в settings.**  
   Есть `X_FRAME_OPTIONS`, `SECURE_CONTENT_TYPE_NOSNIFF`, secure cookies при `DEBUG=False`, но стоит явно задать ещё `SECURE_REFERRER_POLICY`, `SECURE_CROSS_ORIGIN_OPENER_POLICY` и др.  
   Где: `config/settings.py`.

## 🟡 Низкие / Low

7. **Нет формализованного runbook на деплой/rollback/restore.**  
   Риск: долгий MTTR при инциденте.  
   Где: частично покрыто `README.md`, но не как операционный документ.

8. **Не зафиксирована стратегия ротации секретов и паролей БД/SMTP.**  
   Риск: накопление технического долга и security debt.

---

## 5) Конкретные действия (приоритетный backlog)

## Sprint 1 (обязательно перед production)

1. Изменить дефолт `DEBUG` на `False` в settings (локально включать только env-переменной).
2. Ввести TTL для `email_token` (например, 24 часа) + хранить время генерации токена.
3. Перевести контейнер приложения на non-root user.
4. Добавить health endpoint (`/healthz`) и healthcheck в compose для `web`/`nginx`.
5. Зафиксировать production checklist (env, TLS, backup, smoke-test).

## Sprint 2 (желательно)

6. Добавить rate limiting (например, `django-ratelimit`) на чувствительные endpoints.
7. Добавить расширенные security headers и зафиксировать CSP-политику.
8. Подключить Sentry/аналог для ошибок и алертов.
9. Внедрить регулярный backup + тест восстановления (не только бэкап).

---

## 6) Минимальный production checklist (коротко)

- [ ] `DEBUG=False`
- [ ] `SECRET_KEY` длинный и случайный
- [ ] корректные `ALLOWED_HOSTS`
- [ ] корректные `CSRF_TRUSTED_ORIGINS`
- [ ] `SITE_URL` = боевой HTTPS-домен
- [ ] HTTPS + редирект с HTTP
- [ ] Бэкап БД по расписанию + проверка restore
- [ ] Мониторинг uptime/ошибок
- [ ] Создан superuser, отключены дефолтные/тестовые учётки
- [ ] Пройден end-to-end smoke-flow заказа

---

## 7) Вывод

Проект уже близок к production-ready для MVP-нагрузки, но перед запуском на «боевом» хосте **нужно закрыть минимум 3 high-риска** (безопасные defaults, TTL токенов, non-root runtime) и добавить базовую эксплуатационную обвязку (healthchecks, backup/monitoring/runbook). После этого можно безопасно запускать пилот.
