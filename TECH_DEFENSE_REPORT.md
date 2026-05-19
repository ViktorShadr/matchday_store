# Техническая защита проекта Matchday Store MVP

Документ подготовлен по фактическому коду проекта в директории `matchday_store` (Django 5.2).  
Дата анализа: 2026-05-19.

## 1. Краткое резюме проекта

### Что это за сервис
`Matchday Store` — монолитный Django-сервис интернет-магазина клубной атрибутики (MVP) с витриной, корзиной, checkout, заказами, ручной оплатой, staff-dashboard и каналом обращений в поддержку.

### Какую бизнес-задачу решает
- Продажа клубного мерча через web-интерфейс.
- Обработка заказов в сценарии **самовывоза**.
- Управление складскими остатками и резервами без oversell.
- Операционная обработка заказов сотрудниками (готов/выдан/отменен, оплата, заметки).

### Для кого предназначен
- Клиенты магазина (гость/зарегистрированный пользователь).
- Сотрудники/модераторы склада и заказов.
- Администратор (Django admin + superuser функции).

### Основные пользовательские сценарии
- Каталог → карточка товара → корзина → checkout → подтверждение заказа.
- Регистрация, подтверждение email, авторизация, профиль, история заказов.
- Отмена заказа клиентом (в допустимых статусах).
- Обращение в поддержку через форму.
- Staff: обработка заказов и управление складом через dashboard.

---

## 2. Общая архитектура

### Django-приложения и их зоны ответственности

- `store`:
  - каталог, категории, варианты товара, изображения;
  - корзина и cart-операции;
  - legal/CMS-страницы (`Page`, `InfoCard`);
  - staff dashboard (warehouse/orders UI).
- `orders`:
  - сущности заказа, позиции заказа, журнал переходов;
  - checkout orchestration;
  - отмена/выдача/авто-отмена;
  - staff workflow по статусам заказа.
- `payments`:
  - модель платежа;
  - синхронизация `Order.payment_status` через workflow + fallback signals.
- `users`:
  - кастомный пользователь (email как login);
  - регистрация/логин/профиль;
  - подтверждение email.
- `support`:
  - форма обращений и хранение заявок;
  - фоновые уведомления сотрудников.
- `analytics`:
  - интеграция Яндекс.Метрики;
  - ecommerce events (`detail/add/checkout/purchase`).
- `config`:
  - settings, middleware, Celery, logging, healthcheck, sentry init.

### Связи между приложениями

- `orders.OrderItem.product_variant -> store.ProductVariant`.
- `payments.Payment.order -> orders.Order`.
- `store.Cart.user -> users.User`.
- `orders.Order.user -> users.User` (nullable для guest orders).
- `support.SupportRequest.user -> users.User` (nullable).

### Внешние сервисы/компоненты

- PostgreSQL (`django.db.backends.postgresql`) — `config/settings.py`.
- Redis:
  - Celery broker/result backend;
  - cache (включая ratelimit backend при `CACHE_URL`).
- Celery (`worker`, `email-worker`, `beat`).
- SMTP (`django.core.mail.backends.smtp.EmailBackend`).
- Gunicorn (`docker/web-entrypoint.sh`).
- Nginx reverse proxy (`docker/nginx/default.conf`).
- Docker Compose (dev/prod файлы).
- GitHub Actions CI/CD (`.github/workflows/ci-cd.yml`).
- Sentry (опционально через `SENTRY_DSN`).

### Общий поток данных (high-level)

1. Клиент → `nginx` → `gunicorn`/Django.
2. Django читает/пишет бизнес-данные в PostgreSQL.
3. При checkout/order/support/user-email событиях Django ставит Celery задачи.
4. `email-worker` отправляет email через SMTP.
5. `beat` периодически запускает авто-отмену просроченных pickup-заказов.
6. Staff-dashboard и admin работают поверх той же БД.

---

## 3. Структура проекта

Ниже ключевые директории и файлы (по коду и роли в системе).

- `config/`
  - `settings.py`: окружение, apps, middleware, db, cache, celery, security, csp, logging.
  - `urls.py`: root routing, `healthz`, admin, include app urls.
  - `middleware.py`: `RequestIdMiddleware`.
  - `celery.py`: app + request-id propagation в Celery headers/context.
  - `email_delivery.py`: retry-политика email и классификация SMTP ошибок.
  - `health.py`: readiness endpoint (DB probe).
  - `logging_utils.py`: JSON/human logging + masking PII/secret.

- `store/`
  - `models.py`: Category/Product/ProductVariant/ProductImage/Page/InfoCard/Cart/CartItem.
  - `views/`: витрина, корзина, legal pages, dashboard.
  - `services/`: cart service/exceptions/validators, template display adapters.
  - `application/`: `CartContextResolver`, `WarehouseCrudService`.
  - `queries/`: catalog + dashboard query services.
  - `presenters/`: UI-oriented preparation данных для шаблонов.
  - `management/commands/create_moderator_group.py`.
  - `signals.py`: merge carts on login.
  - `templates/`: витрина и dashboard UI.

- `orders/`
  - `models.py`: Order, OrderItem, Address, OrderStatusTransition.
  - `services.py`: checkout/cancel/issue/auto-cancel/manual-payment business logic.
  - `application/`: status policy, dashboard flow, notification service, checkout session service.
  - `tasks.py`: order emails + staff order emails + auto-cancel periodic task.
  - `views.py`: checkout и checkout success.
  - `management/commands/backfill_stock_reservations.py`.

- `payments/`
  - `models.py`: Payment (+ unique idempotency_key).
  - `application/payment_workflow.py`: controlled update path with explicit sync.
  - `services/payment_status_service.py`: order payment status resolution.
  - `signals.py`: fallback sync for direct ORM/admin edits.

- `users/`
  - `models.py`: custom User (email login), email token fields/methods.
  - `views.py`: login/registration/profile/order-history/email-confirm.
  - `forms.py`: registration/login/profile/avatar validation.
  - `application/email_confirmation_service.py`: token lifecycle + queue dispatch.
  - `tasks.py`: confirmation/welcome emails.
  - `admin.py`: user admin + moderator group admin UX.

- `support/`
  - `models.py`: support requests + email delivery flags.
  - `forms.py`: honeypot + personal data consent.
  - `views.py`: support form + success page.
  - `application/support_notification_service.py`: enqueue/schedule.
  - `tasks.py`: support notification email with retry/failure persistence.

- `analytics/`
  - `metrika.py`: config/events builders, session queue.
  - `templatetags/metrika_tags.py`, `templates/analytics/_yandex_metrika.html`.
  - `static/js/metrika.js` (инициализация и consent-aware loading).

- Infra/DevOps
  - `Dockerfile`, `docker/web-entrypoint.sh`, `docker/nginx/default.conf`.
  - `docker-compose.yaml`, `docker-compose.prod.yml`.
  - `.github/workflows/ci-cd.yml`.
  - `ops/db/backup.sh`, `restore_verify.sh`, `cron.example`.

---

## 4. Подробное описание моделей

## 4.1 `store.Category`
- Файл: `store/models.py`.
- Назначение: справочник категорий каталога.
- Поля: `name(unique)`, `description`, timestamps.
- Связи: `Product.category` (1:N).
- Ограничения/индексы: unique on `name`.
- Методы: `__str__`, `get_absolute_url`.
- Использование: витрина, фильтрация каталога, warehouse dashboard, admin.

## 4.2 `store.Product`
- Назначение: карточка товара.
- Поля: `name`, `short_description`, `description`, `old_price`, `material`, `care_instructions`, `size_guide`, `category`, `is_on_sale`, timestamps.
- Связи: `variants`, `images`.
- Ограничения: валидация `old_price > 0` через `MinValueValidator`.
- Методы: `__str__`, `get_absolute_url`.
- Использование: catalog list/detail, dashboard CRUD, checkout snapshots через `OrderItem`.

## 4.3 `store.ProductVariant`
- Назначение: SKU-level вариант товара (size/color/price/stock).
- Поля: `product`, `sku`, `size`, `color`, `price`, `quantity`, `reserved_quantity`, `image`, timestamps.
- Связи: cart items, order items.
- Ограничения:
  - unique `(product, size, color)`;
  - unique non-blank `sku`;
  - check `reserved_quantity <= quantity`;
  - check `price > 0`.
- Индексы: `sku db_index`, FK indexes.
- Методы: `available_quantity` property.
- Использование: cart validation, checkout reserve/issue, warehouse stock.

## 4.4 `store.ProductImage`
- Назначение: изображения товара.
- Поля: `product`, `image`, `alt_text`, `is_primary`, `created_at`.
- Использование: gallery/preview in catalog/detail/cart/dashboard.

## 4.5 `store.Page`
- Назначение: CMS-страницы (privacy/terms/return/offer).
- Поля: `slug(unique)`, `title`, `lead`, `content`, `is_published`, timestamps, `updated_by`.
- Использование: legal pages rendering, nav links via context processor.

## 4.6 `store.InfoCard`
- Назначение: информационные карточки на главной.
- Поля: `title`, `text`, `icon`, `sort_order`, `is_published`, timestamps.
- Использование: `MainView` и home template.

## 4.7 `store.Cart`
- Назначение: корзина пользователя/сессии.
- Поля: `user(nullable)`, `session_key(nullable, db_index)`, timestamps.
- Ограничения:
  - unique user cart (`user is not null`);
  - unique session cart (`user is null`).
- Методы: `total_price`, `total_items`.
- Использование: cart flows, checkout source.

## 4.8 `store.CartItem`
- Назначение: позиция корзины.
- Поля: `cart`, `product_variant`, `quantity>=1`, timestamps.
- Ограничение: unique `(cart, product_variant)`.
- Метод: `total_price`.
- Использование: cart page, checkout order lines.

## 4.9 `orders.Address`
- Назначение: адреса пользователя.
- Поля: recipient/phone/country/city/street etc, `is_default`, timestamps.
- Использование: в текущем checkout-сценарии (pickup MVP) **в коде не найдено активного использования**.

## 4.10 `orders.Order`
- Назначение: агрегат заказа.
- Поля:
  - идентификация: `number(unique)`, `user(nullable)`, `recipient_name`, `email`, `phone`;
  - бизнес-статусы: `status`, `payment_status`, `fulfillment_status`;
  - fulfillment: `delivery_method`, `delivery_address`, `pickup_point_code`;
  - суммы: `subtotal_amount`, `delivery_amount`, `discount_amount`, `total_amount`, `currency`;
  - служебные: `customer_comment`, `staff_note`, `source_cart_id`,
    `confirmed_at`, `paid_at`, `issued_at`, `cancelled_at`, timestamps.
- Индексы/ограничения: unique `number`, FK indexes.
- Использование: checkout, dashboard, user order history, notifications.

## 4.11 `orders.OrderStatusTransition`
- Назначение: аудит переходов статусов.
- Поля: `order`, `transition_type`, `from_value`, `to_value`, `changed_by`, `created_at`.
- Методы: `log_if_changed` (no-op если from==to).
- Использование: cancellation, dashboard status/payment updates.

## 4.12 `orders.OrderItem`
- Назначение: snapshot позиции заказа.
- Поля: `order`, `product_variant(nullable)`, snapshot fields (`product_name_snapshot`, `sku_snapshot`, `size_snapshot`, `color_snapshot`), `unit_price`, `quantity`, `line_total`, timestamps.
- Использование: order detail, notifications, metrika purchase event.

## 4.13 `payments.Payment`
- Назначение: попытка/факт платежа.
- Поля: `order`, `provider`, `provider_payment_id`, `idempotency_key(unique)`, `status`, `amount`, `currency`, `raw_request`, `raw_response`, `failure_reason`, `paid_at`, `refunded_amount`, timestamps.
- Индексы/ограничения: unique `idempotency_key`.
- Использование: checkout manual payment, dashboard payment updates, status sync.

## 4.14 `users.User`
- Назначение: кастомный пользователь.
- Отличия: `username=None`, `USERNAME_FIELD=email`.
- Поля: email(unique), profile fields, avatar, `is_email_confirmed`, `email_token`, `email_token_created_at`, `confirmation_email_last_sent_at`.
- Методы: `generate_email_token`, `confirm_email`.
- Использование: auth, order visibility, support association.

## 4.15 `support.SupportRequest`
- Назначение: тикет из формы поддержки.
- Поля: `name/email/phone/subject/message`, `status`, `user`, `staff_notes`, `email_sent`, `email_error`, timestamps.
- Использование: support form + admin processing + email notification workflow.

---

## 5. Подробное описание бизнес-логики

Ниже ключевые сценарии по формату: вход → участники → шаги → изменения → ошибки → edge cases.

## 5.1 Регистрация
- Вход: `users/views.py:CustomRegistrationView` (`/users/registration/`).
- Участники: `UserRegistrationForm`, `EmailConfirmationService`.
- Шаги:
  1. Валидация формы (email unique, passwords).
  2. `form.save()` создаёт `User`.
  3. В транзакции: при необходимости `is_active=True`.
  4. `schedule_confirmation_for_new_user()` генерирует токен и ставит отправку email в `transaction.on_commit`.
- Изменения: `users_user` + token/timestamp fields.
- Ошибки: rate-limit, queue dispatch fail (аккаунт создаётся, письмо может не уйти).
- Edge: сообщение пользователю различается в зависимости от успеха постановки задачи.

## 5.2 Подтверждение email
- Вход: `EmailConfirmationView` (`/users/confirm-email/<token>/`).
- Участники: `EmailConfirmationService.is_token_expired`, `User.confirm_email`.
- Шаги: поиск user по token → проверка TTL → confirm + auto-login → попытка отправки welcome email.
- Изменения: `is_email_confirmed=True`, `is_active=True`, token null.
- Ошибки: invalid/expired token.
- Edge:
  - rollout-safe legacy: если `email_token_created_at` отсутствует, token считается валидным.

## 5.3 Авторизация
- Вход: `CustomLoginView` (`/users/login/`), `CustomLogoutView`.
- Шаги: перед login сохраняется `_pre_login_session_key`, чтобы после `user_logged_in` объединить корзины.
- Безопасность: ratelimit по IP и credential key; CSRF стандартный middleware.

## 5.4 Просмотр каталога
- Вход: `MainView`, `ProductListView`, `ProductDetailsView`.
- Участники: `CatalogQueryService`, `ProductCardPresenter`.
- Логика: фильтрация/сортировка/поиск/stock filters, pagination, breadcrumbs, metrika detail event.
- Edge: сортировка по цене опирается на min доступной цены варианта.

## 5.5 Выбор товара/варианта
- В карточке товара:
  - если 1 доступный вариант: CTA “В корзину”;
  - если несколько: CTA “Выбрать размер/вариант” (detail flow).
- Реализовано в `ProductCardPresenter.enrich`.

## 5.6 Корзина
- Вход: `AddToCartView`, `UpdateCartView`, `RemoveFromCartView`, `CartView`.
- Участники: `CartValidator`, `CartService`, `CartContextResolver`.
- Логика:
  - validate variant_id/quantity;
  - `transaction.atomic` + `select_for_update` variant;
  - проверка sale flag и `available_quantity`.
- Изменения: `Cart`, `CartItem`.
- Ошибки: кастомные exceptions с HTTP status mapping.
- Edge:
  - safe redirect URL validation (`url_has_allowed_host_and_scheme`);
  - JSON vs redirect режим по заголовкам.

## 5.7 Оформление заказа (checkout)
- Вход: `CheckoutView` (`/checkout/`), POST.
- Участники: `CheckoutSessionService`, `CheckoutService`.
- Ключевые шаги в `CheckoutService.create_order_from_cart`:
  1. Сбор `payment_idempotency_key` из `checkout_token` + user/session scope.
  2. Pre-lock lookup existing payment (idempotent replay).
  3. Guard: `STOCK_RESERVE_MODE_ENABLED`, лимит активных неоплаченных заказов, per-SKU max qty.
  4. Transaction:
     - optional `select_for_update` user row;
     - повторный existing payment lookup;
     - lock cart items (`select_for_update`);
     - lock variants (`select_for_update`);
     - построение order lines, удаление недоступных items из cart;
     - создание `Order`, `OrderItem`, manual `Payment`;
     - резерв остатков (`reserved_quantity += qty`);
     - очистка корзины оформленных позиций;
     - schedule notifications via `on_commit`.
  5. IntegrityError fallback: повторный lookup existing payment и доменная ошибка.
- Изменения: `Order`, `OrderItem`, `Payment`, `ProductVariant.reserved_quantity`, `CartItem`.
- Ошибки: `CheckoutError`.
- Edge:
  - stale checkout token;
  - repeat submit/parallel submit;
  - empty cart after race;
  - недоступные позиции удаляются, доступные оформляются.

## 5.8 Резервирование остатков
- `OrderStockReservationService.reserve_variant`.
- Атомарный UPDATE с условием `quantity >= reserved + qty`.
- Гарантия инварианта на уровне модели и SQL update filter.

## 5.9 Изменение статусов заказа (staff)
- Вход: dashboard endpoints:
  - `/dashboard/orders/<id>/status/`
  - `/dashboard/orders/<id>/payment/`
- Участники: `DashboardOrderFlowService`, `OrderStatusPolicy`, `ManualPaymentUpdateService`, `OrderIssueService`, `OrderCancellationService`.
- Логика:
  - валидные переходы только по policy;
  - финальные состояния (issued/cancelled) неизменяемы;
  - `issued` требует successful payment;
  - для `issued` сначала consume reserved stock, затем status apply;
  - логирование transitions и audit logger.

## 5.10 Отмена заказа
- Вход:
  - user: `/users/orders/<id>/cancel/`;
  - staff: dashboard status -> `cancelled`.
- Участник: `OrderCancellationService.cancel_order`.
- Логика:
  - lock order;
  - ownership check (для user-flow);
  - state guards;
  - lock variants из order items;
  - release reserve;
  - cancel manual payments;
  - set `status/fulfillment/payment = cancelled`, `cancelled_at`, transitions, notification.
- Идемпотентность: повторная отмена уже cancelled заказа безопасна (no double release).

## 5.11 Возврат резерва
- Происходит в `release_variant_reservation` при cancellation.
- SQL guard `reserved_quantity__gte=quantity` защищает от ухода в минус.

## 5.12 Отправка email
- Order/user/support уведомления идут через Celery tasks с общей retry-политикой.
- Постановка задач обычно через `transaction.on_commit`.
- При permanent SMTP rejection задачи не ретраятся (возвращают `False`), при transient — `NotificationDeliveryError` для autoretry.

## 5.13 Staff/manager-сценарии
- Warehouse dashboard:
  - CRUD product/category/variant/image;
  - stock update with validation `quantity >= reserved_quantity`;
  - publish/unpublish товара.
- Orders dashboard:
  - фильтры/поиск;
  - статус, оплата, staff note;
  - status transitions timeline.

## 5.14 Складская логика
- Три величины:
  - физический остаток: `quantity`;
  - резерв: `reserved_quantity`;
  - доступно: `quantity - reserved_quantity`.
- При checkout: только reserve.
- При issued: физический остаток уменьшается, резерв уменьшается.
- При cancel: резерв уменьшается.

## 5.15 Защита от гонок/повторов
- `transaction.atomic + select_for_update` в checkout/cart/merge/cancel/issue/payment update.
- Idempotency key в `Payment` + session checkout token.
- Повторная submission обработана на UI session уровне и на DB unique уровне.

## 5.16 Idempotency
- Используется:
  - `Payment.idempotency_key (unique)`;
  - `CheckoutService.build_checkout_idempotency_key()`;
  - `CheckoutSessionService._checkout_processed` marker.
- В коде не найдено HTTP-level idempotency-key header middleware/API.

---

## 6. Описание сервисного слоя

### `orders/services.py`

- `CheckoutService`:
  - отвечает за end-to-end checkout orchestration;
  - вход: `CheckoutContext`, `cleaned_data`, optional token;
  - выход: `Order`;
  - трогает: cart/order/order_items/payment/product_variant reserve;
  - исключения: `CheckoutError`.
  - плюс: сильная транзакционная целостность, idempotency, race-handling.
  - минус: файл большой, высокая когнитивная нагрузка.

- `OrderStockReservationService`:
  - reserve/release/issue;
  - плюс: атомарные SQL conditions;
  - минус: логика ошибок зависит от актуальности in-memory variant.

- `OrderCancellationService`:
  - доменные правила отмены, release reserve, cancel payments, status transitions;
  - плюс: идемпотентность, ownership check.

- `OrderIssueService`:
  - списание physical stock из резерва;
  - плюс: чёткие preconditions по статусам/оплате.

- `OrderAutoCancellationService`:
  - batch auto-cancel pickup orders по business-day deadline.

- `ManualPaymentUpdateService`:
  - staff update payment status + payment record create/update + paid_at sync + paid notification.

### `orders/application/*`

- `DashboardOrderFlowService`: прикладной orchestration staff-flow (status/payment).
- `OrderStatusPolicy`: чистая policy-переходов и status-key mapping.
- `OrderNotificationService`: enqueue/schedule order emails.
- `CheckoutSessionService`: session token и доступ к success page.
- `CheckoutContext`: request-independent context for checkout.

### `store/services/cart_service.py`
- cart operations with locks/atomic.
- плюсы: DI репозиториев, кастомные доменные errors, конкурентная устойчивость.
- слабое место: смешаны доменная логика и presentation-oriented details (`get_cart_items_with_details`).

### `store/application/cart_context.py`
- resolve cart per request, merge carts on login.
- плюс: request-level cache + transaction-safe merge.
- риск: merge logic сложна и требует аккуратного regression coverage.

### `payments/application/payment_workflow.py`
- централизованный путь изменения платежей;
- подавляет signal sync и вызывает explicit sync 1 раз.

### `payments/services/payment_status_service.py`
- стратегия priority:
  - refunded > succeeded > latest status;
  - cancelled order фиксирует payment_status=cancelled.

### `users/application/email_confirmation_service.py`
- token lifecycle, cooldown, on_commit dispatch.

### `support/application/support_notification_service.py`
- enqueue + fallback запись ошибки в БД при проблеме очереди.

---

## 7. Описание views / CBV / FBV

## 7.1 Orders views

- `CheckoutView` (`/checkout/`):
  - доступ: гость/юзер;
  - использует: `CheckoutForm`, `CheckoutService`, `CheckoutSessionService`;
  - шаблон: `orders/checkout.html`;
  - side effects: order/payment/reserve/cart cleanup/notifications;
  - безопасность: CSRF, ratelimit, stale token check, processed token replay.

- `CheckoutSuccessView` (`/checkout/success/<id>/`):
  - доступ: только владелец user-order или guest order из той же сессии;
  - защита: `CheckoutSessionService.can_access_order`.

## 7.2 Cart views

- `AddToCartView`, `UpdateCartView`, `RemoveFromCartView`:
  - POST-only;
  - валидация входа через `CartValidator`;
  - доступ: гость/юзер;
  - side effects: изменения Cart/CartItem;
  - безопасность: CSRF + safe redirect + exception mapping.

- `CartView`:
  - рендер корзины и summary.

## 7.3 Catalog/Legal views
- `MainView`, `ProductListView`, `ProductDetailsView`, `CategoryListView`, `CategoryDetailView`.
- `LegalPageView` family: публикация legal pages через `Page` (`is_published=True`) иначе 404.

## 7.4 Dashboard views (`store/views/views_dashboard.py`)
- доступ: `ModeratorRequiredMixin`.
- покрывают stock/orders CRUD/updates.
- side effects: статусы заказов, payment updates, note updates, stock updates.

## 7.5 Users views

- `CustomLoginView` / `CustomRegistrationView` / `CustomLogoutView`.
- `ResendOwnConfirmationEmailView`.
- `ProfileDetailView`/`ProfileUpdateView`/`ProfileDeleteView`.
- `UserOrderListView` / `UserOrderDetailView` / `UserOrderCancelView`.
- `EmailConfirmationView`.
- Безопасность:
  - ratelimit для login/registration/resend;
  - custom CSRF failure redirect;
  - permission guards на чужие профили и чужие заказы.

## 7.6 Support views
- `SupportRequestView`:
  - ratelimit;
  - сохраняет `SupportRequest`;
  - enqueue notification on commit.
- `SupportSuccessView`: статическая страница результата.

---

## 8. Описание форм

- `orders.forms.CheckoutForm`:
  - поля: recipient_name/email/phone/customer_comment;
  - валидация: garbage-name, phone normalization to `+digits`, auth user email lock.
  - бизнес-цель: корректные данные покупателя и минимизация мусора.

- `store.forms.ProductVariantForm`:
  - валидация price>0, trimmed sku, `quantity >= reserved_quantity`.

- `store.forms.ProductImageForm`:
  - validate extension/content-type/size (<=5MB) и реальную image-сигнатуру через PIL.

- `store.forms.VariantStockForm`:
  - запрет уменьшить physical stock ниже reserve.

- `users.forms.UserRegistrationForm`:
  - уникальность email.

- `users.forms.UserProfileForm` + `AvatarImageField`:
  - avatar type/size validation;
  - phone normalization E.164 (`phonenumber_field`).

- `users.forms.ProfileDeleteConfirmForm`:
  - подтверждение пароля для удаления аккаунта.

- `support.forms.SupportRequestForm`:
  - honeypot `website`;
  - required `personal_data_consent`;
  - limits subject/message.

---

## 9. Presenters / selectors / helpers / utils

### Presenters
- `store/presenters/catalog_presenters.py`:
  - `ProductCardPresenter`: CTA/stock/image/price presentation.
  - `ProductDetailsPresenter`: detail payload.
  - `PermissionPresenter`: роль пользователя для шаблонов.
- `store/presenters/dashboard_presenters.py`:
  - `DashboardOrderPresenter`: status/payment badges + staff guidance.
  - `WarehouseProductPresenter`: stock labels/summary.
- `store/presenters/warehouse_ui_presenters.py`: текстовые UI context blocks.
- `store/presenters/cart_presenters.py`: cart item presentation.

### Query/selector-style services
- `store/queries/catalog_queries.py`: фильтрация/сортировка каталога.
- `store/queries/dashboard_queries.py`: warehouse/order dashboards + active reservation items.
- `store/queries/warehouse_manage_queries.py`: product manage context.

### Helpers/utils
- `store/site_contacts.py`: pickup/store contact builders.
- `config/logging_utils.py`: masking PII/secrets, JSON formatter.
- `config/email_delivery.py`: SMTP permanent/transient classifier.
- `analytics/metrika.py`: ecommerce event builders + empty-values cleanup.

### Оценка
- Плюс: presentation/query logic вынесена из views.
- Минус: часть “services” в `store/services/template_filters.py` по сути thin wrappers и могут быть объединены/упрощены.

---

## 10. Celery и фоновые задачи

### Задачи
- `orders.tasks`:
  - `send_order_notification`;
  - `send_staff_new_order_notification`;
  - `auto_cancel_expired_pickup_orders`.
- `users.tasks`:
  - `send_confirmation_email`;
  - `send_welcome_email`.
- `support.tasks`:
  - `send_support_request_notification`.

### Когда вызываются
- Checkout created/cancelled/ready/paid события.
- Registration/resend/confirm email flows.
- Support form submit.
- Periodic beat schedule: auto-cancel expired pickup orders.

### Обработка ошибок/retry
- Общая конфигурация `EMAIL_TASK_AUTORETRY_KWARGS`:
  - autoretry for `NotificationDeliveryError`;
  - backoff + jitter; `max_retries=5`.
- Permanent SMTP ошибки: распознаются и не ретраятся.

### Риски при сбоях SMTP/Redis/worker
- SMTP fail:
  - transient: retries;
  - permanent: запись ошибки + `False`.
- Redis/Celery dispatch fail:
  - order/user: логируется; пользовательский flow не всегда ломается;
  - support: дополнительно пишется `email_error` в `SupportRequest`.
- Beat/worker down: авто-отмена и email уведомления не будут исполняться.

---

## 11. Email-логика

### Какие письма отправляются
- Пользователь:
  - email confirmation;
  - welcome.
- Заказы:
  - created/cancelled/ready/paid;
  - staff notification on new order.
- Поддержка:
  - staff notification on new support request.

### Через какие функции/задачи
- Users: `users/tasks.py`, enqueue via `EmailConfirmationService`.
- Orders: `orders/tasks.py`, enqueue via `OrderNotificationService`.
- Support: `support/tasks.py`, enqueue via `SupportNotificationService`.

### Шаблоны писем
- В коде не найдено template-based render для email body; тексты формируются строками в task functions.

### Ошибки доставки
- `config/email_delivery.py`:
  - классификация permanent/transient SMTP.
- Подробный log extra payload (queue/smtp/retries/task_id/...).
- `support` дополнительно сохраняет error text в БД.

---

## 12. Безопасность

### CSRF
- `CsrfViewMiddleware` включен.
- Во всех POST-формах присутствует `{% csrf_token %}`.
- `csrf_exempt` в проекте не найдено.
- Кастомный handler `users.views.csrf_failure` даёт UX-friendly redirect.

### Permissions/авторизация/staff-доступ
- Dashboard: `ModeratorRequiredMixin`:
  - authenticated;
  - superuser OR (is_staff + группа `Модераторы`/`moderators`).
- Профиль:
  - просмотр чужого профиля запрещен, кроме superuser.
- Заказы пользователя:
  - queryset ограничен `build_user_order_visibility_q`.

### Rate limiting
- App-level: `django-ratelimit` для login/registration/resend/checkout/support.
- Proxy-level: nginx `limit_req` для `/checkout/`, `/users/login/`, `/users/registration/`.

### Security headers / CSP / cookie settings
- Security middleware + CSP middleware.
- CSP policy configurable (`CSP_ENFORCE`).
- Cookies: httpOnly + sameSite + secure flags env-driven.
- HSTS/SSL redirect configurable.

### DEBUG/ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS
- `SECRET_KEY` обязателен.
- `ALLOWED_HOSTS` fallback только в DEBUG.
- `CSRF_TRUSTED_ORIGINS` читается из env.

### Race/duplicate protection
- checkout/cart/cancel/issue/merge/payment-update защищены atomic+locks.
- checkout idempotency через payment unique key + session token replay protection.

### Stock depletion protection
- DB check constraint `reserved <= quantity`.
- reserve/update filters предотвращают выход за доступный остаток.

### Персональные данные
- Есть PII в `User`, `Order`, `SupportRequest`.
- Логи санитизируются (`SensitiveDataFilter`) для email/phone/token/secret.

### Потенциальные уязвимости/риски
- В `docker/nginx/default.conf` включен `auth_basic`, но файл `docker/nginx/auth/.htpasswd` в репозитории не найден.
- TLS termination в текущем nginx config не настроен (HTTP-only).
- При активной Метрике `X-Frame-Options` middleware отключается (используется CSP route).

---

## 13. Складская логика и конкурентность

### Базовые величины
- `quantity`: физический остаток.
- `reserved_quantity`: резерв под активные заказы.
- `available_quantity`: `max(quantity - reserved_quantity, 0)`.

### Инварианты
- Всегда `0 <= reserved_quantity <= quantity`.
- Доступный остаток не должен уходить в минус.

### Точки модификации
- Checkout reserve: `reserve_variant` увеличивает `reserved_quantity`.
- Cancel release: `release_variant_reservation` уменьшает `reserved_quantity`.
- Issue consume: `issue_variant` уменьшает и `quantity`, и `reserved_quantity`.

### Транзакционность/locks
- Checkout:
  - lock user (опц.), cart items, variants.
- Cancel/Issue:
  - lock order + variants.
- Cart ops:
  - lock variant при add/update.
- Cart merge:
  - lock carts and session cart items.

### Одновременные заказы
- Критические проверки в SQL update condition + select_for_update минимизируют oversell.
- Повторные checkout submit защищены idempotency.

### Отмена
- Возвращает резерв, переводит статусы, отменяет manual payments.
- Повторная отмена idempotent no-op по stock.

### Изменение статусов
- Staff policy не даёт нелегальных переходов.
- `issued` невозможен без оплаты и без успешного stock consume.

### Что должно сохраняться всегда
- Consistency между `Order` статусами и складом.
- Отмена не должна “двойно” возвращать резерв.
- Выдача не должна списывать больше физического/резерва.

---

## 14. Тесты

### Типы тестов
- Unit/Service tests (`SimpleTestCase`, `TestCase`).
- Transaction/concurrency tests (`TransactionTestCase`).
- Smoke E2E (`orders/test_smoke_e2e.py`, теги `smoke`, `e2e`).

### Что покрыто хорошо
- Checkout flow, idempotency, race scenarios (`orders/tests.py`).
- Cancellation/Issue/Auto-cancel.
- Dashboard status/payment workflows.
- Payment workflow + signal fallback (`payments/tests.py`).
- User auth/email confirmation/ratelimits/profile/order visibility (`users/tests.py`).
- Support form + retry/failure persistence (`support/tests.py`).
- Metrika payload и no-PII assertions (`analytics/tests.py`).
- SMTP error classification (`config/tests.py`).

### Критичные сценарии
- Parallel checkout/cancel invariants (`orders/tests.py:OrderConcurrencyTest`).
- Cart merge concurrency (`store/tests/tests.py:CartMergeConcurrencyTest`).
- End-to-end sales flow smoke (`orders/test_smoke_e2e.py:SalesFlowSmokeE2ETest`).

### Пробелы/что добавить
- Отдельные интеграционные тесты nginx rate-limits (сейчас в app-level тестируются ratelimit реакции).
- Тесты backup/restore scripts (пока shell-level, без CI execution).
- Тесты на upgrade/migration rollback strategy (в коде не найдено).

### Фактический запуск в этом анализе
- Команда: `.venv/bin/python manage.py test --verbosity 1`.
- Результат: найдено 288 тестов, запуск прерван из-за `OperationalError` (`DB_HOST=db` недоступен вне docker-сети).

---

## 15. Docker / deployment / инфраструктура

### Dockerfile
- База `python:3.12-slim`.
- Установка build deps + poetry.
- `poetry install --only main --no-root`.
- Non-root user `app` (uid/gid 10001).
- Entrypoint: `docker/web-entrypoint.sh`.

### web entrypoint
- На старте: `migrate` + `collectstatic`.
- Далее gunicorn bind `0.0.0.0:8000`.
- Access logs include `X-Request-ID`.

### docker-compose (dev)
- Сервисы: `nginx`, `web`, `db`, `redis`, `worker`, `email-worker`, `beat`.
- Healthchecks на nginx/web/db/redis.
- Volumes: postgres/static/media.

### docker-compose.prod
- `web/worker/email-worker/beat` из GHCR image.
- Тот же composition, но без локального build.

### Nginx
- Reverse proxy + static/media serving.
- Basic auth (`auth_basic`).
- `limit_req_zone` для checkout и auth POST.
- `/healthz/` доступен без basic auth.

### PostgreSQL/Redis/Celery
- PostgreSQL 16.x.
- Redis 7.x как broker/backend/cache.
- Отдельный email queue worker (`-Q email`).
- `beat` для periodic auto-cancel.

### Healthchecks
- DB: `pg_isready`.
- Redis: `redis-cli ping`.
- Web: HTTP request to `/healthz/`.
- Nginx: local wget `/healthz/`.

### Env-переменные
- Подробно заданы в `.env.example` и `.env.prod.example`.
- Есть production/security/tuning переменные (CSP, HSTS, cookies, ratelimits, Sentry, Metrika).

### Static/media
- `collectstatic` в `staticfiles`.
- nginx aliases `/static/` и `/media/`.

---

## 16. CI/CD

### Workflow
- Файл: `.github/workflows/ci-cd.yml`.
- Триггеры: PR, push `develop`/`main`.

### Джобы
- `ci`:
  - Poetry check/lock;
  - black/isort/flake8;
  - migrations check;
  - `manage.py check`;
  - `manage.py test` на postgres+redis services.
- `docker`:
  - build image;
  - push в GHCR **только на `main`**.
- `deploy`:
  - SSH to server;
  - `docker login ghcr`;
  - `docker compose -f docker-compose.prod.yml pull && up -d`.

### Secrets
- `SERVER_HOST`, `SERVER_USER`, `SERVER_PORT`, `SERVER_SSH_KEY`.
- `GHCR_USERNAME`, `GHCR_TOKEN`.
- `GITHUB_TOKEN` builtin action token.

### Риски/улучшения
- Нет этапа smoke после deploy (health + business probe).
- Нет rollback automation (manual only).
- Один `latest` tag: полезно добавить immutable tags по commit SHA.

---

## 17. Админка и staff-интерфейс

### Django admin
- Зарегистрированы все ключевые модели (`store/orders/payments/users/support`).
- `OrderAdmin` имеет inline order items + status transitions.
- `ProductVariantAdmin` показывает `available_quantity`.
- `SupportRequestAdmin` позволяет менять status и вести `staff_notes`.

### Staff dashboard (кастомный)
- В `store/templates/dashboard/*` + `store/views/views_dashboard.py`.
- Возможности:
  - warehouse inventory и product management;
  - order list/detail, status/payment updates, internal notes;
  - история переходов статусов.
- Доступ ограничен `ModeratorRequiredMixin`.

### Разграничение прав
- Модераторы: через группу `Модераторы` + `is_staff`.
- Команда `create_moderator_group` выдает нужные permissions.

### Улучшения
- Согласовать/упростить UX управления модераторами в `users/admin.py` и шаблоне `templates_moderator/moderator_group_management.html` (контекст шаблона и ожидаемые поля выглядят несинхронно).

---

## 18. Сильные стороны проекта

- Production-like транзакционный checkout с idempotency и lock strategy.
- Явный service/application слой (не “всё во view”).
- Разделение email queue (`email-worker`) от default queue.
- Согласованная складская модель `physical/reserved/available`.
- Политика переходов статусов (`OrderStatusPolicy`) + audit trail (`OrderStatusTransition`).
- Поддержка guest-to-user continuity заказов через email confirmation rule.
- Ретраи email с классификацией permanent/transient SMTP ошибок.
- Инфраструктурные практики: healthchecks, request-id propagation, PII log masking, backup/restore scripts.
- Широкое покрытие тестами, включая concurrency.

---

## 19. Слабые места и технический долг

- `orders/services.py` перегружен (много ответственности в одном файле).
- Документация частично устарела:
  - `README` ссылается на `ci.yml/cd.yml`, а фактически `ci-cd.yml`;
  - ссылка на `RUNBOOK.md` в README, файл в коде не найден;
  - в README есть команды с несуществующим `delivery` каталогом.
- В `docker-compose.yaml` указан mount `docker/nginx/auth/.htpasswd`, но файл/директория в репозитории не найдены.
- Текущий nginx config без TLS (HTTP-only).
- `users/admin.py` кастомный group management UX выглядит не полностью согласованным с шаблоном.
- `store/services/template_filters.py` содержит thin wrappers, которые можно упростить.
- `Address` модель есть, но в MVP checkout (pickup-only) практически не используется.

---

## 20. Вопросы, которые может задать техлид (и краткие ответы)

1. **Почему Django?**  
   Быстрый монолитный старт: ORM, auth, admin, forms, middleware, template stack, mature ecosystem.

2. **Почему сервисный слой?**  
   Чтобы вынести сложную бизнес-логику checkout/order/payment из views и сделать её тестируемой.

3. **Почему Celery?**  
   Для асинхронных email уведомлений и периодических задач (auto-cancel), чтобы не блокировать HTTP.

4. **Как защищены остатки от гонок?**  
   `transaction.atomic` + `select_for_update` + SQL conditional updates + DB constraints.

5. **Что будет при падении Redis?**  
   Не будут ставиться/выполняться Celery задачи; часть user flows продолжит работать, но без async email и auto-cancel.

6. **Что будет при сбое SMTP?**  
   Transient ошибки ретраятся; permanent ошибки фиксируются как failure без бесконечных retry.

7. **Как устроена отмена заказа?**  
   Lock order/variants → release reserve → cancel manual payment → update statuses → transitions + notification.

8. **Как работает резерв?**  
   При checkout резерв увеличивается, при выдаче списывается физический stock и резерв, при отмене резерв снимается.

9. **Как деплоится проект?**  
   GH Actions: CI → build/push GHCR → SSH deploy (`docker compose pull/up -d`).

10. **Какие настройки критичны в prod?**  
    `SECRET_KEY`, hosts/csrf origins, cookie secure flags, SSL/HSTS, DB/Redis, email creds, ratelimits, CSP.

11. **Что улучшил бы дальше?**  
    Разбил бы `orders/services.py`, добавил post-deploy smoke, immutable image tags и rollback workflow, довел docs до консистентного состояния.

---

## 21. Краткая версия защиты на 3–5 минут

Проект — это Django MVP интернет-магазина клубной атрибутики с упором на корректную операционную логику, а не только витрину. Бизнес-сценарий — самовывоз: пользователь выбирает товар, оформляет заказ, а сотрудники обрабатывают его в dashboard.  

Архитектурно это монолит из приложений `store`, `orders`, `payments`, `users`, `support`, `analytics`. Ключевая инженерная часть — checkout: он реализован через сервисный слой с `transaction.atomic`, `select_for_update`, idempotency key и контролем остатков. Это защищает от гонок при параллельных запросах и от повторного оформления одного заказа.  

Складская модель разделяет физический остаток и резерв. При checkout резервируется товар, при отмене резерв возвращается, при выдаче физический остаток списывается. Для статусов заказа есть формализованная policy переходов и журнал `OrderStatusTransition`, поэтому staff-flow прозрачен и аудитируем.  

Фоновые задачи вынесены в Celery: email пользователю, staff-уведомления и периодическая авто-отмена просроченных заказов самовывоза. Для SMTP ошибок реализована классификация permanent/transient и корректный retry policy.  

По инфраструктуре: Docker Compose, Nginx+Gunicorn, Postgres, Redis, healthchecks, CI/CD в GitHub Actions, деплой по SSH с pull/up образа из GHCR. По качеству: в проекте широкое тестовое покрытие, включая concurrency и smoke E2E.  

Если кратко, это не “просто CRUD-магазин”, а MVP с production-like контролем конкурентности, статусных переходов и операционной устойчивости.

---

## 22. Подробная версия защиты на 15–20 минут

### Вступление
Я делал проект как MVP магазина атрибутики, но с приоритетом на корректную backend-логику: статусные процессы, остатки и операционные сценарии сотрудников.

### Бизнес-задача
Сервис закрывает полный цикл: пользовательский каталог и checkout, плюс staff обработка заказов в формате самовывоза.  
В MVP нет онлайн-эквайринга и курьерской логистики, но есть ручная оплата и складские резервы.

### Архитектура
Монолит Django, разбитый по доменам:
- `store` — каталог, корзина, warehouse dashboard;
- `orders` — checkout, статусы, отмена/выдача/авто-отмена;
- `payments` — платежные сущности и sync статусов;
- `users` — auth и email confirmation;
- `support` — обращения;
- `analytics` — metrika ecommerce.

Infra: Postgres, Redis, Celery worker/email-worker/beat, Nginx, Gunicorn, Docker Compose.

### Ключевая бизнес-логика
Главный сценарий — checkout:
1. Получение idempotency key из checkout token.
2. Проверка лимитов и режимов.
3. Транзакция с блокировкой user/cart/variants.
4. Очистка недоступных позиций.
5. Создание order + order items snapshots + manual payment.
6. Резерв остатков.
7. Очистка корзины и постановка уведомлений через on_commit.

Отмена заказа:
- доменные guards по статусам,
- release reserve,
- отмена manual payment,
- фиксация transitions и уведомление.

Выдача:
- только при подтвержденной оплате,
- consume reserve → уменьшение физического stock.

Staff-flow:
- policy переходов не даёт нелегальных шагов,
- финальные статусы immutable,
- есть журнал всех переходов.

### Безопасность
CSRF включен везде, есть кастомный UX для CSRF-failure.  
Rate limiting реализован на уровне приложения и nginx.  
Есть role-based доступ к staff dashboard через group + `is_staff`.  
Request-id прокидывается в HTTP/Celery и логи.  
Логи санитизируют email/phone/secrets/tokens.

### Инфраструктура
Dockerfile на Python 3.12, non-root user, web-entrypoint с миграциями и collectstatic.  
Nginx отдаёт static/media и проксирует в gunicorn.  
CI/CD: lint + check + tests + build + push + deploy по SSH.  
Есть backup/restore verification scripts.

### Тесты
Сильное покрытие:
- checkout/idempotency/race,
- cancel/issue/auto-cancel,
- payment workflow and signal fallback,
- user auth/confirmation/visibility,
- support retries and failure persistence,
- metrika no-PII payload checks.

### Вывод
Проект уровня уверенного backend MVP: важные production-паттерны реализованы (transactions, locks, idempotency, audit, async jobs).  
Следующий шаг — доработка документации/операционного контура и декомпозиция крупных сервисов.

---

## 23. Таблица “компонент → назначение”

| Компонент | Файл/директория | Назначение | Важность | Что сказать на защите |
|---|---|---|---|---|
| Root settings | `config/settings.py` | Центральная конфигурация runtime/security/celery/cache | Критично | Показать env-driven подход и security defaults |
| Request ID middleware | `config/middleware.py` | Correlation ID для HTTP/логов | Высокая | Сквозная трассировка инцидентов |
| Logging sanitize | `config/logging_utils.py` | JSON logging + masking PII/secrets | Высокая | Production-like observability |
| Email retry policy | `config/email_delivery.py` | Retry/backoff и SMTP error classification | Высокая | Не ретраим permanent ошибки |
| Store models | `store/models.py` | Каталог, корзина, CMS страницы | Критично | Основа товарного домена |
| Order models | `orders/models.py` | Заказы, позиции, transitions | Критично | Аудит и статусный lifecycle |
| Payment model | `payments/models.py` | Платежи и idempotency key | Критично | Защита от дублей |
| User model | `users/models.py` | Custom auth по email + token fields | Критично | Email confirmation flow |
| Support model | `support/models.py` | Обращения и delivery статус | Средняя | Контроль обработки support |
| Checkout service | `orders/services.py` | Orchestration checkout и резервов | Критично | Главная инженерная часть |
| Cancellation service | `orders/services.py` | Безопасная отмена и release reserve | Критично | Идемпотентная отмена |
| Issue service | `orders/services.py` | Списание физического stock при выдаче | Критично | Инварианты склада |
| Dashboard flow service | `orders/application/dashboard_order_flow.py` | Staff сценарии изменения статусов/оплаты | Высокая | Policy-driven transitions |
| Order status policy | `orders/application/order_status_policy.py` | Разрешенные переходы статусов | Высокая | Формализация процесса |
| Cart service | `store/services/cart_service.py` | Add/update/remove cart items с lock | Высокая | Race-safe корзина |
| Cart context resolver | `store/application/cart_context.py` | User/session cart resolution + merge | Высокая | Continuity guest→user |
| Cart merge signal | `store/signals.py` | Trigger merge on login | Средняя | Автоматизация UX |
| Catalog query service | `store/queries/catalog_queries.py` | Фильтры/сортировки каталога | Средняя | Чистые query-слои |
| Warehouse query service | `store/queries/dashboard_queries.py` | Dashboard aggregates по stock/orders | Высокая | Прозрачный stock summary |
| Checkout view | `orders/views.py` | Entry point оформления заказа | Критично | Token + ratelimit + idempotency |
| User views | `users/views.py` | Auth/profile/orders/confirm | Высокая | Полный user lifecycle |
| Dashboard views | `store/views/views_dashboard.py` | Staff интерфейс операций | Высокая | Операционка магазина |
| Support views/forms | `support/views.py`, `support/forms.py` | Канал обращений + антиспам | Средняя | Honeypot + consent |
| Order tasks | `orders/tasks.py` | Order email notifications + auto-cancel task | Высокая | Async processing |
| User tasks | `users/tasks.py` | Confirmation/welcome emails | Средняя | Resilient отправка писем |
| Support tasks | `support/tasks.py` | Support email + failure persistence | Высокая | Отказоустойчивость support |
| Payment workflow | `payments/application/payment_workflow.py` | Controlled payment updates + sync | Высокая | Избежание двойной sync |
| Payment signals | `payments/signals.py` | Fallback sync для direct ORM/admin edits | Средняя | Safety net |
| Analytics metrika | `analytics/metrika.py` | Ecommerce events pipeline | Средняя | No-PII ecommerce payload |
| Dockerfile | `Dockerfile` | Build runtime image | Высокая | Reproducible deploy |
| Compose dev/prod | `docker-compose.yaml`, `docker-compose.prod.yml` | Service topology | Высокая | web/db/redis/workers/beat |
| Nginx config | `docker/nginx/default.conf` | Reverse proxy + limits + static | Высокая | Infra hardening |
| CI/CD workflow | `.github/workflows/ci-cd.yml` | lint/test/build/deploy pipeline | Высокая | Автоматизация поставки |
| Backup scripts | `ops/db/*.sh` | Backup + restore verification | Средняя | Operational readiness |

---

## 24. Таблица “класс/функция → что делает”

> Ниже “важные” классы/функции по core бизнес-логике и инфраструктуре.

| Приложение | Файл | Класс/функция | Назначение | Вход | Результат | Где используется | Комментарий для защиты |
|---|---|---|---|---|---|---|---|
| orders | `orders/services.py` | `CheckoutService.create_order_from_cart` | Оформляет заказ из корзины | `CheckoutContext`, `cleaned_data`, token | `Order` | `CheckoutView` | Ключевой use case с locks/idempotency |
| orders | `orders/services.py` | `CheckoutService.build_checkout_idempotency_key` | Формирует idempotency key | token, user_id/session_key | `str` | checkout flow | user/session scoped dedup |
| orders | `orders/services.py` | `OrderStockReservationService.reserve_variant` | Резервирует stock | variant, qty | None / error | checkout | SQL guard against oversell |
| orders | `orders/services.py` | `OrderStockReservationService.release_variant_reservation` | Снимает резерв | variant, qty | None / error | cancellation | prevent negative reserve |
| orders | `orders/services.py` | `OrderStockReservationService.issue_variant` | Списывает физ. stock из резерва | variant, qty | None / error | issue flow | physical+reserved sync |
| orders | `orders/services.py` | `OrderCancellationService.cancel_order` | Доменная отмена заказа | order_id, user_id?, actor? | `Order` | user/dashboard cancel | idempotent cancellation |
| orders | `orders/services.py` | `OrderIssueService.consume_reserved_stock` | Проверяет условия и списывает stock | order_id | `Order` | dashboard issued | paid+status guarded |
| orders | `orders/services.py` | `OrderAutoCancellationService.cancel_expired_pickup_orders` | Batch auto-cancel просроченных | optional now/batch | summary dict | Celery beat task | business-day deadlines |
| orders | `orders/services.py` | `ManualPaymentUpdateService.update_order_payment_status` | Staff update payment status | order_id, next status | `Order` | dashboard payment update | creates/updates manual payment |
| orders | `orders/application/order_status_policy.py` | `OrderStatusPolicy.get_status_key` | Маппинг order→dashboard status key | `Order` | key | dashboard presenter/flow | централизует бизнес-статус |
| orders | `orders/application/order_status_policy.py` | `OrderStatusPolicy.can_transition` | Проверка допустимого перехода | current, next | bool | dashboard flow | policy-based transitions |
| orders | `orders/application/dashboard_order_flow.py` | `DashboardOrderFlowService.update_order_status` | Применяет staff статусный переход | order, next, actor | result dataclass | dashboard status endpoint | orchestration слоя application |
| orders | `orders/application/dashboard_order_flow.py` | `DashboardOrderFlowService.update_payment_status` | Обновляет payment status | order, next, actor | result dataclass | dashboard payment endpoint | uses ManualPaymentUpdateService |
| orders | `orders/application/order_notification_service.py` | `OrderNotificationService.schedule_*` | on_commit enqueue order emails | order_id | None | services | decoupled async notifications |
| orders | `orders/application/checkout_session_service.py` | `get_or_create_checkout_token` | anti-double-submit token | request | token | checkout page | session-based protection |
| orders | `orders/application/checkout_session_service.py` | `get_processed_order_for_token` | replay detection | request, token | order/None | checkout POST | UX idempotency layer |
| orders | `orders/views.py` | `CheckoutView.form_valid` | HTTP entry checkout | validated form | redirect | route `/checkout/` | integrates metrika purchase queue |
| orders | `orders/views.py` | `CheckoutSuccessView.get_context_data` | success page with access control | request+order pk | context | `/checkout/success/<pk>/` | guest session bound access |
| orders | `orders/tasks.py` | `send_order_notification_sync` | Синхронная отправка order email | order_id, event_key | bool | Celery task + tests | permanent/transient aware |
| orders | `orders/tasks.py` | `send_staff_new_order_notification_sync` | Письмо сотрудникам о новом заказе | order_id | bool | Celery task | staff recipients parsing |
| orders | `orders/tasks.py` | `auto_cancel_expired_pickup_orders` | wrapper periodic task | - | summary dict | beat | delegates to service |
| store | `store/services/cart_service.py` | `CartService.add_item` | Добавление в корзину | cart_context, variant_id, qty | cart item | AddToCartView | atomic + select_for_update |
| store | `store/services/cart_service.py` | `CartService.update_item_quantity` | Изменение количества | cart_context, variant_id, qty | cart item | UpdateCartView | sale/stock guards |
| store | `store/services/cart_service.py` | `CartService.remove_item` | Удаление из корзины | cart_context, variant_id | bool | RemoveFromCartView | explicit error mapping |
| store | `store/application/cart_context.py` | `CartContextResolver.resolve_request` | resolve user/session cart | request | `CartContext` | mixins/views | request-level caching |
| store | `store/application/cart_context.py` | `merge_session_cart_into_user_cart` | merge guest cart into user | user_cart, session_key | None | signal/login flow | concurrency-aware merge |
| store | `store/signals.py` | `merge_carts_on_login` | trigger merge after auth | sender/request/user | None | auth signal | continuity guest→user |
| store | `store/queries/catalog_queries.py` | `build_product_list_queryset` | catalog filters/sort | filter params | queryset | product list view | stock-aware sorting/filtering |
| store | `store/queries/dashboard_queries.py` | `WarehouseQueryService.build_products_queryset` | stock dashboard aggregates | filters | queryset | warehouse view | physical/reserved/available sums |
| store | `store/queries/dashboard_queries.py` | `DashboardOrderQueryService.build_orders_queryset` | orders dashboard filtering | filters | queryset | orders dashboard | status/payment/date/amount filters |
| store | `store/queries/dashboard_queries.py` | `WarehouseReservationQueryService.get_active_reservation_items_by_variant` | активные резервы по variant | variants | dict | product manage page | explain why stock reserved |
| store | `store/application/warehouse_crud.py` | `WarehouseCrudService.*` | CRUD/application methods | forms/data | model/form | dashboard CRUD views | keeps views thinner |
| store | `store/views/views_cart.py` | `AddToCartView.post` | cart add endpoint | POST form data | JSON/redirect | `/cart/add/` | Accept-aware response style |
| store | `store/views/views_cart.py` | `get_safe_redirect_url` | open redirect protection | request | safe url | cart POST flows | host/scheme validation |
| store | `store/views/views_dashboard.py` | `DashboardOrderStatusUpdateView.post` | staff status endpoint | POST status | redirect+message | dashboard | calls DashboardOrderFlowService |
| store | `store/views/views_dashboard.py` | `WarehouseVariantStockUpdateView.post` | stock update endpoint | POST quantity | redirect | dashboard | validation via form |
| store | `store/forms.py` | `ProductVariantForm.clean_quantity` | guard quantity>=reserve | quantity | quantity/error | variant CRUD | protects stock invariant |
| store | `store/forms.py` | `ProductImageForm.clean_image` | secure image validation | file | file/error | image upload | type/size/content checks |
| store | `store/context_processors.py` | `navigation_permissions` | global template context | request | dict | all templates | legal links + contacts |
| store | `store/site_contacts.py` | `build_pickup_location` | pickup meta from settings | - | dict | checkout/order templates | central source of pickup data |
| payments | `payments/application/payment_workflow.py` | `PaymentWorkflowService.create/save/delete_payment` | controlled payment mutations + sync | payment data | payment/None | checkout/manual updates/tests | avoids signal double-sync |
| payments | `payments/services/payment_status_service.py` | `sync_order_payment_status` | order payment status reconciliation | order | status | workflow/signals | cancelled order protection |
| payments | `payments/signals.py` | `sync_order_payment_status_on_save/delete` | fallback sync on direct ORM/admin changes | Payment signal | None | global signal handlers | safety net for non-workflow edits |
| users | `users/application/email_confirmation_service.py` | `schedule_confirmation_for_new_user` | token + on_commit queueing | user, mutable result dict | token | registration | no email dispatch before commit |
| users | `users/application/email_confirmation_service.py` | `can_resend` | resend cooldown check | user | bool + seconds | resend view | anti-spam/anti-flood |
| users | `users/views.py` | `csrf_failure` | custom CSRF UX handler | request | redirect | CSRF failure view | safe referer redirect |
| users | `users/views.py` | `build_user_order_visibility_q` | order visibility logic | user | `Q` | order list/detail | includes guest orders after email confirm |
| users | `users/views.py` | `UserOrderCancelView.post` | user cancel endpoint | request, order pk | redirect | `/users/orders/<pk>/cancel/` | ownership enforced in service |
| users | `users/views.py` | `EmailConfirmationView.get` | token confirmation + autologin | token | redirect | confirm-email route | welcome email enqueue |
| users | `users/forms.py` | `AvatarImageField.to_python` | avatar security validation | file | image/error | profile form | protects against invalid archive uploads |
| users | `users/tasks.py` | `send_confirmation_email_sync` | sync confirmation email | email, token | bool | celery task | raises domain error for retries |
| users | `users/tasks.py` | `send_welcome_email_sync` | sync welcome email | email | bool | celery task | same retry policy |
| support | `support/forms.py` | `clean_website` | honeypot anti-bot | hidden field | value/error | support form | blocks bot-like submissions |
| support | `support/views.py` | `SupportRequestView.form_valid` | create support request | validated form | redirect | `/support/` | schedule notification on commit |
| support | `support/application/support_notification_service.py` | `enqueue` | queue support email task | support_request_id | bool | support flow | persists dispatch failure in DB |
| support | `support/tasks.py` | `send_support_request_notification_sync` | send support email with retry/failure persistence | support_request_id | bool | celery task | final failure stored in model |
| analytics | `analytics/metrika.py` | `build_purchase_event` | purchase ecommerce payload | order, order_items | dict/None | checkout success | excludes customer PII |
| analytics | `analytics/metrika.py` | `queue_ecommerce_event` | queue events in session | request, event | None | cart/checkout flows | one-time event delivery |
| analytics | `analytics/templatetags/metrika_tags.py` | `yandex_metrika` | render config/events once | template context | dict | base template | prevents duplicated loader |
| config | `config/middleware.py` | `RequestIdMiddleware` | request correlation id | request | response | middleware chain | adds header + context |
| config | `config/celery.py` | `inject_request_id_before_publish` | propagate request-id to Celery headers | headers | mutated headers | celery signal | cross-service traceability |
| config | `config/email_delivery.py` | `is_permanent_email_delivery_error` | classify SMTP errors | exception | bool | all email tasks | retry only transient |
| config | `config/health.py` | `healthz_view` | readiness check (DB) | request | JSON 200/503 | `/healthz/` | infra health probing |

---

## 25. Финальный вывод

### Уровень проекта
По backend-части это **сильный middle-level MVP**: есть не только CRUD/шаблоны, но и корректные транзакционные сценарии, доменные сервисы, конкурентная защита, асинхронные задачи и аудит.

### Насколько production-like
Высокий уровень для MVP:
- явные инварианты склада;
- idempotency checkout;
- статусные policy и transition logging;
- CI/CD + dockerized runtime + healthchecks + backup scripts.

Ограничения production-ready статуса:
- документация частично расходится с кодом;
- нет полноценного TLS/ingress story внутри текущего nginx конфига;
- нет автоматизированного rollback/post-deploy smoke pipeline.

### Что ценно для портфолио
- Показывать именно checkout/cancellation/issue workflow.
- Показать как решены race conditions и duplicate submits.
- Показать раздельный email queue worker и SMTP retry semantics.
- Показать coverage concurrency tests и smoke E2E.

### Что доделать перед показом работодателю
1. Привести README/ops docs к актуальному состоянию (workflow names, runbook, команды).
2. Закрыть infra gaps (`.htpasswd` provisioning, TLS deployment инструкция).
3. Разбить `orders/services.py` на более мелкие модули.
4. Добавить post-deploy smoke checks и версионирование образов по SHA.

