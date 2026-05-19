# Что мне обязательно выучить перед защитой

Ниже 30 пунктов, которые нужно понимать без подсказок, с привязкой к коду проекта.

1. Как устроен checkout end-to-end в `orders/services.py:CheckoutService.create_order_from_cart`.
2. Зачем нужен `checkout_token` и как работает session replay защита (`CheckoutSessionService`).
3. Как формируется `Payment.idempotency_key` и почему это защищает от дублей.
4. Почему checkout работает в `transaction.atomic` и где используются `select_for_update`.
5. Что такое `quantity`, `reserved_quantity`, `available_quantity` и где они меняются.
6. Как `OrderStockReservationService.reserve_variant` предотвращает oversell SQL-условием.
7. Как работает отмена заказа в `OrderCancellationService.cancel_order`.
8. Почему повторная отмена идемпотентна и не возвращает резерв дважды.
9. Как работает выдача заказа (`OrderIssueService`) и почему без оплаты она запрещена.
10. Как `OrderStatusPolicy` ограничивает переходы статусов.
11. Что делает `DashboardOrderFlowService` и чем он отличается от “прямого save во view”.
12. Как `ManualPaymentUpdateService` создает/обновляет manual payment и синхронизирует `paid_at`.
13. Почему в `payments` есть и workflow, и signals, и как они не конфликтуют.
14. Как считается итоговый `Order.payment_status` в `PaymentStatusSyncService`.
15. Как происходит merge guest корзины в user корзину при логине (`store/signals.py`, `CartContextResolver`).
16. Как защищены cart-операции от гонок (`CartService` + lock variant).
17. Как устроен доступ к staff dashboard (`ModeratorRequiredMixin`, группа `Модераторы` + `is_staff`).
18. Какие статусы/правила разрешают отмену заказа (`OrderCancellationService` guards).
19. Как работают ratelimits: app-level (`django-ratelimit`) и nginx-level (`limit_req`).
20. Как обрабатываются CSRF ошибки (`users.views.csrf_failure`) и зачем это сделано.
21. Какие security-настройки критичны в `config/settings.py` для production.
22. Как работает `RequestIdMiddleware` и propagation request-id в Celery (`config/celery.py`).
23. Как санитизируются логи и какие данные маскируются (`config/logging_utils.py`).
24. Как классифицируются SMTP ошибки permanent/transient (`config/email_delivery.py`).
25. Как support-обращения создаются и почему есть honeypot + personal data consent (`support/forms.py`).
26. Какие email-события отправляются по заказам и в какой момент (`OrderNotificationService` + `on_commit`).
27. Как работает auto-cancel pickup заказов и что такое business-day deadline.
28. Какие сценарии уже покрыты тестами конкурентности и idempotency (`orders/tests.py`, `store/tests/tests.py`).
29. Как устроен CI/CD pipeline в `.github/workflows/ci-cd.yml` (ci → docker → deploy).
30. Какие текущие техдолги/риски проекта (документация, TLS story, `.htpasswd`, декомпозиция `orders/services.py`).

---

## Мини-чек перед собеседованием

- Умею за 2–3 минуты объяснить checkout flow по шагам.
- Умею нарисовать переходы статусов заказа и назвать запреты.
- Могу объяснить, почему без lock/idempotency проект сломался бы под параллельной нагрузкой.
- Могу рассказать, что будет при падении Redis/SMTP/worker.
- Могу назвать, какие улучшения сделал бы в первую очередь и почему.

