#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'matchday_store.settings')
django.setup()

from matchday_store.celery import app

@app.task
def simple_test():
    return "Hello from Celery!"

def test_simple():
    print("=== Тест простой задачи ===")
    
    try:
        result = simple_test.delay()
        print(f"Задача отправлена. ID: {result.id}")
        
        # Ожидание результата
        try:
            outcome = result.get(timeout=5)
            print(f"Результат: {outcome}")
        except Exception as e:
            print(f"Ошибка выполнения: {e}")
            
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple()
