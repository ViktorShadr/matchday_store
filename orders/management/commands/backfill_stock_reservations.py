from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from orders.models import Order, OrderItem
from store.models import ProductVariant


class Command(BaseCommand):
    """Backfill stock reservations for orders created before reserve mode."""

    help = (
        "Backfill ProductVariant.reserved_quantity for active unissued orders "
        "created before checkout started reserving stock."
    )

    ACTIVE_ORDER_STATUSES = (
        Order.Status.PLACED,
        Order.Status.AWAITING_PAYMENT,
        Order.Status.PAID,
        Order.Status.PROCESSING,
        Order.Status.SHIPPED,
    )
    FINAL_FULFILLMENT_STATUSES = (
        Order.FulfillmentStatus.DELIVERED,
        Order.FulfillmentStatus.CANCELLED,
        Order.FulfillmentStatus.RETURNED,
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply changes. Without this flag the command only prints a dry-run summary.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow applying while STOCK_RESERVE_MODE_ENABLED=True.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        force = options["force"]

        if apply_changes and getattr(settings, "STOCK_RESERVE_MODE_ENABLED", True) and not force:
            raise CommandError(
                "Refusing to apply while STOCK_RESERVE_MODE_ENABLED=True. "
                "Set it to False for the maintenance window or pass --force."
            )

        with transaction.atomic():
            locked_variants = {
                variant.pk: variant for variant in ProductVariant.objects.select_for_update().order_by("pk")
            }
            demand_by_variant = self._get_active_order_demand()

            summary = {
                "active_variants": len(demand_by_variant),
                "required_reserved": sum(demand_by_variant.values()),
                "missing_reserved": 0,
                "over_reserved": 0,
                "updated_variants": 0,
            }

            for variant_id, required_reserved in sorted(demand_by_variant.items()):
                variant = locked_variants.get(variant_id)
                if variant is None:
                    continue

                current_reserved = variant.reserved_quantity or 0
                if current_reserved > required_reserved:
                    summary["over_reserved"] += current_reserved - required_reserved
                    continue

                missing_reserved = required_reserved - current_reserved
                if missing_reserved <= 0:
                    continue

                summary["missing_reserved"] += missing_reserved
                summary["updated_variants"] += 1

                if apply_changes:
                    ProductVariant.objects.filter(pk=variant.pk).update(
                        quantity=F("quantity") + missing_reserved,
                        reserved_quantity=F("reserved_quantity") + missing_reserved,
                        updated_at=timezone.now(),
                    )

        mode = "APPLIED" if apply_changes else "DRY-RUN"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: active_variants={summary['active_variants']}, "
                f"required_reserved={summary['required_reserved']}, "
                f"missing_reserved={summary['missing_reserved']}, "
                f"updated_variants={summary['updated_variants']}, "
                f"over_reserved={summary['over_reserved']}"
            )
        )
        if not apply_changes:
            self.stdout.write("Run again with --apply during the maintenance window to write changes.")

    def _get_active_order_demand(self) -> dict[int, int]:
        rows = (
            OrderItem.objects.filter(
                product_variant_id__isnull=False,
                order__status__in=self.ACTIVE_ORDER_STATUSES,
            )
            .exclude(order__fulfillment_status__in=self.FINAL_FULFILLMENT_STATUSES)
            .values("product_variant_id")
            .annotate(required_reserved=Sum("quantity"))
            .order_by("product_variant_id")
        )
        return {row["product_variant_id"]: row["required_reserved"] or 0 for row in rows}
