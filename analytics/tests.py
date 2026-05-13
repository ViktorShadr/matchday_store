from decimal import Decimal

from django.template import Context, Template
from django.test import TestCase, override_settings
from django.urls import reverse

from analytics.metrika import (
    build_metrika_config,
    build_purchase_event,
)
from orders.models import Order, OrderItem
from store.models import Category, Product, ProductVariant


class YandexMetrikaConfigTest(TestCase):
    @override_settings(METRIKA_ACTIVE=False, METRIKA_COUNTER_ID="123456")
    def test_config_is_disabled_when_metrika_is_not_active(self):
        self.assertEqual(build_metrika_config(), {"enabled": False})

    @override_settings(METRIKA_ACTIVE=True, METRIKA_COUNTER_ID="123456", METRIKA_REQUIRE_CONSENT=False)
    def test_template_tag_renders_counter_once_with_safe_json(self):
        event = {
            "event": "view_item",
            "ecommerce": {
                "currencyCode": "RUB",
                "detail": {
                    "products": [
                        {
                            "id": "SKU-1",
                            "name": '</script><img src=x onerror="alert(1)">',
                        }
                    ]
                },
            },
        }

        html = Template("{% load metrika_tags %}{% yandex_metrika %}").render(
            Context(
                {
                    "yandex_metrika": build_metrika_config(),
                    "metrika_pending_events": [],
                    "metrika_page_events": [event],
                }
            )
        )

        self.assertIn('id="matchday-metrika-config"', html)
        self.assertIn('id="matchday-metrika-events"', html)
        self.assertIn("/static/js/metrika.js?v=1", html)
        self.assertEqual(html.count("/static/js/metrika.js?v=1"), 1)
        self.assertIn("https://mc.yandex.ru/watch/123456", html)
        self.assertNotIn('</script><img src=x onerror="alert(1)">', html)
        self.assertIn("\\u003C/script\\u003E\\u003Cimg", html)


class YandexMetrikaEcommercePayloadTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Шарфы")
        self.product = Product.objects.create(name="Шарф ФК Шинник", category=self.category)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="SCARF-BLUE",
            size="One Size",
            color="Синий",
            price=Decimal("1990.00"),
            quantity=5,
        )

    def test_purchase_event_contains_order_data_without_customer_pii(self):
        order = Order.objects.create(
            number="ORD-TEST-1",
            user=None,
            recipient_name="Иван Иванов",
            email="buyer@example.com",
            phone="+79990001122",
            status=Order.Status.PLACED,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.NEW,
            delivery_method=Order.DeliveryMethod.PICKUP,
            subtotal_amount=Decimal("3980.00"),
            delivery_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("3980.00"),
            currency="RUB",
        )
        order_item = OrderItem.objects.create(
            order=order,
            product_variant=self.variant,
            product_name_snapshot=self.product.name,
            sku_snapshot=self.variant.sku,
            size_snapshot=self.variant.size,
            color_snapshot=self.variant.color,
            unit_price=self.variant.price,
            quantity=2,
            line_total=Decimal("3980.00"),
        )

        event = build_purchase_event(order, [order_item])

        purchase = event["ecommerce"]["purchase"]
        self.assertEqual(purchase["actionField"]["id"], "ORD-TEST-1")
        self.assertEqual(purchase["actionField"]["revenue"], 3980.0)
        self.assertNotIn("buyer@example.com", str(event))
        self.assertNotIn("+79990001122", str(event))

        product = purchase["products"][0]
        self.assertEqual(product["id"], "SCARF-BLUE")
        self.assertEqual(product["sku"], "SCARF-BLUE")
        self.assertEqual(product["category"], "Шарфы")
        self.assertEqual(product["quantity"], 2)
        self.assertEqual(product["line_total"], 3980.0)

    @override_settings(METRIKA_ACTIVE=True, METRIKA_COUNTER_ID="123456")
    def test_add_to_cart_json_response_includes_event_only_when_metrika_active(self):
        response = self.client.post(
            reverse("store:add_to_cart"),
            data={"variant_id": str(self.variant.id), "quantity": "2"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["cart_total"], 2)
        self.assertEqual(payload["metrika_event"]["event"], "add_to_cart")
        product = payload["metrika_event"]["ecommerce"]["add"]["products"][0]
        self.assertEqual(product["id"], "SCARF-BLUE")
        self.assertEqual(product["quantity"], 2)
