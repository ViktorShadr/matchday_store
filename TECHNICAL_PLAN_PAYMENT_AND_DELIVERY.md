# Technical Plan: Payment and Delivery Integration

## Goal
Prepare the project for payment system and delivery integration without breaking catalog, cart, and user flows.

## Current State
- The project has catalog, cart, and user profile functionality.
- There is no full order domain model.
- There is no checkout flow.
- There is no payment provider integration.
- There is no delivery provider integration.
- There is no stock reservation flow for paid orders.
- The cart page still has a placeholder checkout action.

## Stage 1. Order Domain
Separate cart data from order data and introduce immutable order snapshots.

### 1.1 Address model <span style="background-color:#d1fae5;color:#065f46;padding:2px 8px;border-radius:999px;font-weight:600;">DONE</span>

Implemented `Address` in the `orders` application with the following fields:
- `user`
- `recipient_name`
- `phone`
- `country`
- `city`
- `postal_code`
- `street`
- `house`
- `building`
- `apartment`
- `comment`
- `is_default`

Notes:
- Model created in `orders.models.Address`
- App connected in Django settings
- Admin registration added
- Initial migration created

### 1.2 Order model <span style="background-color:#d1fae5;color:#065f46;padding:2px 8px;border-radius:999px;font-weight:600;">DONE</span>

Implemented `Order` in the `orders` application with the following fields:
- `number`
- `user`
- `email`
- `phone`
- `status`
- `payment_status`
- `fulfillment_status`
- `delivery_method`
- `delivery_address`
- `pickup_point_code`
- `subtotal_amount`
- `delivery_amount`
- `discount_amount`
- `total_amount`
- `currency`
- `customer_comment`
- `source_cart_id`
- `created_at`
- `updated_at`
- `confirmed_at`
- `paid_at`
- `cancelled_at`

Notes:
- Model created in `orders.models.Order`
- Admin registration added
- Status enums added for order, payment, and fulfillment
- Migration created

### 1.3 OrderItem model <span style="background-color:#d1fae5;color:#065f46;padding:2px 8px;border-radius:999px;font-weight:600;">DONE</span>

Implemented `OrderItem` in the `orders` application with the following fields:
- `order`
- `product_variant`
- `product_name_snapshot`
- `sku_snapshot`
- `size_snapshot`
- `color_snapshot`
- `unit_price`
- `quantity`
- `line_total`

Notes:
- Model created in `orders.models.OrderItem`
- Link to `store.ProductVariant` is nullable to preserve order history
- Admin registration added
- Inline display added to order admin
- Migration created

### 1.4 Payment model
Add `Payment` with fields:
- `order`
- `provider`
- `provider_payment_id`
- `idempotency_key`
- `status`
- `amount`
- `currency`
- `raw_request`
- `raw_response`
- `failure_reason`
- `paid_at`
- `refunded_amount`

### 1.5 Shipment model
Add `Shipment` with fields:
- `order`
- `provider`
- `status`
- `delivery_type`
- `tariff_code`
- `tracking_number`
- `provider_order_id`
- `label_url`
- `pickup_point_code`
- `cost`
- `raw_response`
- `shipped_at`
- `delivered_at`

### 1.6 Event log models
Add audit models such as:
- `OrderEvent`
- `PaymentEvent`

They should store:
- event type
- external payload
- processing status
- timestamps
- link to order/payment

### 1.7 Status enums
Introduce explicit enums.

`OrderStatus`:
- `draft`
- `placed`
- `awaiting_payment`
- `paid`
- `processing`
- `shipped`
- `delivered`
- `cancelled`
- `refunded`

`PaymentStatus`:
- `pending`
- `requires_action`
- `succeeded`
- `failed`
- `cancelled`
- `refunded`

`FulfillmentStatus`:
- `new`
- `reserved`
- `packing`
- `shipped`
- `delivered`
- `returned`
- `cancelled`

## Stage 2. Checkout Flow
Build a real checkout path from cart to order creation.

### 2.1 Checkout page
Add `/checkout/` with the following blocks:
- contacts
- delivery
- payment method
- order confirmation

### 2.2 Checkout forms
Create dedicated forms:
- `ContactForm`
- `AddressForm`
- `DeliveryForm`
- `PaymentMethodForm`

### 2.3 Create order from cart
When checkout is submitted:
- validate cart is not empty
- validate stock availability
- validate contact and address data
- create `Order`
- copy cart items into `OrderItem`
- save price snapshots
- save total amounts

### 2.4 Freeze order data
After order creation:
- product price changes must not affect the order
- product title changes must not affect the order
- variant attribute changes must not affect the order

### 2.5 Cart cleanup rule
Define and implement one rule:
- clear cart after order is placed
or
- clear cart only after successful payment

This must be explicit and consistent.

## Stage 3. Stock Consistency
Payment integration is unsafe without inventory reservation.

### 3.1 Reservation strategy
Replace the simple stock model with one of these approaches:
- `available_quantity` + `reserved_quantity`
or
- dedicated stock reservation model

### 3.2 Reserve stock on order placement
During checkout:
- lock variants with `select_for_update()`
- reserve required quantity transactionally

### 3.3 Confirm stock write-off on payment success
After successful payment:
- convert reservation into actual stock deduction

### 3.4 Release stock
On failure, timeout, or cancellation:
- release reservation

### 3.5 Expiration cleanup
Add a periodic task for expired unpaid orders and stale reservations.

## Stage 4. Payment Integration
Implement payments through a provider abstraction.

### 4.1 Payment gateway interface
Introduce a gateway layer with methods:
- `create_payment`
- `get_payment`
- `cancel_payment`
- `refund_payment`
- `handle_webhook`

### 4.2 Payment configuration
Add environment settings such as:
- `PAYMENT_PROVIDER`
- `PAYMENT_SHOP_ID`
- `PAYMENT_SECRET_KEY`
- `PAYMENT_WEBHOOK_SECRET`
- `PAYMENT_RETURN_URL`
- `PAYMENT_CURRENCY`

### 4.3 Webhook endpoint
Add a secure webhook endpoint, for example:
- `/payments/webhook/`

### 4.4 Idempotency
Store and use an idempotency key for each payment creation request.

### 4.5 Source of truth
Do not trust frontend redirects as payment confirmation.
Use:
- provider webhook
or
- server-side verification API call

### 4.6 Required payment scenarios
Support:
- `pending`
- `succeeded`
- `failed`
- duplicate webhook
- cancellation
- refund

### 4.7 Logging
Log:
- outbound payment requests
- inbound webhooks
- provider errors
- order state transitions

## Stage 5. Delivery Integration
Implement shipping through a dedicated abstraction layer.

### 5.1 Delivery gateway interface
Introduce methods:
- `calculate`
- `create_shipment`
- `get_label`
- `track`
- `cancel`

### 5.2 Delivery methods
Add supported methods such as:
- `pickup`
- `courier`
- `pvz`

### 5.3 Pickup point support
For pickup and parcel locker flows, store:
- pickup point code
- pickup point address
- provider metadata

### 5.4 Delivery price calculation
Before payment:
- calculate delivery cost
- include it in `Order.delivery_amount`
- include it in `Order.total_amount`

### 5.5 Shipment creation
After successful payment:
- create shipment with provider
- save provider IDs
- save tracking number
- save label URL if available

### 5.6 Tracking
Add:
- manual tracking refresh
- automatic tracking updates

Shipment updates should also update order fulfillment status where appropriate.

## Stage 6. UI and Admin
Make the order lifecycle visible to staff and customers.

### 6.1 Customer pages
Add:
- `checkout`
- `checkout_success`
- `order_detail`
- `order_list`

### 6.2 Cart page update
Replace the placeholder checkout button with a real route to checkout.

### 6.3 Admin models
Register in admin:
- `Order`
- `OrderItem`
- `Payment`
- `Shipment`
- `Address`
- event log models

### 6.4 Admin usability
Add:
- filters by status
- search by order number
- search by email and phone
- search by `provider_payment_id`
- search by `tracking_number`
- readonly provider payload views

## Stage 7. Security and Operations
Do not connect real payments before production hardening.

### 7.1 Production-safe settings
Configure:
- `DEBUG=False` in production
- mandatory `SECRET_KEY`
- `SESSION_COOKIE_SECURE`
- `CSRF_COOKIE_SECURE`
- `SECURE_PROXY_SSL_HEADER`
- HSTS settings
- `SECURE_SSL_REDIRECT` if required

### 7.2 Logging and monitoring
Add structured logging for:
- `orders`
- `payments`
- `delivery`
- `webhooks`

Optional but recommended:
- Sentry or equivalent monitoring

### 7.3 Reproducible local environment
Expand `docker-compose` to include:
- `web`
- `db`
- `redis`
- `worker`
- `beat`

### 7.4 Documentation
Document:
- local setup
- migrations
- test run
- celery worker run
- webhook local testing flow

## Stage 8. Testing
Integration without test coverage is not acceptable.

### 8.1 Unit tests
Add tests for:
- order creation from cart
- amount calculation
- address validation
- stock reservation
- stock release

### 8.2 Integration tests
Add tests for:
- payment creation
- payment webhook processing
- duplicate webhook handling
- delivery quote calculation
- shipment creation

### 8.3 End-to-end scenarios
Cover:
- `cart -> checkout -> payment pending`
- `cart -> checkout -> payment success -> stock deduction`
- `payment failure -> reservation release`
- `paid order -> shipment creation`

### 8.4 Test environment
Make test execution reproducible without manual PostgreSQL preparation.

## Recommended Implementation Order
1. Add `Address`, `Order`, `OrderItem`, `Payment`, `Shipment`.
2. Implement checkout and order creation from cart.
3. Implement stock reservation and release.
4. Add customer order pages and admin support.
5. Implement payment abstraction and webhook processing.
6. Implement delivery abstraction and shipment flow.
7. Add logging, security hardening, docker improvements, and documentation.
8. Add full automated tests.

## Minimum MVP
If the goal is to reach a first production-capable version with minimal scope:

1. Add `Order`, `OrderItem`, `Payment`, `Address`.
2. Add one delivery method: `courier`.
3. Add one payment method/provider.
4. Add one webhook endpoint.
5. Add stock reservation.
6. Add checkout page.
7. Add admin for orders and payments.
8. Add tests for the main happy path.

## Immediate P0 Before Provider Integration
- Create order domain models.
- Implement checkout.
- Implement stock reservation.
- Implement payment webhook processing.
- Add delivery address and delivery method support.
- Make local/dev/test environment reproducible.
- Add automated tests for order/payment flow.
