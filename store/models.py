from django.core.validators import MinValueValidator
from django.db import models


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
        return self.name

    class Meta:
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
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
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
        image (ProductImage): Основное изображение варианта
        created_at (datetime): Дата создания
        updated_at (datetime): Дата последнего обновления
    """
    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name="variants",
    )
    size = models.CharField(max_length=10)
    color = models.CharField(max_length=50)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    quantity = models.PositiveIntegerField(default=0)
    image = models.ForeignKey(
        "ProductImage",
        on_delete=models.CASCADE,
        related_name="images",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product.name} ({self.size}, {self.color})"

    class Meta:
        verbose_name = "Вариант товара"
        verbose_name_plural = "Варианты товара"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "size", "color"],
                name="unique_product_variant_size_color",
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
        return f"Изображение для {self.product.name}"

    class Meta:
        verbose_name = "Изображение товара"
        verbose_name_plural = "Изображения товаров"
