# Примеры тестирования логики корзины

## Unit Tests для CartValidator

```python
from django.test import TestCase
from store.services.cart_validator import CartValidator
from store.services.cart_exceptions import InvalidQuantityError, ProductVariantNotFoundError


class CartValidatorTestCase(TestCase):
    """Тесты для валидатора входных данных корзины"""
    
    def test_validate_quantity_valid(self):
        """Проверка валидного количества"""
        assert CartValidator.validate_quantity('5') == 5
        assert CartValidator.validate_quantity('1') == 1
        assert CartValidator.validate_quantity('999') == 999
    
    def test_validate_quantity_default(self):
        """Проверка значения по умолчанию"""
        assert CartValidator.validate_quantity('') == 1
        assert CartValidator.validate_quantity(None) == 1
    
    def test_validate_quantity_invalid_format(self):
        """Проверка некорректного формата"""
        with self.assertRaises(InvalidQuantityError):
            CartValidator.validate_quantity('abc')
        
        with self.assertRaises(InvalidQuantityError):
            CartValidator.validate_quantity('5.5')
        
        with self.assertRaises(InvalidQuantityError):
            CartValidator.validate_quantity('-5')
    
    def test_validate_quantity_out_of_range(self):
        """Проверка значений вне допустимого диапазона"""
        with self.assertRaises(InvalidQuantityError):
            CartValidator.validate_quantity('0')
        
        with self.assertRaises(InvalidQuantityError):
            CartValidator.validate_quantity('1000')
    
    def test_validate_variant_id_valid(self):
        """Проверка валидного ID варианта"""
        assert CartValidator.validate_variant_id('1') == 1
        assert CartValidator.validate_variant_id(1) == 1
    
    def test_validate_variant_id_invalid(self):
        """Проверка некорректного ID варианта"""
        with self.assertRaises(ProductVariantNotFoundError):
            CartValidator.validate_variant_id('')
        
        with self.assertRaises(ProductVariantNotFoundError):
            CartValidator.validate_variant_id(None)
        
        with self.assertRaises(ProductVariantNotFoundError):
            CartValidator.validate_variant_id('abc')
        
        with self.assertRaises(ProductVariantNotFoundError):
            CartValidator.validate_variant_id('-1')
```

## Integration Tests для CartService

```python
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from store.models import Category, Product, ProductVariant, ProductImage, Cart
from store.services.cart_service import CartService
from store.services.cart_exceptions import InsufficientStockError, ProductVariantNotFoundError

User = get_user_model()


class CartServiceTestCase(TestCase):
    """Тесты для сервиса работы с корзиной"""
    
    def setUp(self):
        """Подготовка данных для тестов"""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(email='test@test.com', password='pass')
        
        # Создаём категорию
        self.category = Category.objects.create(name='Test Category')
        
        # Создаём товар
        self.product = Product.objects.create(
            name='Test Product',
            category=self.category
        )
        
        # Создаём изображение
        self.image = ProductImage.objects.create(
            product=self.product,
            image='test.jpg',
            is_primary=True
        )
        
        # Создаём вариант товара
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size='M',
            color='Red',
            price=100,
            quantity=10,
            image=self.image
        )
    
    def test_add_item_to_cart_authenticated_user(self):
        """Добавление товара в корзину авторизованного пользователя"""
        request = self.factory.post('/')
        request.user = self.user
        request.session = {}  # Mock сессия
        
        cart_item = CartService.add_item(request, self.variant.id, quantity=2)
        
        assert cart_item.quantity == 2
        assert cart_item.product_variant == self.variant
        assert cart_item.cart.user == self.user
    
    def test_add_item_increments_quantity(self):
        """Добавление товара, который уже в корзине"""
        request = self.factory.post('/')
        request.user = self.user
        request.session = {}
        
        # Добавляем товар первый раз
        CartService.add_item(request, self.variant.id, quantity=2)
        
        # Добавляем ещё раз
        cart_item = CartService.add_item(request, self.variant.id, quantity=3)
        
        assert cart_item.quantity == 5  # 2 + 3
    
    def test_add_item_insufficient_stock(self):
        """Попытка добавить товара больше, чем в наличии"""
        request = self.factory.post('/')
        request.user = self.user
        request.session = {}
        
        with self.assertRaises(InsufficientStockError) as context:
            CartService.add_item(request, self.variant.id, quantity=20)
        
        assert 'Недостаточно товара' in str(context.exception)
    
    def test_add_item_variant_not_found(self):
        """Попытка добавить несуществующий вариант"""
        request = self.factory.post('/')
        request.user = self.user
        request.session = {}
        
        with self.assertRaises(ProductVariantNotFoundError):
            CartService.add_item(request, 99999, quantity=1)
    
    def test_update_item_quantity(self):
        """Обновление количества товара в корзине"""
        request = self.factory.post('/')
        request.user = self.user
        request.session = {}
        
        # Добавляем товар
        CartService.add_item(request, self.variant.id, quantity=2)
        
        # Обновляем количество
        cart_item = CartService.update_item_quantity(request, self.variant.id, quantity=5)
        
        assert cart_item.quantity == 5
    
    def test_update_item_insufficient_stock(self):
        """Обновление на количество больше, чем в наличии"""
        request = self.factory.post('/')
        request.user = self.user
        request.session = {}
        
        CartService.add_item(request, self.variant.id, quantity=1)
        
        with self.assertRaises(InsufficientStockError):
            CartService.update_item_quantity(request, self.variant.id, quantity=20)
    
    def test_remove_item(self):
        """Удаление товара из корзины"""
        request = self.factory.post('/')
        request.user = self.user
        request.session = {}
        
        # Добавляем товар
        CartService.add_item(request, self.variant.id, quantity=2)
        
        # Удаляем
        success = CartService.remove_item(request, self.variant.id)
        
        assert success is True
        
        # Проверяем, что товара нет в корзине
        cart = CartService.get_or_create_cart(request)
        assert cart.items.count() == 0
    
    def test_remove_nonexistent_item(self):
        """Попытка удалить товара, которого нет в корзине"""
        request = self.factory.post('/')
        request.user = self.user
        request.session = {}
        
        success = CartService.remove_item(request, self.variant.id)
        
        assert success is False
    
    def test_clear_cart(self):
        """Очистка корзины"""
        request = self.factory.post('/')
        request.user = self.user
        request.session = {}
        
        # Добавляем несколько товаров
        CartService.add_item(request, self.variant.id, quantity=2)
        
        # Очищаем корзину
        cart = CartService.clear_cart(request)
        
        assert cart.items.count() == 0
    
    def test_get_cart_summary(self):
        """Получение сводки по корзине"""
        request = self.factory.post('/')
        request.user = self.user
        request.session = {}
        
        CartService.add_item(request, self.variant.id, quantity=2)
        
        summary = CartService.get_cart_summary(request)
        
        assert summary['total_items'] == 2
        assert summary['total_price'] == 200  # 100 * 2
        assert summary['items'].count() == 1
```

## View Tests для AddToCartView

```python
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from store.models import Category, Product, ProductVariant, ProductImage

User = get_user_model()


class AddToCartViewTestCase(TestCase):
    """Тесты для view добавления товара в корзину"""
    
    def setUp(self):
        """Подготовка данных"""
        self.client = Client(enforce_csrf_checks=False)  # Для простоты в тестах
        self.user = User.objects.create_user(email='test@test.com', password='pass')
        
        self.category = Category.objects.create(name='Test Category')
        self.product = Product.objects.create(name='Test Product', category=self.category)
        
        self.image = ProductImage.objects.create(
            product=self.product,
            image='test.jpg',
            is_primary=True
        )
        
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size='M',
            color='Red',
            price=100,
            quantity=10,
            image=self.image
        )
        
        self.url = reverse('main_page:add_to_cart')
    
    def test_add_to_cart_success(self):
        """Успешное добавление товара"""
        response = self.client.post(self.url, {
            'variant_id': self.variant.id,
            'quantity': 2
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'добавлен в корзину' in data['message']
        assert data['cart_total'] == 2
    
    def test_add_to_cart_insufficient_stock(self):
        """Добавление товара при недостаточном остатке"""
        response = self.client.post(self.url, {
            'variant_id': self.variant.id,
            'quantity': 20
        })
        
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Недостаточно товара' in data['error']
    
    def test_add_to_cart_missing_variant_id(self):
        """Добавление без указания ID варианта"""
        response = self.client.post(self.url, {
            'quantity': 2
        })
        
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
    
    def test_add_to_cart_invalid_quantity(self):
        """Добавление с некорректным количеством"""
        response = self.client.post(self.url, {
            'variant_id': self.variant.id,
            'quantity': 'abc'
        })
        
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_add_to_cart_zero_quantity(self):
        """Добавление с нулевым количеством"""
        response = self.client.post(self.url, {
            'variant_id': self.variant.id,
            'quantity': 0
        })
        
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_add_to_cart_nonexistent_variant(self):
        """Добавление несуществующего варианта"""
        response = self.client.post(self.url, {
            'variant_id': 99999,
            'quantity': 1
        })
        
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
```

## Performance Test для Race Conditions

```python
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from concurrent.futures import ThreadPoolExecutor
import threading
from store.models import Category, Product, ProductVariant, ProductImage, CartItem
from store.services.cart_service import CartService
from store.services.cart_exceptions import InsufficientStockError

User = get_user_model()


class CartRaceConditionTestCase(TestCase):
    """Тесты на race conditions в корзине"""
    
    def setUp(self):
        """Подготовка данных"""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(email='test@test.com', password='pass')
        
        self.category = Category.objects.create(name='Test Category')
        self.product = Product.objects.create(name='Test Product', category=self.category)
        
        self.image = ProductImage.objects.create(
            product=self.product,
            image='test.jpg',
            is_primary=True
        )
        
        # Вариант товара с ограниченным количеством
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size='M',
            color='Red',
            price=100,
            quantity=5,  # Только 5 шт
            image=self.image
        )
    
    def test_concurrent_add_items_no_overselling(self):
        """
        Проверка, что при одновременных добавлениях не происходит
        переселения товара (overselling).
        
        Сценарий: 2 пользователя пытаются одновременно добавить по 3 шт товара
        Ожидаемый результат: первый успешен, второй получает ошибку
        """
        results = {'success': 0, 'failed': 0}
        lock = threading.Lock()
        
        def try_add_item(user_num):
            request = self.factory.post('/')
            request.user = self.user
            request.session = {}
            
            try:
                CartService.add_item(request, self.variant.id, quantity=3)
                with lock:
                    results['success'] += 1
            except InsufficientStockError:
                with lock:
                    results['failed'] += 1
        
        # Запускаем 2 потока одновременно
        with ThreadPoolExecutor(max_workers=2) as executor:
            executor.submit(try_add_item, 1)
            executor.submit(try_add_item, 2)
        
        # Один успешен, один нет
        assert results['success'] == 1 or results['failed'] == 1
        
        # Проверяем, что товара не больше чем было
        cart = CartService.get_or_create_cart(
            self.factory.post('/')
        )
        cart.user = self.user
        total_in_cart = sum(item.quantity for item in cart.items.all())
        assert total_in_cart <= 5  # Не переселили товар
```
