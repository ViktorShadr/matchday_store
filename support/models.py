from django.conf import settings
from django.db import models


class SupportRequest(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новое"
        IN_PROGRESS = "in_progress", "В работе"
        RESOLVED = "resolved", "Решено"
        CLOSED = "closed", "Закрыто"

    name = models.CharField("Имя", max_length=150)
    email = models.EmailField("Email")
    phone = models.CharField("Телефон", max_length=32, blank=True)
    subject = models.CharField("Тема", max_length=160)
    message = models.TextField("Сообщение")
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.NEW)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        related_name="support_requests",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    staff_notes = models.TextField("Внутренние заметки", blank=True)
    email_sent = models.BooleanField("Email отправлен", default=False)
    email_error = models.TextField("Ошибка отправки email", blank=True, null=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Обращение в поддержку"
        verbose_name_plural = "Обращения в поддержку"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} — {self.email}"
