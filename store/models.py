from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse


class Category(models.Model):
    """
    Модель категории товаров.

    Представляет категорию для группировки товаров.

    Attributes:
        name (str): Уникальное название категории
        description (str): Описание категории (необязательно)
        created_at (datetime): Дата создания
        updated_at (datetime): Дата последнего обновления
    """

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        """Возвращает строковое представление объекта."""
        return self.name

    def get_absolute_url(self):
        """Возвращает URL для просмотра объекта."""
        return reverse("store:category_detail", kwargs={"pk": self.pk})

    class Meta:
        """Мета-настройки класса."""

        verbose_name = "Категория"
        verbose_name_plural = "Категории"


class Product(models.Model):
    """
    Модель товара.

    Представляет основной товар в каталоге.

    Attributes:
        name (str): Название товара
        description (str): Описание товара (необязательно)
        category (Category): Связанная категория (необязательно)
        is_on_sale (bool): Доступен ли товар к продаже на витрине
        created_at (datetime): Дата создания
        updated_at (datetime): Дата последнего обновления
    """

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        "Category",
        on_delete=models.CASCADE,
        related_name="products",
        null=True,
        blank=True,
    )
    is_on_sale = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        """Возвращает строковое представление объекта."""
        return self.name

    def get_absolute_url(self):
        """Возвращает URL для просмотра объекта."""
        return reverse("store:product_detail", kwargs={"pk": self.pk})

    class Meta:
        """Мета-настройки класса."""

        verbose_name = "Товар"
        verbose_name_plural = "Товары"


class ProductVariant(models.Model):
    """
    Модель варианта товара.

    Представляет конкретный вариант товара с определённым размером,
    цветом и ценой. Один товар может иметь несколько вариантов.

    Attributes:
        product (Product): Базовый товар
        size (str): Размер варианта
        color (str): Цвет варианта
        price (Decimal): Цена варианта
        quantity (int): Количество на складе
        reserved_quantity (int): Количество, зарезервированное под активные заказы
        image (ProductImage): Основное изображение варианта (необязательно)
        created_at (datetime): Дата создания
        updated_at (datetime): Дата последнего обновления
    """

    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name="variants",
    )
    size = models.CharField(max_length=10, blank=True, null=True)
    color = models.CharField(max_length=50, blank=True, null=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    quantity = models.PositiveIntegerField(default=0)
    reserved_quantity = models.PositiveIntegerField(default=0)
    image = models.ForeignKey(
        "ProductImage",
        on_delete=models.SET_NULL,
        related_name="images",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        """Возвращает строковое представление объекта."""
        return f"{self.product.name} ({self.size}, {self.color})"

    @property
    def available_quantity(self) -> int:
        """Количество, доступное для новых заказов."""
        return max((self.quantity or 0) - (self.reserved_quantity or 0), 0)

    class Meta:
        """Мета-настройки класса."""

        verbose_name = "Вариант товара"
        verbose_name_plural = "Варианты товара"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "size", "color"],
                name="unique_product_variant_size_color",
            ),
            models.CheckConstraint(
                condition=models.Q(reserved_quantity__lte=models.F("quantity")),
                name="product_variant_reserved_lte_quantity",
            ),
            models.CheckConstraint(
                condition=models.Q(price__gt=0),
                name="product_variant_price_gt_zero",
            ),
        ]


class ProductImage(models.Model):
    """
    Модель изображения товара.

    Представляет изображение, связанное с товаром.

    Attributes:
        product (Product): Связанный товар
        image (ImageField): Файл изображения
        alt_text (str): Альтернативный текст для изображения
        is_primary (bool): Флаг основного изображения товара
        created_at (datetime): Дата создания
    """

    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="product_images/")
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """Возвращает строковое представление объекта."""
        return f"Изображение для {self.product.name}"

    class Meta:
        """Мета-настройки класса."""

        verbose_name = "Изображение товара"
        verbose_name_plural = "Изображения товаров"


class Page(models.Model):
    """
    Контентная страница сайта.

    Используется для юридических и информационных страниц,
    управляемых через админку.
    """

    slug = models.SlugField(max_length=150, unique=True)
    title = models.CharField(max_length=255)
    lead = models.TextField(blank=True)
    content = models.TextField()
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_store_pages",
    )

    class Meta:
        verbose_name = "Страница"
        verbose_name_plural = "Страницы"
        ordering = ["slug"]

    def __str__(self):
        return self.title


class InfoCard(models.Model):
    """
    Информационная карточка для блоков витрины.
    """

    title = models.CharField(max_length=255)
    text = models.TextField()
    icon = models.CharField(max_length=100, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Инфо-карточка"
        verbose_name_plural = "Инфо-карточки"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.title


class Cart(models.Model):
    """
    Модель корзины.

    Представляет корзину пользователя для хранения выбранных товаров.
    Может быть привязана к пользователю или к сессии.

    Attributes:
        user (User): Владелец корзины (необязательно)
        session_key (str): Ключ сессии для анонимных пользователей (необязательно)
        created_at (datetime): Дата создания
        updated_at (datetime): Дата последнего обновления
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart", null=True, blank=True
    )
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        """Возвращает строковое представление объекта."""
        if self.user:
            return f"Корзина пользователя {self.user.email}"
        else:
            return f"Корзина сессии {self.session_key[:8]}..."

    @property
    def total_price(self):
        """Общая стоимость всех товаров в корзине"""
        return sum(item.total_price for item in self.items.all())

    @property
    def total_items(self):
        """Общее количество товаров в корзине"""
        return sum(item.quantity for item in self.items.all())

    class Meta:
        """Мета-настройки класса."""

        verbose_name = "Корзина"
        verbose_name_plural = "Корзины"
        constraints = [
            models.UniqueConstraint(fields=["user"], condition=models.Q(user__isnull=False), name="unique_user_cart"),
            models.UniqueConstraint(
                fields=["session_key"], condition=models.Q(user__isnull=True), name="unique_session_cart"
            ),
        ]


class CartItem(models.Model):
    """
    Модель элемента корзины.

    Представляет товар в корзине с указанием количества.

    Attributes:
        cart (Cart): Корзина, в которой находится элемент
        product_variant (ProductVariant): Вариант товара
        quantity (int): Количество товара
        created_at (datetime): Дата добавления в корзину
        updated_at (datetime): Дата последнего обновления
    """

    cart = models.ForeignKey("Cart", on_delete=models.CASCADE, related_name="items")
    product_variant = models.ForeignKey("ProductVariant", on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        """Возвращает строковое представление объекта."""
        variant = self.product_variant
        return f"{variant.product.name} ({variant.size}, {variant.color}) - {self.quantity} шт."

    class Meta:
        """Мета-настройки класса."""

        verbose_name = "Элемент корзины"
        verbose_name_plural = "Элементы корзины"
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product_variant"],
                name="unique_cart_product_variant",
            ),
        ]

    @property
    def total_price(self):
        """Общая стоимость элемента корзины"""
        return self.product_variant.price * self.quantity
