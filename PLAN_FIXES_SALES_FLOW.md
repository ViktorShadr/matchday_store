# План исправлений полного цикла продажи

Документ фиксирует порядок исправлений по итогам аудита e-commerce флоу:
регистрация -> корзина -> checkout -> создание заказа -> обработка staff -> выдача.

## 1) Критичный блок (сделать первым, 1-2 дня)

1. [x] Исправить Celery-регистрацию задач заказов.
   - `config/celery.py`: включить autodiscover для `orders` (предпочтительно по `INSTALLED_APPS`).
   - Критерий: worker видит `orders.tasks.send_order_notification`.

2. [x] Добавить уведомление сотруднику о новом заказе.
   - `orders/tasks.py`, `orders/application/order_notification_service.py`.
   - Добавить `STAFF_ORDER_NOTIFICATION_EMAILS` в settings.
   - В уведомлении: номер заказа, сумма, контакты клиента, ссылка на dashboard.
   - Критерий: при создании заказа сотрудник получает уведомление.

3. [ ] Привести `docker-compose` к рабочему состоянию.
   - Развести env для docker и локального запуска.
   - В docker-режиме использовать `DB_HOST=db`.
   - Актуализировать README по запуску.
   - Критерий: `db`, `web`, `worker` стартуют без restart-loop.

## 2) Высокий приоритет (2-4 дня)

4. [x] Закрыть race condition на смене статусов заказа в dashboard.
   - `orders/application/dashboard_order_flow.py`: `transaction.atomic` + `select_for_update` по `Order`.
   - Добавить тест на параллельные изменения статуса.

5. [x] Подключить сигналы payments.
   - `payments/apps.py`: импорт `payments.signals` в `ready()`.
   - Критерий: любые изменения `Payment` корректно синхронизируют `Order.payment_status`.

6. [x] Повысить надежность уведомлений.
   - Добавить retries/backoff для celery task уведомлений.
   - Расширить логирование ошибок отправки (`order_id`, `event_key`, причина).

## 3) До production-ready (4-7 дней)

7. [x] Ввести аудит жизненного цикла заказа.
   - Добавить `issued_at` в `Order`.
   - Ввести журнал переходов статусов (кто/когда/из какого в какой).

8. Доработать production-настройки безопасности.
   - `DEBUG=False`, secure cookies, HTTPS/HSTS.
   - Ротация секретов и проверка утечек.

9. [x] Добавить интеграционные smoke-проверки.
   - E2E: регистрация -> checkout -> уведомления -> dashboard обработка -> выдача.
   - Проверка, что worker реально исполняет задачи.

## 4) Критерий "готово"

- Заказ создается только из валидной корзины, без дублей и oversell.
- Клиент и staff получают нужные уведомления.
- Статусы заказа меняются только по допустимому flow, без гонок.
- `docker compose up --build` поднимает рабочий сервис с БД и worker.
- `python manage.py test` + интеграционные тесты проходят.
