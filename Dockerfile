FROM python:3.12-slim

# Установка Poetry
RUN pip install poetry

# Установка рабочей директории
WORKDIR /app

# Копирование файлов конфигурации Poetry
COPY pyproject.toml poetry.lock ./

# Настройка Poetry
RUN poetry config virtualenvs.create false

# Установка зависимостей
RUN poetry install --only main --no-interaction --no-ansi --no-root

# Копирование кода приложения
COPY . .

# Создание директории для логов
RUN mkdir -p logs

# Команда по умолчанию для worker
CMD ["celery", "-A", "matchday_store", "worker", "-l", "info"]
