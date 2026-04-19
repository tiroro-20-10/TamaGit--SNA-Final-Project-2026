FROM python:3.11-slim

WORKDIR /app
COPY src/ /app/src/

RUN pip install --no-cache-dir pydantic

ENV PYTHONPATH=/app

ENTRYPOINT ["python", "-m", "src.main"]
