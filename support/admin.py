from django.contrib import admin

from support.models import SupportRequest


@admin.register(SupportRequest)
class SupportRequestAdmin(admin.ModelAdmin):
    list_display = ("created_at", "subject", "name", "email", "phone", "status", "email_sent")
    list_filter = ("status", "email_sent", "created_at")
    search_fields = ("name", "email", "phone", "subject", "message")
    readonly_fields = ("created_at", "updated_at", "email_error")
    list_editable = ("status",)
    fieldsets = (
        (
            "Обращение",
            {
                "fields": (
                    "status",
                    "user",
                    "name",
                    "email",
                    "phone",
                    "subject",
                    "message",
                )
            },
        ),
        ("Работа сотрудников", {"fields": ("staff_notes",)}),
        ("Email", {"fields": ("email_sent", "email_error")}),
        ("Служебные поля", {"fields": ("created_at", "updated_at")}),
    )
