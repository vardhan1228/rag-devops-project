# syntax=docker/dockerfile:1

# Single image serving both roles:
#   ECS    -> uvicorn on $PORT (default CMD)
#   Lambda -> awslambdaric with app.ingestion.indexer.lambda_handler (image_config.command)
FROM public.ecr.aws/docker/library/python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ---------------------------------------------------------------- build stage
FROM base AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt \
    && pip install --prefix=/install awslambdaric==3.0.0

# --------------------------------------------------------------- runtime stage
FROM base AS runtime

COPY --from=builder /install /usr/local
COPY app/ ./app/

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV PORT=8000
EXPOSE 8000

# Lambda overrides this entrypoint via image_config.command; ECS uses it as-is.
CMD ["sh", "-c", "exec uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT} --workers 2"]
