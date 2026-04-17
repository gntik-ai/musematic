FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY entrypoints ./entrypoints
COPY migrations ./migrations

RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -e .

FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home app

COPY --from=builder /usr/local /usr/local
COPY --from=builder /app /app

EXPOSE 8000

USER app

ENTRYPOINT ["python", "-m", "uvicorn"]
CMD ["platform.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
