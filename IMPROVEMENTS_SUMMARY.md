# Улучшения логики добавления товара в корзину ✅

## Что было исправлено

### 1. ✅ CSRF Protection (КРИТИЧНО - ИСПРАВЛЕНО)

**Было:**
```python
@method_decorator(csrf_exempt, name='dispatch')
class AddToCartView(View):  # ОПАСНО!
```

**Стало:**
```python
@require_http_methods(["POST"])
class AddToCartView(View):  # CSRF token обязателен
```

**Как это работает:**
- CSRF token теперь требуется в заголовке `X-CSRFToken` или в теле запроса
- JavaScript автоматически отправляет token из `csrfmiddlewaretoken` или cookie
- Защита от CSRF атак включена по умолчанию

---

### 2. ✅ Race Conditions (КРИТИЧНО - ИСПРАВЛЕНО)

**Было:**
```python
if product_variant.quantity < quantity:  # Проверка
    raise ValueError(...)
# RACE CONDITION: товар может закончиться здесь!
cart_item, created = CartItem.objects.get_or_create(...)
```

**Стало:**
```python
@transaction.atomic
def add_item(request, product_variant_id, quantity=1):
    # Блокируем вариант товара на время операции
    product_variant = ProductVariant.objects.select_for_update().get(id=product_variant_id)
    
    if product_variant.quantity < quantity:
        raise InsufficientStockError(...)
    
    # Остальная операция выполняется в транзакции
    cart_item, created = CartItem.objects.get_or_create(...)
```

**Как это работает:**
- `@transaction.atomic` оборачивает всю операцию в БД транзакцию
- `select_for_update()` блокирует строку в БД на время операции
- Другие процессы ждут завершения операции перед доступом
- Гарантирует, что товар не переселится во время добавления в корзину

---

### 3. ✅ Input Validation (ИСПРАВЛЕНО)

**Было:**
```python
quantity = int(request.POST.get('quantity', 1))  # May raise ValueError!
```

**Стало:**
```python
# Отдельный валидатор с явной обработкой ошибок
class CartValidator:
    @staticmethod
    def validate_quantity(quantity_str) -> int:
        try:
            quantity = int(quantity_str) if quantity_str else 1
            if quantity < 1 or quantity > 999:
                raise ValueError()
            return quantity
        except (ValueError, TypeError):
            raise InvalidQuantityError("Количество должно быть числом от 1 до 999")

# В view:
variant_id, quantity = CartValidator.validate_add_to_cart_input(variant_id, quantity_str)
```

**Как это работает:**
- Валидация в отдельном классе
- Явная обработка исключений
- Возвращает 400 Bad Request вместо 500 Server Error
- Валидация происходит ДО обращения к БД

---

### 4. ✅ Специфичные исключения (НОВОЕ)

**Было:**
```python
raise ValueError("Какая-то ошибка")  # Общее исключение
```

**Стало:**
```python
# Специализированные исключения с HTTP статусами
class InsufficientStockError(CartException):
    http_status = 400  # 400 Bad Request
    
class ProductVariantNotFoundError(CartException):
    http_status = 404  # 404 Not Found
    
class CartOperationError(CartException):
    http_status = 500  # 500 Server Error

# В view:
try:
    cart_item = CartService.add_item(request, variant_id, quantity)
except InsufficientStockError as e:
    return build_error_response(e)  # JSON с правильным HTTP кодом
```

**Как это работает:**
- Каждое исключение имеет правильный HTTP статус
- JavaScript может по кодам различить типы ошибок
- Поведение предсказуемо: всегда возвращается JSON

---

### 5. ✅ Логирование (НОВОЕ)

**Было:**
```python
# Логирование отсутствовало
```

**Стало:**
```python
logger = logging.getLogger(__name__)

def add_item(request, product_variant_id, quantity=1):
    logger.info(
        f"User {request.user.id} adding variant {product_variant_id} qty {quantity}"
    )
    try:
        # ...операция...
        logger.info(f"New cart item created: {cart_item.id}, qty={quantity}")
    except InsufficientStockError as e:
        logger.warning(f"Insufficient stock: {e}")
        raise
    except Exception as e:
        logger.error(f"Error adding item to cart: {e}", exc_info=True)
        raise
```

**Логируются:**
- ✅ Добавление товара (уровень INFO)
- ✅ Недостаточно товара (уровень WARNING)
- ✅ Ошибки операции (уровень ERROR)
- ✅ Stack trace для отладки

---

### 6. ✅ Производительность (ИСПРАВЛЕНО)

**Было:**
```python
# Вызов get_or_create_cart три раза подряд!
'cart_total': CartService.get_or_create_cart(request).total_price,
'cart_items': CartService.get_or_create_cart(request).total_items
```

**Стало:**
```python
# Кэшируем результат в одной переменной
cart = CartService.get_or_create_cart(request)

return JsonResponse({
    'success': True,
    'message': '...',
    'item_total': float(cart_item.total_price),
    'cart_total': float(cart.total_price),
    'cart_items': cart.total_items
})
```

**Результат:**
- Одно обращение к БД вместо трёх
- Быстрее и экономнее

---

### 7. ✅ Проверка методов HTTP (НОВОЕ)

**Было:**
```python
class AddToCartView(View):
    def post(self, request):  # Работает ANY POST
```

**Стало:**
```python
@require_http_methods(["POST"])
class AddToCartView(View):
    def post(self, request):  # ТОЛЬКО POST
```

**Как это работает:**
- GET, HEAD, PUT, DELETE и другие методы вернут 405 Method Not Allowed
- Защита от случайных запросов
- Явное заявление о требованиях к API

---

### 8. ✅ Правильная обработка исключений в транзакциях (ИСПРАВЛЕНО)

**Было:**
```python
# Слияние корзин без транзакции
for item in session_cart.items.all():
    cart_item, created = CartItem.objects.get_or_create(...)  # May fail!
session_cart.delete()  # Может не выполниться
```

**Стало:**
```python
@transaction.atomic
def _merge_session_cart_with_user_cart(user_cart, session_key):
    try:
        # Все операции в одной транзакции
        for item in session_cart.items.all():
            cart_item, created = CartItem.objects.get_or_create(...)
        session_cart.delete()
        logger.info(f"Session cart merged")
    except Exception as e:
        logger.error(f"Error merging carts: {e}", exc_info=True)
        raise  # Транзакция откатится
```

**Гарантирует:**
- Либо ВСЕ товары перенесены и корзина удалена
- Либо НИЧЕГО не изменилось (откат)
- Нет неполных операций

---

### 9. ✅ Возвращаемые типы (ИСПРАВЛЕНО)

**Было:**
```python
'item_total': cart_item.total_price,  # Decimal - может быть проблема с JSON
'cart_total': cart.total_price,        # Decimal
```

**Стало:**
```python
'item_total': float(cart_item.total_price),  # float - корректно сериализуется
'cart_total': float(cart.total_price),
```

**Результат:**
- JSON всегда корректно сериализуется
- Нет ошибок при отправке ответа
- JavaScript получает числа, а не строки

---

## Тестирование Best Practices

### ✅ Основные сценарии:

1. **Добавление товара в корзину**
   ```javascript
   // Должно пройти:
   POST /cart/add/ {variant_id: 1, quantity: 2, csrftoken: "..."}
   // Должно вернуть: {"success": true, "message": "...", "cart_total": 2}
   ```

2. **Недостаточно товара на складе**
   ```javascript
   // Если товара 5, а запрошено 10:
   POST /cart/add/ {variant_id: 1, quantity: 10, csrftoken: "..."}
   // Должно вернуть: 400 {"success": false, "error": "Недостаточно..."}
   ```

3. **Некорректный ID**
   ```javascript
   // Если товара нет:
   POST /cart/add/ {variant_id: 99999, quantity: 1, csrftoken: "..."}
   // Должно вернуть: 404 {"success": false, "error": "...не найден"}
   ```

4. **Race condition (одновременные запросы)**
   ```javascript
   // Два одновременных запроса на добавление товара:
   POST /cart/add/ {variant_id: 1, quantity: 8, csrftoken: "..."}
   POST /cart/add/ {variant_id: 1, quantity: 8, csrftoken: "..."}
   // Первый успешен, второй вернёт 400 (недостаточно)
   ```

---

## Структура файлов

```
store/services/
├── cart_exceptions.py      # ← НОВОЕ: Исключения для корзины
├── cart_validator.py       # ← НОВОЕ: Валидаторы для корзины
├── cart_service.py         # ← ОБНОВЛЕНО: С @transaction.atomic и логированием
├── template_filters.py     # Сервисы для шаблонов
└── __init__.py            # ← ОБНОВЛЕНО: Экспортирует новые классы
```

---

## Миграция с старого кода

Если вы уже используете старый код, нужно обновить вызовы:

```python
# Старый код:
from store.services.cart_service import CartService
cart_item = CartService.add_item(request, variant_id, quantity)

# Может выбросить ValueError("Недостаточно...")
# Нужна обработка ошибок

# Новый код:
from store.services import CartService, CartValidator, InsufficientStockError

try:
    variant_id, quantity = CartValidator.validate_add_to_cart_input(
        request.POST.get('variant_id'),
        request.POST.get('quantity', '1')
    )
    cart_item = CartService.add_item(request, variant_id, quantity)
except InsufficientStockError as e:
    # Обработка ошибки
    logger.warning(f"Stock error: {e}")
```

---

## Summary

| Проблема | Статус | Решение |
|----------|--------|---------|
| CSRF Protection | ✅ ИСПРАВЛЕНО | Удалён @csrf_exempt, добавлена @require_http_methods |
| Race Conditions | ✅ ИСПРАВЛЕНО | @transaction.atomic + select_for_update() |
| Input Validation | ✅ ИСПРАВЛЕНО | CartValidator с явной обработкой исключений |
| Error Handling | ✅ ИСПРАВЛЕНО | Специфичные исключения с HTTP статусами |
| Logging | ✅ ДОБАВЛЕНО | INFO/WARNING/ERROR для всех операций |
| Performance | ✅ ИСПРАВЛЕНО | Кэширование результатов get_or_create_cart |
| API Response | ✅ ИСПРАВЛЕНО | JSON для всех ошибок, float для чисел |
| Atomicity | ✅ ИСПРАВЛЕНО | @transaction.atomic на все операции |
