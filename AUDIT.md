# 1. Executive Summary

**Matchday Store** — это не просто CRUD-витрина, а транзакционный backend MVP интернет-магазина с явным фокусом на операционную надежность: защита от overselling, атомарный checkout, идемпотентность оформления, state machine статусов заказа, анти-абуз и production-контур (Docker, Nginx, Gunicorn, Redis, Celery, healthchecks, CI/CD).  

Почему проект сильнее типичного pet-project:
- В центре — **инвентарный домен** (physical stock + reserved stock + available-to-sell), а не «просто Order.create()».  
- Реализован **конкурентный сценарий** оформления заказов через блокировки и транзакции (`select_for_update`, `transaction.atomic`, `F`-обновления).  
- Есть **идемпотентность checkout** через `checkout_token` + `Payment.idempotency_key`, что закрывает double-submit/retry кейсы.  
- Присутствует **доменная политика жизненного цикла заказа** и журнал переходов статусов (`OrderStatusTransition`).  
- Наличие инфраструктурного мышления: docker-compose окружение с healthcheck’ами, выделенный worker/beat, reverse proxy, rate limit, security middleware и logging context.  

Какие бизнес-задачи закрываются:
- Продажа ограниченной атрибутики без перепродажи «виртуального» товара.  
- Контролируемая обработка заказов staff-командой (операционный dashboard).  
- Снижение абуза checkout/login/email flows за счет лимитов и политик.  
- Готовность MVP к выкладке и дальнейшей эволюции в production-платформу.

---

# 2. Архитектура проекта

## 2.1. Разделение на Django apps и зоны ответственности

- `store`: каталог, категории, карточки товара, корзина, warehouse UI/queries/presenters, variant-level остатки и резервы.  
- `orders`: checkout, доменная оркестрация создания/отмены/выдачи заказа, transitions, order-level процессы и шаблоны checkout/success.  
- `payments`: модель платежа + workflow/синхронизация статуса оплаты (сейчас manual provider, но архитектурно задел под расширение).  
- `users`: регистрация/логин/подтверждение email, профиль и user-centric сценарии.  
- `analytics`: метрика/ecommerce events с безопасным включением через env и шаблоны.  
- `config`: settings, middleware, celery bootstrap, health endpoint, rate-limit settings, logging/sentry wiring.

Это хороший SoC: предметные области изолированы, а cross-app интеграции идут через сервисы/репозитории и доменные контракты, а не через хаотичные импорт-цепочки.

## 2.2. Layered architecture

**Presentation layer**
- Django CBV/FBV + forms + templates (и, вероятно, DRF-слой для API сценариев, если расширять).  
- Примеры: `orders/views.py`, `store/views/*`.

**Application / Domain layer**
- Сервисы use-case уровня (`CheckoutService`, `OrderCancellationService`, `PaymentWorkflowService`, app-level policy/service classes).  
- Основная бизнес-логика не зашита в views — это зрелый признак.

**Infrastructure layer**
- Репозитории (`orders/repositories`, `store/repositories`) + ORM модели + Celery брокер + Docker/Nginx/Gunicorn.

Паттерны, которые уже видны:
- Service Layer + Repository abstraction (DIP через интерфейсы).  
- State transition logging.  
- Idempotency key pattern.  
- Transaction Script / Unit of Work через `transaction.atomic`.

## 2.3. Flow запроса: от пользователя до БД

1. Клиент → `nginx` (`:8000`) как reverse proxy и static/media server.  
2. `nginx` проксирует динамику в `gunicorn` (`web` контейнер).  
3. Django view валидирует вход, применяет anti-abuse/rate-limit и вызывает сервисный слой.  
4. Сервис открывает транзакцию, получает row-lock’и, рассчитывает доменную операцию.  
5. ORM пишет в PostgreSQL (orders, items, payments, variant reserves).  
6. На `on_commit` ставятся фоновые уведомления (Celery).  
7. Ответ возвращается пользователю; async уведомления уходят worker’ом через Redis broker.

## 2.4. Checkout / Order / Payment flow

- `CheckoutView` генерирует/проверяет `checkout_token`, не дает оформить пустую корзину, а при POST делегирует оформление в `CheckoutService`.  
- `CheckoutService.create_order_from_cart`:
  - рассчитывает `idempotency_key` (user/session scoped),
  - повторно ищет существующий payment/order,
  - в `transaction.atomic` лочит пользователя (если auth), cart items и product variants,
  - валидирует доступность/цену/лимиты,
  - создает `Order` + `OrderItem` snapshot,
  - создает manual `Payment` с idempotency,
  - резервирует склад,
  - чистит корзину,
  - планирует уведомления после коммита.

Это очень правильный порядок: **сначала консистентные проверки под lock, потом запись заказа/платежа, потом резерв**, а не наоборот.

## 2.5. Логика резервов склада

Ключевая идея: `available_quantity = quantity - reserved_quantity`.  
Операции:
- reserve: `reserved_quantity += qty`, но только если `quantity >= reserved + qty`;  
- release: `reserved_quantity -= qty`, но только если резерв достаточный;  
- issue: `quantity -= qty` и `reserved_quantity -= qty` атомарно.

Обновления идут через `QuerySet.update + F()` — это защищает от lost updates при конкуренции.

## 2.6. Celery tasks

- Redis используется как broker/cache.  
- `OrderNotificationService.schedule_created(...)` вызывается через on-commit-планирование.  
- Worker/beat вынесены в отдельные сервисы compose (профили и отдельные процессы).  
- Важный плюс: бизнес-транзакция не зависит от скорости email-провайдера.

## 2.7. Docker / Nginx / Gunicorn

- `docker-compose.yaml` описывает `nginx`, `web`, `db`, `redis`, optional `worker`, `beat`; для web/nginx/db/redis прописаны healthchecks.  
- `nginx` отдает static/media из volume, динамику шлет в Django.  
- `web-entrypoint` обычно выполняет миграции + collectstatic + запуск gunicorn (по README/runtime описанию).  
- Лог-драйвер с ротацией на уровне контейнера уже учитывается.

Почему production-oriented:
- сервисная декомпозиция,
- healthchecks,
- фоновая очередь,
- rate-limit/security заголовки,
- runbook/backup scripts/CI/CD.

---

# 3. Глубокий разбор бизнес-логики

## 3.1. Как предотвращается overselling

Механизм multi-layer:
1. Проверка доступности на основе `available_quantity` в locked контексте.  
2. `select_for_update` на variants/cart/user — конкурентные checkout-операции сериализуются по тем же SKU.  
3. Атомарный reserve через `UPDATE ... WHERE quantity >= reserved + qty`. Если условие не прошло — фейл без частичного списания.  
4. Финальная выдача (`issue`) проверяет и physical, и reserved остаток.

Этого достаточно для MVP single-DB архитектуры.

## 3.2. Зачем нужен reserve stock

`reserved_quantity` отделяет «обещанный в заказе» товар от свободного к продаже. Это важно, когда:
- заказ создан, но еще не выдан/не оплачен,
- есть задержка между checkout и фактической выдачей,
- staff обрабатывает заказы не мгновенно.

Без reserve второй покупатель может «съесть» тот же stock в окне гонки.

## 3.3. Идемпотентность checkout

Решение:
- `checkout_token` в сессии/форме,
- генерация `payment_idempotency_key` (user/session scoped),
- повторный поиск existing payment/order до и после lock’ов,
- fallback на обработку `IntegrityError` с повторным чтением existing результата.

Закрывает кейсы:
- двойной клик submit,
- retry браузера,
- повторный POST при сетевых глитчах.

## 3.4. Зачем `select_for_update`

Row-level lock обеспечивает **serializable-like behavior локально на затронутых строках** в рамках read-committed:
- две транзакции не могут одновременно «успешно» прочитать и зарезервировать один и тот же последний остаток.

Это дешевле и практичнее, чем полный `SERIALIZABLE` для всего checkout.

## 3.5. Зачем atomic transactions

Чтобы весь use-case был all-or-nothing:
- или заказ + items + payment + reserve + cart cleanup коммитятся вместе,
- или rollback и система остается консистентной.

Особенно критично в ecommerce: нельзя оставить «заказ без резерва» или «резерв без заказа».

## 3.6. Lifecycle заказа

У заказа три оси состояния:
- `status` (бизнес-статус),
- `payment_status`,
- `fulfillment_status`.

Плюс отдельный журнал переходов (`OrderStatusTransition`) для аудита и разборов инцидентов. Это сильный production-сигнал.

## 3.7. Anti-abuse

В checkout есть rate-limit по `ip` и `user_or_ip`, а также бизнес-ограничения:
- максимум активных неоплаченных заказов на пользователя,
- максимум qty на SKU за checkout,
- возможность экстренного стопа через `STOCK_RESERVE_MODE_ENABLED`.

Это practical defense-in-depth для MVP.

## 3.8. Edge cases и риски

- **Deadlock risk**: при сложном перекрытии SKU в разных корзинах. Частично снижен deterministic ordering (`order_by('pk')`), но нужен мониторинг deadlock/retry policy.  
- **Zombie reserves**: если заказ «подвис» долго в RESERVED/NEW без авто-expire/cleanup.  
- **Manual payment flow**: при real payment provider потребуются webhook idempotency/reconciliation.  
- **Cart mutation race**: часть позиций может стать недоступной в момент checkout — сервис корректно удаляет их и возвращает управляемую ошибку.

Почему для MVP решение хорошее:
- высокая целостность данных при умеренной сложности,
- минимальная инфраструктурная стоимость,
- ясная эволюция к полноценным payment/inventory policy.

---

# 4. Production Engineering

## 4.1. Docker architecture

Зрелые элементы:
- разделение на web/nginx/db/redis/worker/beat,
- healthchecks в compose,
- restart policy,
- лог-rotation у контейнеров,
- отдельные volumes для postgres/static/media.

Что улучшать:
- resource limits/cpu/memory quotas,
- отдельная сеть/segmentation для internal-only сервисов,
- иммутабельные image tags + SBOM/vuln scan в CI.

## 4.2. Environment variables и secrets

Плюсы:
- конфиг внешне управляем через env,
- есть README с production-переменными.

Слабые места:
- не видно полноценного secret manager (Vault/SSM/Secrets Manager),
- ротация секретов/паролей не формализована,
- нужен policy: кто/как меняет секреты и как откат.

## 4.3. Deployment flow

Есть CI/CD workflows (lint/test/build/publish), runbook и dockerized delivery path — сильная база.

Что добавить senior-уровня:
- blue/green или rolling deploy strategy,
- DB migration safety checks (expand/contract),
- автоматический smoke-test post-deploy,
- rollback automation.

## 4.4. Healthchecks, backup, observability

Есть:
- `/healthz` и container healthchecks,
- backup/restore scripts в `ops/db`.

Нужно усилить:
- разделить liveness/readiness/deep health,
- мониторинг p95/p99 latency, DB pool saturation, queue lag,
- centralized logs + correlation id across nginx/gunicorn/celery,
- алерты (5xx spike, deadlock, failed tasks, disk usage).

## 4.5. Security practices

Плюсы:
- security headers/CSP controls,
- rate limiting,
- CSRF/host env guidance,
- role/staff разграничение.

Риски:
- нужен formal hardening checklist: TLS, HSTS, secure cookies, trusted proxies,
- dependency scanning и SAST/DAST в CI,
- контроль админ-доступов (MFA, IP allowlist, audit trail).

## 4.6. Nginx hardening

Что уже ок:
- reverse proxy separation,
- static/media offload,
- health endpoint.

Что добавить:
- лимиты body/request size/timeout tuned по endpoint-классам,
- stricter TLS ciphers/policies (если TLS termination здесь),
- bot mitigation/WAF хотя бы на уровне managed edge.

---

# 5. Backend Engineering Review (senior-level)

## Сильные стороны

- **CheckoutService как orchestration ядро**: логика явно централизована, testability выше.  
- **Concurrency discipline**: lock + atomic + F expressions + idempotency.  
- **State tracking**: transitions журналирует изменения статусов.  
- **Repository abstraction**: удобный seam для unit/integration тестов.  
- **Anti-abuse как бизнес-правила**, а не только infra ratelimit.

## Что выглядит junior/middle-ish

- Местами монолитные сервисы (много обязанностей в одном классе).  
- Вероятно недостаток explicit domain invariants в БД (часть правил в Python, а не constraints).  
- Manual payment как временное решение — ок для MVP, но требует аккуратного позиционирования на защите.

## Что может быть overengineered

- Для раннего MVP интерфейсы репозиториев + presenters + queries могут показаться тяжеловесными, если команда 1-2 человека и мало endpoint’ов.  
- Но это оправдано, если цель — демонстрация архитектурной зрелости и дальнейшее масштабирование.

## Что рефакторить приоритетно

1. Разбить `CheckoutService` на шаги/handlers (validation, pricing, reservation, payment creation, post-commit hooks).  
2. Формализовать state machine (transition matrix + guard clauses в одном месте).  
3. Добавить retry strategy при deadlock/serialization failure на transaction boundary.  
4. Вынести warehouse-policy (reserve ttl, auto-release) в отдельный bounded context модуль.

## Потенциально опасные зоны

- Высокая связность между order/payment/warehouse внутри одного use-case.  
- Риск «тихого» дрейфа статусов при ручных staff действиях без централизованных guard’ов.  
- Рост сложности при подключении реального PSP/webhooks без anti-corruption layer.

## Оценка отдельных частей

- **Service layer**: сильный (middle+/senior mindset), но нуждается в декомпозиции.  
- **Presenters**: полезны для шаблонного UI и снижения логики в views; для API лучше serializer-centric подход.  
- **Checkout flow**: сильнейшая часть проекта (конкурентность + idempotency).  
- **Warehouse logic**: адекватна MVP, особенно reserve/issue/release триада.  
- **Order status management**: хороший базис, следующий шаг — строгий transition policy engine.

---

# 6. Возможные вопросы tech lead на собеседовании

Q: Почему вы выбрали `select_for_update`, а не просто проверку остатка в Python?  
A: Потому что Python-проверка без row lock не защищает от race condition между конкурентными checkout. `select_for_update` сериализует доступ к тем же SKU-строкам и делает проверку+обновление консистентными.

Q: Как вы обеспечили идемпотентность checkout?  
A: Через `checkout_token` + `payment_idempotency_key`, повторный поиск уже созданного платежа/заказа до и после захвата блокировок и обработку `IntegrityError` как допустимого конкурентного сценария.

Q: Что защищает от overselling?  
A: Комбинация row-lock, транзакции и условного `UPDATE ... WHERE quantity >= reserved + qty`/`reserved >= qty`; это исключает отрицательный available stock.

Q: Почему не SERIALIZABLE isolation?  
A: Для MVP это дорого по latency/abort-rate. Мы локализовали консистентность на критических строках через explicit locks + conditional updates.

Q: Где проходит граница между view и бизнес-логикой?  
A: View отвечает за HTTP/session/form/rate-limit, сервис — за доменный use-case и транзакционные инварианты.

Q: Как работает отмена заказа?  
A: В atomic-блоке лочится заказ и его variant-ы, проверяется cancellable policy, снимается резерв, отменяются manual payments, обновляются статусы и пишутся transitions.

Q: Зачем separate `reserved_quantity`?  
A: Чтобы разделить физический остаток и обещанный к выдаче, иначе pending-заказы не защищают товар от повторной продажи.

Q: Как обрабатываются недоступные позиции в корзине при checkout?  
A: Они детектируются под lock, удаляются из корзины в той же транзакции, пользователь получает управляемый ответ/ошибку.

Q: Какие анти-абуз меры есть?  
A: Endpoint rate-limit (`ip`, `user_or_ip`), лимит активных неоплаченных заказов, лимит qty per SKU, флаг глобальной остановки checkout.

Q: Как связаны Nginx и Gunicorn?  
A: Nginx принимает внешние запросы и static/media, динамические HTTP проксирует в gunicorn внутри web-контейнера.

Q: Зачем Celery, если можно sync email?  
A: Async исключает влияние внешнего SMTP на latency checkout и повышает устойчивость user flow.

Q: Как вы бы подключили реальный платежный провайдер?  
A: Добавил бы provider adapter, webhook endpoint с signature verification и webhook-idempotency store, затем reconciliation job.

Q: Что в PostgreSQL критично для этого проекта?  
A: Индексы по FK/статусам/датам, lock monitoring (`pg_locks`), вакуум/автовакуум, контроль long transactions.

Q: Какие тесты обязательны?  
A: Конкурентные integration tests для checkout/cancel/issue, idempotency tests, transition-policy tests, chaos/retry tests для Celery.

Q: Как масштабировать под рост трафика?  
A: Горизонтально web/worker, Redis/DB tuning, read replicas для чтения, кэширование каталога, затем выделение inventory/order bounded contexts.

Q: Что будет bottleneck №1?  
A: Contention на hot SKU при checkout и write-load на order/payment tables.

Q: Как решать contention hot SKU?  
A: Быстрые транзакции, deterministic lock order, retry with backoff, возможно reservation queue/partitioning по SKU.

Q: Как организован healthcheck?  
A: Есть `/healthz` и container-level checks, но в зрелой версии стоит развести liveness/readiness/dependency checks.

Q: Какой риск у manual status updates staff?  
A: Возможны недопустимые переходы без строгой матрицы; нужен centralized transition engine и аудит.

Q: Почему проект production-oriented?  
A: Потому что учитывает операционные риски (конкурентность, идемпотентность, observability, deployment, anti-abuse), а не ограничивается CRUD.

---

# 7. Слабые места проекта (честно)

1. Нет полного enterprise-grade observability стека (metrics/tracing/alerting dashboards).  
2. Payment subsystem пока MVP/manual-first; при интеграции PSP сложность вырастет резко.  
3. Потенциальные deadlocks/lock wait под burst-нагрузкой на одни и те же SKU.  
4. Нет явно описанной стратегии авто-истечения резервов (reservation TTL/sweeper).  
5. Вероятно недостаточно formal security governance (secret rotation, access audit, MFA policy).  
6. Возможен рост связности внутри checkout orchestration по мере добавления акций/доставки/платежей.

Что из этого нормальный MVP-компромисс:
- manual payment,
- ограниченная observability,
- монолитная кодовая база,
- частично ручной ops.

Это приемлемо, если clearly stated roadmap есть и архитектура не блокирует эволюцию.

---

# 8. План эволюции проекта

## 8.1. Краткосрочно (1–2 спринта)

- Ввести transition matrix policy engine.  
- Добавить reservation TTL + periodic cleanup task (Celery beat).  
- Расширить интеграционные тесты конкурентных сценариев.  
- Подключить централизованный error tracking + базовые SLI/SLO.

## 8.2. Среднесрочно

- Подключить PSP (Webhook + idempotent processing + reconciliation).  
- Вынести read-heavy каталожные endpoint’ы в DRF + кеш слой (Redis).  
- Ввести outbox pattern для надежной доставки доменных событий.

## 8.3. Масштабирование

- Horizontal scaling web/worker.  
- Оптимизация БД: индексы, partitioning по orders/payments при росте.  
- Read replicas для аналитических/исторических запросов.

## 8.4. Переход к микросервисам (если действительно нужен)

Не делать рано. Триггеры к выделению сервисов:
- независимые команды,
- разные профили нагрузки,
- SLA/релизная независимость.

Первый кандидат на выделение — **inventory service**, второй — **payment integration service**. До этого лучше modular monolith + clear bounded contexts.

## 8.5. Подготовка к high load

- Performance budget на checkout latency.  
- Load-test на hot SKU и массовые parallel checkout.  
- Retry/backoff policies, circuit breakers на внешние интеграции.  
- Очереди фоновых задач с DLQ и мониторингом lag.

---

# 9. Оценка уровня разработчика

Текущий уровень по этому проекту: **уверенный junior+ / ближе к middle**.

Почему:
- Есть инженерное мышление про консистентность данных и конкуренцию.  
- Понимание production-контуров выше среднего junior.  
- Наличие сервисного слоя и доменных правил отличает от «forms + fat views».

Что отделяет от полноценного middle:
- нужно больше зрелых решений по observability, resilience и operational automation,
- нужна более строгая формализация state machine и отказоустойчивости внешних интеграций.

Для резюме проект сильный:
- конкурентоспособен против типичных CRUD pet-project,
- дает предмет для глубоких технических вопросов на интервью,
- демонстрирует practical backend mindset.

---

# 10. Итоговая оценка проекта

**Итог:** проект близок к реальному production-MVP и уже демонстрирует зрелые backend-практики для e-commerce домена. Ключевая ценность — корректная работа в конкурентных сценариях checkout/stock reservation.

Strongest points:
- транзакционность и anti-oversell,
- идемпотентный checkout,
- структурированная архитектура слоев,
- dockerized infra + CI/CD + healthchecks.

Critical improvements:
- формализованная state machine policy,
- усиление observability/alerting,
- эволюция payment integration и reconciliation,
- нагрузочные тесты и lock-contention стратегия.

---

## Как защищать этот проект на собеседовании

### Как рассказывать
- Стройте рассказ вокруг **бизнес-риска overselling** и того, как архитектура его закрывает.  
- Порядок питча: домен → инварианты → транзакционная реализация → production-контур.  
- Используйте конкретику: `select_for_update`, `transaction.atomic`, `F()` updates, idempotency key.

### На чем делать акцент
- На инженерных компромиссах MVP vs production.  
- На том, что вы думали не только о «счастливом пути», но и о race/retry/duplicate submit.  
- На операционной стороне: деплой, мониторинг, healthchecks, восстановление.

### Что не говорить
- «Я сделал микросервисную архитектуру» (если фактически modular monolith).  
- «Гонок нет вообще» (вместо этого: какие гонки закрыты, какие остаются и как мониторятся).  
- «Производительность будет норм» без цифр/тестов.

### Если начинают копать глубже
- Спокойно рисуйте sequence checkout и точки lock’ов.  
- Объясняйте, почему выбран именно такой уровень изоляции и где trade-off latency vs strictness.  
- Признавайте слабые места и сразу давайте roadmap исправлений (TTL reserve, webhook idempotency, observability).
