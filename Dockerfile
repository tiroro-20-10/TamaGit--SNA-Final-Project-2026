FROM python:3.11-slim

WORKDIR /app

# Копируем только код проекта
COPY src/ /app/src/

# Устанавливаем зависимости
RUN pip install --no-cache-dir pydantic

# Чтобы Python видел модули
ENV PYTHONPATH=/app

# Запуск по умолчанию
ENTRYPOINT ["python", "-m", "src.main"]
