#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'matchday_store.settings')
django.setup()

from matchday_store.celery import send_welcome_email

def test_final_email():
    print("=== Финальный тест отправки email ===")
    
    try:
        # Вызов задачи
        result = send_welcome_email.delay('test@example.com')
        print(f"Задача отправлена в очередь. ID: {result.id}")
        print(f"Статус: {result.status}")
        
        # Ожидание результата
        try:
            result.get(timeout=10)
            print(f"Задача выполнена успешно. Результат: {result.result}")
        except Exception as e:
            print(f"Ошибка выполнения задачи: {e}")
            
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_final_email()
