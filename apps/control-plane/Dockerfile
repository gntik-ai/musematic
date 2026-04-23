ARG PYTHON_BASE=mirror.gcr.io/library/python:3.12-slim

FROM ${PYTHON_BASE} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY entrypoints ./entrypoints
COPY migrations ./migrations
COPY lua ./lua

RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -e .

FROM ${PYTHON_BASE} AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home app

COPY --from=builder /usr/local /usr/local
COPY --from=builder /app /app

EXPOSE 8000

USER app

ENTRYPOINT ["python", "-m", "uvicorn"]
CMD ["platform.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
