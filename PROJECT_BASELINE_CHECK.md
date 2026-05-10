# Project Baseline Check

Дата: 2026-05-09
Проект: Matchday Store

## 1. Команды и окружение

- Runtime: Python 3.12.3 в локальном `.venv`, Python 3.12.13 в Docker image.
- Управление зависимостями: Poetry 2.3.2.
- Основной локальный запуск по README: `docker compose up --build`.
- Текущий Docker Compose уже поднят: `nginx`, `web`, `db`, `redis`, `worker`, `beat`.
- PostgreSQL доступен внутри compose-сети как `db`; host-запуск команд, которым нужна БД, получает предупреждение по `DB_HOST=db`.

## 2. Результаты проверок

- `.venv/bin/python manage.py check`: OK, issues не найдено.
- `.venv/bin/python manage.py makemigrations --check --dry-run`: миграции не требуются; есть предупреждение о недоступности host `db` при запуске вне Docker.
- `docker compose run --rm --no-deps --user root -v "$PWD:/app" web python manage.py test --verbosity 2`: OK.
- Тесты: 227 total, 226 passed, 1 skipped.
- Skipped: `WorkerExecutionSmokeE2ETest`, включается через `RUN_SMOKE_E2E=1`.

## 3. Локальный старт

- `docker compose ps`: все основные сервисы подняты; `db`, `nginx`, `web`, `redis` healthy.
- `http://127.0.0.1:8000/healthz/`: 200, `{"status": "ok"}`.
- `http://127.0.0.1:8000/`: 401 через nginx из-за global Basic Auth.
- Прямо внутри `web` Django отвечает:
  - `/`: 200.
  - `/products/`: 200.
  - `/cart/`: 200.
  - `/checkout/`: redirect to login.
  - `/dashboard/`, `/dashboard/orders/`, `/dashboard/stock/`: redirect to login.

## 4. Checkout

- Основные файлы:
  - `orders/views.py`
  - `orders/forms.py`
  - `orders/services.py`
  - `orders/templates/orders/checkout.html`
  - `orders/templates/orders/checkout_success.html`
- Checkout требует авторизованного пользователя и подтвержденный email.
- Есть idempotency token в сессии.
- Есть rate limit на POST checkout.
- Заказ создается как pickup/manual payment.
- Остатки резервируются через `reserved_quantity`, физическое списание выполняется при выдаче.
- В checkout есть технический блок `Важно`, который нужно заменить на коммерческие условия.
- Success page уже показывает данные самовывоза из `STORE_PICKUP_*`.

## 5. Каталог и карточка товара

- Основные файлы:
  - `store/views/views_product.py`
  - `store/queries/catalog_queries.py`
  - `store/presenters/catalog_presenters.py`
  - `store/templates/main_page/product_list.html`
  - `store/templates/main_page/product_details.html`
  - `store/templates/main_page/_product_card.html`
- В каталоге есть поиск, категории и сортировка.
- Фильтров по размеру, наличию и цене пока нет.
- Карточка товара показывает галерею, наличие, цену, выбор варианта и описание.
- В шаблонах уже используются `short_description` и `old_price`, но в модели `Product` таких полей пока нет.
- Реального SKU-поля нет; snapshot SKU сейчас строится из id варианта.

## 6. Staff Dashboard Заказов

- Основные файлы:
  - `store/views/views_dashboard.py`
  - `store/queries/dashboard_queries.py`
  - `store/presenters/dashboard_presenters.py`
  - `store/templates/dashboard/orders.html`
  - `store/templates/dashboard/order_detail.html`
- Список заказов фильтруется по fulfillment/status-группам.
- Поиск сейчас по номеру заказа и email.
- Фильтра по оплате, телефону, дате и сумме пока нет.
- Detail показывает состав, статусы, сумму, получателя, телефон, самовывоз, issued timestamp, staff guidance и историю переходов.
- Комментарий клиента, отдельный email, кликабельный телефон, pickup deadline, внутренние заметки и причина отмены пока не выведены.

## 7. Склад

- Основные файлы:
  - `store/templates/dashboard/warehouse.html`
  - `store/templates/dashboard/product_manage.html`
  - `store/queries/dashboard_queries.py`
  - `store/queries/warehouse_manage_queries.py`
  - `store/forms.py`
  - `store/application/warehouse_crud.py`
- В warehouse есть поиск, категория, фильтр по остатку, сортировка.
- Список склада показывает агрегированный физический остаток `Sum(variants__quantity)`.
- Резерв и доступно к продаже в списке не показаны.
- Карточка управления товаром показывает варианты и поле физического остатка.
- Формы уже запрещают уменьшать физический остаток ниже `reserved_quantity`.
- Активные заказы, которые держат резерв, в UI склада пока не показаны.

## 8. Email Flow

- Основные файлы:
  - `orders/application/order_notification_service.py`
  - `orders/tasks.py`
  - `users/application/email_confirmation_service.py`
  - `users/tasks.py`
- Заказные уведомления покрывают события `created`, `cancelled`, `ready`, `paid`.
- Staff-уведомление о новом заказе содержит контакты клиента, позиции и комментарий.
- Есть Celery dispatch и sync fallback.
- В текстах заказных писем еще встречается generic `Matchday Store`.
- Текущий `.env` не задает `STORE_PICKUP_*`, поэтому используются defaults из `config/settings.py`.

## 9. Зафиксированные P0 Наблюдения Для Следующего Шага

- Global Basic Auth включен в `docker/nginx/default.conf` для всего storefront, кроме `/healthz/`.
- Footer содержит `support@matchday-store.com` и `Ежедневно: 10:00 — 19:00`.
- Settings defaults для самовывоза: `пн-пт с 10:00 до 16:00`, `сб-вс выходной`.
- Fixture `store/fixtures/store_catalog.json` содержит товары Barcelona, Real Madrid, Manchester United, Juventus, Arsenal, Liverpool.
- Checkout template содержит внутренние UX-формулировки в покупательском интерфейсе.
