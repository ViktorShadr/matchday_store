#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'matchday_store.settings')
django.setup()

from django.core.mail import send_mail
from django.conf import settings
from celery import current_app

def test_email():
    print("=== Тест отправки email ===")
    print(f"Email backend: {settings.EMAIL_BACKEND}")
    print(f"From email: {settings.DEFAULT_FROM_EMAIL}")
    
    try:
        # Отправка письма
        result = send_mail(
            subject='Тестовое письмо от Celery',
            message='Это тестовое письмо для проверки работы Celery',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=['test@example.com'],
            fail_silently=False,
        )
        print(f"Письмо добавлено в очередь. Результат: {result}")
        
        # Проверяем статус задачи
        if result:
            task_id = result[0].id
            print(f"ID задачи: {task_id}")
            
            # Проверяем результат
            async_result = current_app.AsyncResult(task_id)
            print(f"Статус задачи: {async_result.status}")
            print(f"Результат задачи: {async_result.result}")
            
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_email()
