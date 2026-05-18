FROM python:3.11-bookworm AS runtime

WORKDIR /app
RUN apt-get update -o Acquire::Retries=3 \
    && apt-get install -y --no-install-recommends -o Acquire::Retries=3 git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --global --add safe.directory /workspace

COPY pyproject.toml README.md /app/
# Устанавливаем все зависимости включая textual
RUN pip install --no-cache-dir \
    "fastapi>=0.115,<0.116" \
    "uvicorn>=0.34,<0.35" \
    "textual>=0.80.0" \
    "pytest>=8.0"
COPY src/ /app/src/

ENV PYTHONPATH=/app

ENTRYPOINT ["python", "-m", "src.main"]


FROM runtime AS test
COPY tests/ /app/tests/
RUN pip install --no-cache-dir pytest
ENTRYPOINT ["python", "-m", "pytest"]
CMD ["-q"]
