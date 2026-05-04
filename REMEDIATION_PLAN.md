# План устранения недостатков Matchday Store

**Дата создания:** 2026-05-04  
**Приоритет:** Критичные → Средние → Низкие

---

## Сводка по категориям

| Категория | Критичные | Средние | Низкие | Всего |
|-----------|-----------|---------|--------|-------|
| Бизнес-логика | 3 | 5 | 1 | 9 |
| Безопасность | 1 | 4 | 2 | 7 |
| Деплой | 2 | 4 | 2 | 8 |
| **Итого** | **6** | **13** | **5** | **24** |

---

## Этап 1: Критичные баги бизнес-логики

### 1.1 Рассинхронизация статуса заказа при обновлении платежа

**Файл:** `orders/services.py` (строки 734-740)  
**Проблема:** Статус `order.payment_status` не обновляется при изменении статуса платежа.

**Исправление:**
```python
# После строки 732 добавить:
order.payment_status = next_payment_status
if next_payment_status == Order.PaymentStatus.SUCCEEDED:
    if order.paid_at is None:
        order.paid_at = payment.paid_at or now
    if order.status == Order.Status.PLACED:
        order.status = Order.Status.PAID
    order.save(update_fields=["payment_status", "paid_at", "status", "updated_at"])
elif next_payment_status in self.RESET_PAID_AT_STATUSES and order.paid_at is not None:
    order.paid_at = None
    order.payment_status = next_payment_status
    order.save(update_fields=["payment_status", "paid_at", "updated_at"])
else:
    order.payment_status = next_payment_status
    order.save(update_fields=["payment_status", "updated_at"])
```

**Проверка:**
1. Создать заказ
2. Добавить платеж со статусом SUCCEEDED
3. Проверить, что `order.payment_status` = SUCCEEDED и `order.status` = PAID

---

### 1.2 Проверка email только в dispatch()

**Файл:** `orders/views.py` (строки 101-130)  
**Проблема:** Проверка `is_email_confirmed` только в `dispatch()`, но не в `form_valid()`.

**Исправление:**
```python
def form_valid(self, form):
    """Создать заказ из корзины."""
    # Повторная проверка email перед созданием заказа
    if not self.request.user.is_email_confirmed:
        messages.error(self.request, "Подтвердите email в личном кабинете перед оформлением заказа.")
        return redirect(reverse("users:profile_detail", kwargs={"pk": self.request.user.pk}))
    
    session_token = self.checkout_session_service.get_or_create_checkout_token(self.request)
    # ... остальной код
```

---

## Этап 2: Критичные уязвимости безопасности

### 2.1 Ограничение размера загружаемых файлов

**Файл:** `store/forms.py` (строки 57-65)  
**Проблема:** Отсутствует ограничение размера файла и проверка MIME-type.

**Исправление:**
```python
class ProductImageForm(forms.ModelForm):
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
    
    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "is_primary"]
        widgets = {
            "image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "alt_text": forms.TextInput(attrs={"class": "form-control", "placeholder": "Краткое описание изображения"}),
            "is_primary": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
    
    def clean_image(self):
        image = self.cleaned_data.get('image')
        if not image:
            return image
            
        # Проверка размера
        if image.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError(f"Размер файла не должен превышать {self.MAX_FILE_SIZE // (1024*1024)}MB")
        
        # Проверка MIME-type
        if hasattr(image, 'content_type') and image.content_type not in self.ALLOWED_TYPES:
            raise forms.ValidationError(f"Допустимые форматы: JPEG, PNG, WebP, GIF")
        
        return image
```

---

## Этап 3: Критичные проблемы деплоя

### 3.1 Усиление настроек nginx

**Файл:** `docker/nginx/default.conf`  
**Проблема:** Отсутствуют защита от slowloris, rate limiting, gzip.

**Исправление:**
```nginx
map $http_x_forwarded_proto $proxy_x_forwarded_proto {
    default $scheme;
    https https;
}

# Rate limiting zone
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

server {
    listen 80;
    server_name _;

    # Защита от медленных атак
    client_body_timeout 12s;
    client_header_timeout 12s;
    send_timeout 10s;
    
    # Ограничения размера
    client_max_body_size 10m;
    client_header_buffer_size 4k;
    large_client_header_buffers 4 8k;

    resolver 127.0.0.11 valid=30s ipv6=off;
    resolver_timeout 5s;
    set $web_upstream web:8000;

    # Gzip сжатие
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;

    location /static/ {
        alias /var/www/static/;
        access_log off;
        expires 7d;
        add_header Cache-Control "public";
    }

    location /media/ {
        alias /var/www/media/;
        access_log off;
        expires 1d;
        add_header Cache-Control "public";
    }

    # Rate limiting для API endpoints
    location /orders/checkout {
        limit_req zone=login burst=3 nodelay;
        proxy_pass http://$web_upstream;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $proxy_x_forwarded_proto;
        proxy_redirect off;
    }

    location / {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://$web_upstream;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $proxy_x_forwarded_proto;
        proxy_redirect off;
    }
}
```

---

### 3.2 Добавить user для web сервиса

**Файл:** `docker-compose.yaml` (сервис web)  
**Проблема:** Сервис web работает без явного указания пользователя.

**Исправление:**
```yaml
web:
  build: .
  user: "10001:10001"  # <-- добавить эту строку
  entrypoint: /app/docker/web-entrypoint.sh
  command: >
    gunicorn config.asgi:application
    ...
```

---

## Этап 4: Средние приоритеты (бизнес-логика)

### 4.1 Race condition в merge корзин

**Файл:** `store/application/cart_context.py` (строки 77-113)  
**Проблема:** Отсутствует `select_for_update()` при мерже корзин.

**Исправление:**
```python
@transaction.atomic
def merge_session_cart_into_user_cart(self, user_cart: Cart, session_key: str) -> None:
    try:
        session_cart = self.cart_repository.get_cart_by_session_key(session_key)
        if not session_cart:
            return
        
        # Добавить select_for_update для предотвращения race conditions
        items = list(
            session_cart.items
            .select_related("product_variant")
            .select_for_update(nowait=False)
            .all()
        )
        
        for item in items:
            # ... остальной код
```

---

### 4.2 Инвалидация токена при ошибке checkout

**Файл:** `orders/views.py` (строки 120-127)  
**Проблема:** Токен не инвалидируется при `CheckoutError`.

**Исправление:**
```python
except CheckoutError as exc:
    # Инвалидируем токен при ошибке
    self.request.session.pop("_checkout_token", None)
    self.request.session.modified = True
    
    # Корзина могла измениться в checkout-сервисе
    self.cart_summary = cart_service.get_cart_summary(self.cart_context)
    if not self.cart_summary["items"]:
        messages.warning(self.request, str(exc))
        return redirect("store:cart")
    form.add_error(None, str(exc))
    return self.form_invalid(form)
```

---

### 4.3 Валидация цены при создании заказа

**Файл:** `orders/services.py` (строки 313-316)  
**Проблема:** Нет проверки на отрицательную или нулевую цену.

**Исправление:**
```python
if variant.price <= 0:
    raise CheckoutError(
        f'Некорректная цена для товара "{variant.product.name}". '
        f"Обратитесь в поддержку."
    )
```

---

### 4.4 Авто-отмена заказов использует created_at

**Файл:** `orders/services.py` (строки 606-615)  
**Проблема:** Используется `created_at` вместо `confirmed_at`.

**Предварительно:** Проверить наличие поля `confirmed_at` в модели Order. Если отсутствует — добавить миграцию.

**Исправление:**
```python
candidate_orders = list(
    Order.objects.filter(
        delivery_method=Order.DeliveryMethod.PICKUP,
        status__in=self.ELIGIBLE_ORDER_STATUSES,
        fulfillment_status__in=self.ELIGIBLE_FULFILLMENT_STATUSES,
        confirmed_at__lte=rough_cutoff,  # <-- изменить с created_at
    )
    .exclude(payment_status__in=self.NON_CANCELLABLE_PAYMENT_STATUSES)
    ...
)
```

---

## Этап 5: Средние приоритеты (деплой)

### 5.1 Healthcheck для redis

**Файл:** `docker-compose.yaml` (сервис redis)  
**Проблема:** Отсутствует healthcheck.

**Исправление:**
```yaml
redis:
  image: redis:7-alpine
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 5s
    timeout: 3s
    retries: 5
    start_period: 5s
```

---

### 5.2 Graceful shutdown для Celery worker

**Файл:** `docker-compose.yaml` (сервис worker)  
**Проблема:** Нет graceful shutdown.

**Исправление:**
```yaml
worker:
  build: .
  user: "10001:10001"
  stop_signal: SIGTERM
  stop_grace_period: 30s
  command: >
    celery -A config worker
    --loglevel=${CELERY_LOG_LEVEL:-info}
    --concurrency=2
  ...
```

---

### 5.3 Логи в volume

**Файл:** `docker-compose.yaml` (сервис web и volumes)  
**Проблема:** Логи не сохраняются при пересоздании контейнера.

**Исправление:**
```yaml
web:
  build: .
  user: "10001:10001"
  volumes:
    - static_data:/app/staticfiles
    - media_data:/app/media
    - logs_data:/app/logs  # <-- добавить
  ...

# В конце файла добавить:
volumes:
  static_data:
  media_data:
  logs_data:
```

---

## Этап 6: Низкие приоритеты

### 6.1 Проверка совпадения email в checkout

**Файл:** `orders/forms.py` (строки 88-89)  
**Приоритет:** Низкий

**Исправление:**
```python
def __init__(self, *args, user=None, **kwargs):
    super().__init__(*args, **kwargs)
    self.user = user

def clean_email(self):
    email = self._normalize_whitespace(self.cleaned_data["email"])
    if self.user and email != self.user.email:
        raise forms.ValidationError("Email должен совпадать с email вашего аккаунта")
    return email
```

---

### 6.2 Унификация сообщений об ошибке

**Файл:** `users/views.py` (EmailConfirmationView)  
**Приоритет:** Низкий

**Исправление:** Использовать одно сообщение для всех ошибок токена:
```python
messages.error(request, "Недействительная или истекшая ссылка подтверждения.")
```

---

### 6.3 Фиксация версий образов

**Файл:** `docker-compose.yaml`  
**Приоритет:** Низкий

**Исправление:**
```yaml
# Изменить
image: postgres:16.4  # вместо postgres:16
```

---

## Порядок выполнения

### Неделя 1 (Критичные)
```
□ orders/services.py - синхронизация статуса платежа
□ orders/views.py - проверка email в form_valid
□ store/forms.py - ограничение размера файлов
□ docker/nginx/default.conf - безопасность nginx
```

### Неделя 2 (Деплой + бизнес-логика)
```
□ docker-compose.yaml - user, healthchecks, volumes
□ orders/services.py - авто-отмена с confirmed_at
□ orders/views.py - инвалидация токена
```

### Неделя 3 (Оптимизации)
```
□ store/application/cart_context.py - select_for_update
□ orders/services.py - валидация цены
□ orders/forms.py - проверка email
```

---

## Чек-лист приемки

После каждого исправления:

- [ ] Код ревью
- [ ] Unit тесты проходят
- [ ] Интеграционные тесты проходят
- [ ] Ручное тестирование сценария
- [ ] Документация обновлена (при необходимости)

---

## Контакты

При вопросах по плану обращаться к автору анализа.
