# Generated for notification outbox migration.

from django.db import migrations, models


def backfill_notification_outbox_fields(apps, schema_editor):
    OrderNotificationLog = apps.get_model("orders", "OrderNotificationLog")
    used_idempotency_keys = set(
        OrderNotificationLog.objects.exclude(idempotency_key__isnull=True)
        .exclude(idempotency_key="")
        .values_list("idempotency_key", flat=True)
    )

    for notification_log in OrderNotificationLog.objects.order_by(
        "order_id",
        "notification_type",
        "recipient_type",
        "-sent_at",
        "-created_at",
        "-id",
    ):
        event_key = notification_log.event_key or notification_log.notification_type
        recipient_type = notification_log.recipient_type or "customer"
        recipient_list_snapshot = notification_log.recipient_list_snapshot or []
        if not recipient_list_snapshot and notification_log.recipient_email:
            recipient_list_snapshot = [notification_log.recipient_email]

        idempotency_key = f"order-notification:{notification_log.order_id}:{event_key}:{recipient_type}"
        if idempotency_key in used_idempotency_keys:
            idempotency_key = None
        else:
            used_idempotency_keys.add(idempotency_key)

        OrderNotificationLog.objects.filter(pk=notification_log.pk).update(
            event_key=event_key,
            recipient_type=recipient_type,
            recipient_list_snapshot=recipient_list_snapshot,
            last_error=notification_log.last_error or notification_log.error_message,
            idempotency_key=idempotency_key,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0012_ordernotificationlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="ordernotificationlog",
            name="event_key",
            field=models.CharField(
                choices=[
                    ("created", "Заказ принят"),
                    ("cancelled", "Заказ отменен"),
                    ("ready", "Готов к выдаче"),
                    ("paid", "Оплата подтверждена"),
                    ("staff_created", "Новый заказ для сотрудников"),
                ],
                db_index=True,
                default="",
                max_length=32,
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="ordernotificationlog",
            name="notification_type",
            field=models.CharField(
                choices=[
                    ("created", "Заказ принят"),
                    ("cancelled", "Заказ отменен"),
                    ("ready", "Готов к выдаче"),
                    ("paid", "Оплата подтверждена"),
                    ("staff_created", "Новый заказ для сотрудников"),
                ],
                db_index=True,
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="ordernotificationlog",
            name="recipient_type",
            field=models.CharField(
                choices=[("customer", "Покупатель"), ("staff", "Сотрудники")],
                db_index=True,
                default="customer",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="ordernotificationlog",
            name="recipient_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="ordernotificationlog",
            name="recipient_list_snapshot",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="ordernotificationlog",
            name="subject",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="ordernotificationlog",
            name="message",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="ordernotificationlog",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Ожидает отправки"),
                    ("sending", "Отправляется"),
                    ("sent", "Отправлено"),
                    ("failed", "Ошибка"),
                ],
                db_index=True,
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="ordernotificationlog",
            name="attempts_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="ordernotificationlog",
            name="last_error",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ordernotificationlog",
            name="idempotency_key",
            field=models.CharField(blank=True, editable=False, max_length=128, null=True, unique=True),
        ),
        migrations.RunPython(backfill_notification_outbox_fields, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="ordernotificationlog",
            index=models.Index(fields=["order", "event_key", "recipient_type"], name="order_notif_outbox_lookup_idx"),
        ),
    ]
