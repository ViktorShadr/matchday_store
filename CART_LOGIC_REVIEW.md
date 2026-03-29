# Анализ логики добавления товара в корзину

## Найденные проблемы 🔴

### 1. **CSRF Protection - КРИТИЧНО**
- ❌ Использование `@csrf_exempt` на всех view'ах
- ⚠️ AJAX запросы отправляют CSRF token в заголовках, но это игнорируется
- **Риск**: Злоумышленник может добавить товар в корзину пользователя через cross-site request

```python
# Текущий код (ОПАСНО):
@method_decorator(csrf_exempt, name='dispatch')
class AddToCartView(View):
```

### 2. **Race Conditions - КРИТИЧНО**
- ❌ Нет атомарных операций при проверке и обновлении количества
- **Сценарий**: Два одновременных запроса могут добавить товар, превышающий наличие на складе
- **Решение**: Использовать `@transaction.atomic()` и блокировки БД (`select_for_update()`)

```python
# Текущий код (ПРОБЛЕМНО):
if product_variant.quantity < quantity:  # Проверка
    raise ValueError(...)
# ЗДЕСЬ может произойти изменение quantity в другом процессе!
cart_item, created = CartItem.objects.get_or_create(...)  # Создание
```

### 3. **Некорректная валидация в view**
- ⚠️ Проверка `variant.quantity < quantity` происходит в view
- ⚠️ Повторная проверка в service слое (дублирование)
- ⚠️ Между проверкой и добавлением товар может закончиться на складе

### 4. **Проблема с int() преобразованием**
- ❌ `int(request.POST.get('quantity', 1))` может выбросить исключение если quantity не число
- ⚠️ Исключение не обрабатывается, что приводит к 500 ошибке вместо 400

```python
# Текущий код (ПРОБЛЕМНО):
quantity = int(request.POST.get('quantity', 1))  # ValueError if not int
```

### 5. **Отсутствие логирования**
- ❌ Нет логирования критических операций (добавление, удаление товара)
- ⚠️ Сложно отследить проблемы в production

### 6. **Проблема производительности**
- ❌ `CartService.get_or_create_cart(request)` вызывается несколько раз за запрос
- ⚠️ В UpdateCartView вызывается 3 раза подряд (lines 69-70)
- **Решение**: Кэшировать результат

```python
# Текущий код (НЕЭФФЕКТИВНО):
'cart_total': CartService.get_or_create_cart(request).total_price,  # Запрос 1
'cart_items': CartService.get_or_create_cart(request).total_items   # Запрос 2
```

### 7. **Проблема при слиянии корзин**
- ⚠️ `get_or_create_cart()` выполняет слияние корзин внутри себя
- ⚠️ Логика слияния вызывается даже при простом получении корзины
- ⚠️ Нет проверки на race conditions при слиянии

### 8. **Отсутствие проверки прав доступа**
- ⚠️ Любой может добавлять товар (даже неавторизованные пользователи)
- ✅ Это нормально для ЧИТАЕМЫХ операций, но идеально иметь возможность контроля

### 9. **Неправильный обработчик исключений в get_object_or_404**
- ❌ `get_object_or_404` выбросит 404 если товара нет
- ⚠️ Для AJAX это непредсказуемое поведение (возвращает HTML вместо JSON)

```python
# Текущий код (ПРОБЛЕМНО):
variant = get_object_or_404(ProductVariant, id=variant_id)  # Возвращает 404 HTML
```

### 10. **Отсутствие транзакций в create_or_create для get_or_create_cart**
- ⚠️ Слияние корзин (строки 25-35) не обёрнуто в транзакцию
- ⚠️ Может быть неполное слияние при ошибке

---

## Рекомендации Best Practices ✅

| Практика | Статус | Решение |
|----------|--------|---------|
| CSRF Protection | ❌ | Удалить `@csrf_exempt`, использовать CSRF token |
| Database Transactions | ❌ | Добавить `@transaction.atomic()` |
| Concurrency Control | ❌ | Использовать `select_for_update()` для блокировки |
| Input Validation | ⚠️ | Валидировать в отдельной функции, обработать исключения |
| Logging | ❌ | Добавить логирование всех операций |
| Performance | ⚠️ | Кэшировать результаты, избежать множественных вызовов БД |
| Error Handling | ⚠️ | Специфичные коды ошибок для разных случаев |
| API Response | ❌ | Возвращать JSON для всех ошибок в AJAX |

---

## Примеры правильной реализации

### ✅ Правильная проверка input
```python
def validate_quantity(quantity_str):
    try:
        quantity = int(quantity_str)
        if quantity < 1:
            raise ValueError("Количество должно быть больше 0")
        return quantity
    except (ValueError, TypeError):
        raise ValueError("Количество должно быть целым числом")
```

### ✅ Правильное добавление товара с транзакцией
```python
@transaction.atomic
def add_item_safe(request, product_variant_id, quantity=1):
    # Блокируем вариант товара для исключения race conditions
    variant = ProductVariant.objects.select_for_update().get(id=product_variant_id)
    
    if variant.quantity < quantity:
        raise InsufficientStockError(f"Доступно: {variant.quantity}")
    
    cart = CartService.get_or_create_cart(request)
    
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product_variant=variant,
        defaults={'quantity': quantity}
    )
    
    if not created:
        new_quantity = cart_item.quantity + quantity
        if variant.quantity < new_quantity:
            raise InsufficientStockError(f"Доступно: {variant.quantity}")
        cart_item.quantity = new_quantity
        cart_item.save()
    
    return cart_item
```

### ✅ Правильная CSRF защита
```python
from django.views.decorators.http import require_http_methods
from django.middleware.csrf import ensure_csrf_cookie

@require_http_methods(["POST"])
def add_to_cart(request):
    # Убедитесь, что CSRF token отправляется в заголовке
    # Content-Type: application/x-www-form-urlencoded
    # X-CSRFToken: <token>
    ...
```

### ✅ Логирование
```python
import logging

logger = logging.getLogger(__name__)

def add_item(request, product_variant_id, quantity=1):
    logger.info(f"User {request.user.id} adding variant {product_variant_id} qty {quantity}")
    try:
        cart_item = CartService.add_item(request, product_variant_id, quantity)
        logger.info(f"Success: cart_item {cart_item.id} created/updated")
        return cart_item
    except InsufficientStockError as e:
        logger.warning(f"Insufficient stock: {e}")
        raise
```
