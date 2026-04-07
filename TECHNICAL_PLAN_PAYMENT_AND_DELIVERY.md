# Technical Plan: MVP Production Readiness

## Goal
Prepare the project for a first production launch as an MVP with the following scope:
- pickup from store only
- payment on receipt only
- no online payment provider
- no external delivery provider

The plan below prioritizes a working and supportable order flow in production over future integrations.

## Product Scope for MVP

### Included in MVP
- catalog browsing
- cart management
- user authentication
- checkout for authenticated users
- one delivery method: `pickup`
- one payment method: `manual` / pay on receipt
- order creation from cart
- order visibility in admin
- manual staff processing of orders

### Explicitly excluded from MVP
- online payments
- payment webhooks
- courier delivery
- PVZ integrations
- shipment providers
- delivery price calculation via external APIs
- automatic stock reservation release by timeout

## Current State
- Catalog, cart, and user profile flows are present.
- `Order`, `OrderItem`, `Address`, and `Payment` models already exist.
- `Payment` admin and payment status sync logic already exist.
- There is still no real checkout flow.
- The cart page still contains a placeholder checkout action.
- The current order model is broader than MVP and is not yet aligned with pickup-only checkout.
- The current infrastructure is not production-ready yet.

## Release Decision
The next release should target a narrower scope than the original integration plan:
- launch with `pickup` only
- treat payment as manual settlement at pickup
- create orders without payment provider integration
- postpone real delivery and online payment integrations until after MVP launch

## Stage 1. Align Domain Model With MVP
Keep the existing order domain, but make it compatible with pickup-only checkout.

### 1.1 Address model <span style="background-color:#d1fae5;color:#065f46;padding:2px 8px;border-radius:999px;font-weight:600;">DONE</span>
Implemented in `orders.models.Address`.

MVP note:
- address management may remain in the project
- address must not be required for pickup-only checkout

### 1.2 Order model <span style="background-color:#d1fae5;color:#065f46;padding:2px 8px;border-radius:999px;font-weight:600;">PARTIAL</span>
Implemented in `orders.models.Order`, but requires MVP adjustments.

Required MVP changes:
- make `delivery_address` optional for `pickup`
- set `delivery_method` default to `pickup`, or force it in checkout service
- define one store pickup location source of truth
- keep `pickup_point_code` or replace it with a simpler `pickup_location_code`
- ensure order creation does not depend on courier-specific data

### 1.3 OrderItem model <span style="background-color:#d1fae5;color:#065f46;padding:2px 8px;border-radius:999px;font-weight:600;">DONE</span>
Implemented in `orders.models.OrderItem`.

MVP note:
- use immutable snapshots during checkout
- preserve item title, attributes, and price at order creation time

### 1.4 Payment model <span style="background-color:#d1fae5;color:#065f46;padding:2px 8px;border-radius:999px;font-weight:600;">PARTIAL</span>
Implemented in `payments.models.Payment`, but only part of it is needed for MVP.

MVP usage:
- use `provider=manual`
- create a payment record only if it simplifies admin operations
- keep status transitions manual from admin for now

Post-MVP:
- external providers
- provider IDs
- webhook payload processing

### 1.5 Shipment model
Deferred until post-MVP.

Reason:
- pickup from store does not require shipment creation
- introducing `Shipment` now adds complexity without supporting the first release

### 1.6 Event log models
Deferred until post-MVP.

MVP substitute:
- rely on Django admin history
- add concise application logs for checkout and order creation

### 1.7 Status enums <span style="background-color:#d1fae5;color:#065f46;padding:2px 8px;border-radius:999px;font-weight:600;">DONE</span>
Enums already exist and can be reused.

MVP recommendation:
- `Order.status`: start with `placed`, then manual progression by staff
- `Order.payment_status`: keep `pending` until paid at pickup
- `Order.fulfillment_status`: start with `new` and move manually

## Stage 2. Build Real MVP Checkout
Implement the shortest complete path from cart to placed order.

### 2.1 Checkout route and page
Add `/checkout/` for authenticated users only.

The page should contain:
- contact data
- pickup location
- payment method summary
- order summary
- submit action

### 2.2 Checkout form scope
Use MVP-specific forms instead of future-proof generic abstractions.

Required fields:
- customer name
- phone
- email
- optional customer comment

Fixed choices in MVP:
- delivery method: `pickup`
- payment method: `manual`
- pickup location: one configured store location

### 2.3 Create order from cart
When checkout is submitted:
- validate that cart is not empty
- re-check stock availability
- lock cart item variants transactionally where needed
- create `Order`
- copy cart items into `OrderItem`
- store immutable price snapshots
- set `delivery_amount=0`
- set `total_amount=subtotal_amount`
- set `payment_status=pending`
- set `status=placed`

### 2.4 Cart cleanup rule
For MVP use one explicit rule:
- clear cart immediately after successful order creation

Reason:
- payment is manual and happens outside the site
- keeping items in cart after order placement increases support noise and duplicate orders

### 2.5 Checkout success page
Add a confirmation page after order placement with:
- order number
- pickup store address
- store opening hours
- payment on receipt explanation
- contact phone for support

## Stage 3. Stock Consistency for MVP
Implement only the level of stock protection required for a safe first launch.

### 3.1 Minimum consistency rule
Before creating an order:
- re-check all cart item quantities against current stock
- fail checkout if any item is unavailable

### 3.2 Transactional order placement
During checkout:
- use `select_for_update()` on affected variants
- create order and order items in one transaction

### 3.3 Stock write-off strategy for MVP
Choose one explicit operational rule and document it.

Recommended MVP rule:
- deduct stock at order placement time

Reason:
- simpler than reservations
- safer for small-volume pickup MVP
- easier for staff to reason about in admin

### 3.4 Cancellation handling
If an order is cancelled before pickup:
- staff restores stock manually or through a simple admin action

Post-MVP:
- reservation model
- timeout release
- automatic stock restoration workflows

## Stage 4. Admin and Backoffice Flow
Staff must be able to process orders without engineering support.

### 4.1 Order admin
Admin must support:
- list of orders
- search by order number
- search by email and phone
- filters by order status
- filters by payment status
- filters by fulfillment status

### 4.2 Operational fields in admin
Staff should be able to view and update:
- pickup location
- customer contacts
- order items
- payment status
- fulfillment status
- internal comment if needed

### 4.3 Manual payment flow
For MVP, payment is recorded manually.

Required admin scenario:
- order is created with unpaid status
- staff prepares order
- customer picks up order and pays
- staff marks payment as received

### 4.4 Minimal staff process documentation
Document:
- how to find a new order
- how to confirm stock and pickup readiness
- how to mark an order as paid
- how to mark an order as completed or cancelled

## Stage 5. Production Infrastructure
The application must be deployable and operable as a web service.

### 5.1 Runtime topology
Add a production-capable app stack:
- `web`
- `db`
- `redis` if Celery remains in use
- `worker` only if background tasks are actually required for MVP

Optional:
- reverse proxy such as Nginx

### 5.2 Application startup
The project must have a clear web entrypoint:
- run migrations
- collect static files
- start Django via Gunicorn

The current container default must not remain worker-only.

### 5.3 Environment configuration
Define and document required environment variables:
- `SECRET_KEY`
- `DEBUG`
- `ALLOWED_HOSTS`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`
- email settings if transactional emails are kept

For MVP, `.env.example` must describe production-safe defaults and required overrides.

### 5.4 Static and media handling
Define production handling for:
- `STATIC_ROOT`
- `MEDIA_ROOT`
- media persistence across deploys

### 5.5 Database readiness
Use PostgreSQL as the supported production database.

Required:
- migrations must run cleanly
- test database creation must be reproducible
- no release dependency on the committed SQLite file

## Stage 6. Production Security Baseline
Implement only the security controls required for a public MVP launch.

### 6.1 Django settings
Configure for production:
- `DEBUG=False`
- mandatory non-empty `SECRET_KEY`
- explicit `ALLOWED_HOSTS`
- `SESSION_COOKIE_SECURE`
- `CSRF_COOKIE_SECURE`
- `SECURE_PROXY_SSL_HEADER`
- `SECURE_SSL_REDIRECT` where applicable
- `CSRF_TRUSTED_ORIGINS`

### 6.2 Admin safety
Before launch:
- create admin users explicitly
- remove any default or shared credentials
- restrict admin exposure to production domain only

### 6.3 Error visibility
Add:
- application logging for checkout and order creation
- server error logging

Recommended:
- Sentry or equivalent monitoring

## Stage 7. Documentation and Operability
The project must be understandable to the next person who deploys or supports it.

### 7.1 README
Fill `README.md` with:
- project purpose
- local startup
- docker startup
- migrations
- admin creation
- static collection
- test run
- production deployment notes

### 7.2 Runbook
Add a short operational runbook covering:
- order processing flow
- pickup and payment workflow
- cancellation handling
- stock correction procedure

### 7.3 Release checklist
Create a pre-release checklist:
- migrations applied
- static files collected
- admin available
- checkout works
- order appears in admin
- cart clears after checkout
- logs are being written

## Stage 8. Testing
MVP launch should be blocked until the core flow is covered by automated tests.

### 8.1 Unit tests
Add tests for:
- order creation from cart
- total amount calculation
- pickup checkout validation
- manual payment status transitions
- stock deduction on order placement

### 8.2 Integration tests
Add tests for:
- authenticated user checkout
- cart to order conversion
- checkout with insufficient stock
- admin payment status update flow

### 8.3 End-to-end smoke scenarios
Cover at minimum:
- `catalog -> cart -> checkout -> order created`
- `order created -> visible in admin`
- `order paid at pickup -> status updated`
- `cancelled order -> stock restored` if restoration is automated

### 8.4 Test environment
Make test execution reproducible without manual database preparation.

Recommended:
- test database configuration for Django
- one documented command that works in a clean environment

## P0 Before MVP Production Launch
- implement real checkout route and form
- create order from cart transactionally
- align order model with pickup-only checkout
- replace placeholder checkout button with real route
- define one pickup location and display it consistently
- implement explicit stock handling on order placement
- ensure orders are manageable in admin
- make Docker/runtime start the web application
- harden production settings
- document setup and release steps
- add tests for the main checkout and admin flow

## Post-MVP
These items should not block the first production launch:
- online payment provider integration
- payment webhooks
- courier delivery
- PVZ support
- shipment model and tracking
- delivery gateway abstraction
- payment gateway abstraction beyond manual payment
- stock reservation expiration jobs
- audit/event log models

## Recommended Implementation Order
1. Align `Order` and checkout data model with pickup-only MVP.
2. Implement checkout, order creation, and cart cleanup.
3. Implement stock deduction strategy and cancellation handling.
4. Finalize admin workflow for manual processing.
5. Build production runtime: web container, migrations, static files, env handling.
6. Harden production settings and logging.
7. Document deployment and support procedures.
8. Add automated tests and release checklist.
