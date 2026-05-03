# План устранения рисков искусственного опустошения склада

Контекст: checkout в режиме `pickup + pay_on_receipt`.

## 1) Что нужно исправить

1. Списание склада идет в момент checkout, а не в момент выдачи.
2. Нет отдельного резерва по SKU для активных заказов.
3. Нет модели `available = stock - reserved`.
4. Можно создать много неоплаченных заказов и заблокировать остатки.
5. Нет лимита активных заказов на пользователя.
6. Нет жесткого доменного лимита количества одинакового SKU в заказе.
7. Нет TTL-автоотмены старых неоплаченных заказов.

## 2) Целевое поведение

1. `quantity` в `ProductVariant` = физический склад.
2. `reserved_quantity` = резерв под активные заказы.
3. Доступный остаток: `available_quantity = quantity - reserved_quantity`.
4. На checkout происходит резерв, а не списание физического склада.
5. Физическое списание происходит только при статусе `issued`.
6. При отмене/TTL резерв корректно снимается.
7. Массовый абуз режется лимитами до входа в критичные транзакции.

## 3) План работ (минимальные безопасные изменения)

## Этап A. Быстрые антиабуз-ограничения (без смены модели склада) - 1 день

- [x] Добавить лимит активных заказов пользователя перед созданием заказа.
  - Где: `orders/services.py` (`CheckoutService.create_order_from_cart`).
  - Настройки: `CHECKOUT_MAX_ACTIVE_ORDERS` (например, 3-5).
  - Активными считать заказы со статусами не `issued/cancelled` и `payment_status != succeeded`.

- [x] Добавить доменный лимит количества одного SKU в заказе.
  - Где: `orders/services.py` (проверка `cart_item.quantity` перед резервом/созданием позиции).
  - Настройки: `CHECKOUT_MAX_QTY_PER_SKU` (например, 5-10).
  - Важно: это лимит в сервисе, а не только UI/форма.

- [x] Ужесточить текущие rate limits checkout.
  - Где: `config/settings.py`, `orders/views.py`.
  - Пример: снизить `RATELIMIT_CHECKOUT_USER_RATE`, `RATELIMIT_CHECKOUT_IP_RATE`.

## Этап B. TTL-автоотмена невыкупленных заказов самовывоза - 1 день

- [x] Добавить TTL-настройку в рабочих днях.
  - Где: `config/settings.py`.
  - Новая переменная: `ORDER_PICKUP_RETENTION_BUSINESS_DAYS=3`.
  - Считать только понедельник-пятницу; суббота и воскресенье срок хранения не уменьшают.

- [x] Реализовать задачу автоотмены.
  - Где: `orders/tasks.py` (новая Celery task), при необходимости `orders/services.py`.
  - Логика: найти просроченные заказы самовывоза, которые еще можно отменять, и отменять через `OrderCancellationService.cancel_order(...)`.
  - Не менять остатки напрямую в task, только через доменный сервис.

- [x] Запустить по расписанию (beat/cron).
  - Где: Celery beat config или management command + cron.
  - Период: каждые 10-15 минут.

## Этап C. Переход на резерв вместо раннего списания - 2-3 дня

- [ ] Добавить поле резерва в SKU.
  - Где: `store/models.py`, миграция.
  - Поле: `reserved_quantity = models.PositiveIntegerField(default=0)`.
  - Ограничение: `reserved_quantity <= quantity` (CheckConstraint).

- [ ] Изменить checkout-транзакцию: резервировать, не списывать.
  - Где: `orders/services.py`.
  - Вместо `variant.quantity -= cart_item.quantity` делать `variant.reserved_quantity += cart_item.quantity`.
  - Проверка доступности: `quantity - reserved_quantity >= requested`.
  - Сохранить `transaction.atomic()` + `select_for_update()`.

- [ ] Изменить отмену заказа: возвращать резерв.
  - Где: `orders/services.py` (`OrderCancellationService`).
  - Вместо `quantity += ...` делать `reserved_quantity -= ...` (с защитой от ухода в минус).

- [ ] Изменить выдачу заказа: списывать физический склад.
  - Где: `orders/application/dashboard_order_flow.py` (+ сервис в `orders/services.py`).
  - На переходе в `issued`:
    - lock `Order` и все `ProductVariant` через `select_for_update()`,
    - атомарно `quantity -= item.qty`, `reserved_quantity -= item.qty`.
  - Для обновлений использовать `F()`-выражения, чтобы убрать риск lost update.

- [ ] Учесть `available` в витрине/корзине/валидации.
  - Где: `store/services/cart_service.py`, `store/services/cart_validator.py`, при необходимости presenters/queries.
  - UI должен видеть доступность по `quantity - reserved_quantity`.

## Этап D. Безопасная миграция текущих данных - 1 день

- [ ] Добавить одноразовую backfill-команду для перехода со старой схемы.
  - Где: новая management command в `orders/management/commands/`.
  - Для активных невыданных заказов:
    - `quantity += order_item.qty` (откат раннего списания),
    - `reserved_quantity += order_item.qty` (создание резерва).
  - Для `issued/delivered` заказы не трогать.
  - Для `cancelled` заказы не трогать.

- [ ] На время backfill включить maintenance window checkout (короткий), либо feature-flag.
  - Настройка: `STOCK_RESERVE_MODE_ENABLED`.

## Этап E. Тесты и приемка - 1-2 дня

- [ ] Unit/integration тесты:
  - лимит активных заказов пользователя;
  - лимит количества SKU в заказе;
  - TTL-автоотмена и снятие резерва;
  - race на последней единице (два параллельных checkout);
  - корректное списание только при `issued`;
  - идемпотентная повторная отмена.

- [ ] Нагрузочный smoke:
  - N параллельных checkout на SKU с малым остатком;
  - verify: `quantity >= 0`, `reserved_quantity >= 0`, `reserved_quantity <= quantity`.

## 4) Порядок внедрения в прод

1. Этап A (лимиты) + Этап B (TTL).
2. Релиз с флагом `STOCK_RESERVE_MODE_ENABLED=False`, проверка логов.
3. Деплой схемы и кода Этапа C под флагом.
4. Maintenance + backfill (Этап D).
5. Включить `STOCK_RESERVE_MODE_ENABLED=True`.
6. Мониторинг 48 часов: ошибки checkout/cancel/issued, аномалии остатков.

## 5) Критерий готовности

1. Неоплаченные заказы не могут бесконечно блокировать склад.
2. Доступность SKU считается только через `available = stock - reserved`.
3. Резерв снимается при отмене (включая TTL).
4. Физический склад уменьшается только при фактической выдаче (`issued`).
5. Конкурентные заказы последней единицы не приводят к oversell/negative stock.
