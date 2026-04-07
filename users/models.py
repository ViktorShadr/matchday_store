from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Менеджер для управления пользователями с использованием email."""

    def create_user(self, email, password=None, **extra_fields):
        """
        Создать нового пользователя.

        Args:
            email (str): Email пользователя
            password (str): Пароль пользователя (опционально)
            **extra_fields: Дополнительные поля для пользователя

        Returns:
            User: Созданный объект пользователя

        Raises:
            ValueError: Если email не указан
        """
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Создать суперпользователя.

        Args:
            email (str): Email суперпользователя
            password (str): Пароль суперпользователя
            **extra_fields: Дополнительные поля

        Returns:
            User: Созданный объект суперпользователя
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Модель пользователя системы.

    Расширенная модель пользователя Django с использованием email в качестве
    идентификатора вместо username. Включает дополнительные поля для профиля.

    Attributes:
        email (str): Уникальный email пользователя (используется как USERNAME_FIELD)
        first_name (str): Имя пользователя (опционально)
        last_name (str): Фамилия пользователя (опционально)
        phone (str): Номер телефона (опционально)
        city (str): Город проживания (опционально)
        avatar (ImageField): Аватар пользователя (опционально)
        is_active (bool): Флаг активного пользователя
        is_staff (bool): Флаг сотрудника
        is_superuser (bool): Флаг суперпользователя
    """

    username = None
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    avatar = models.ImageField(upload_to="avatars", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        """Возвращает строковое представление объекта."""
        return self.email

    class Meta:
        """Мета-настройки класса."""

        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
