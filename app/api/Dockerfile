# ============================================================================
#  Dockerfile for THIS directory's service: the QUERY API.
#  Runs on ECS Fargate.
#
#  It sits next to the code it builds -- app/api/main.py is right here.
#
#  Build from the REPO ROOT, because the image needs app/ and
#  requirements.txt, and Docker can only copy from inside the build context:
#
#      docker build -f app/api/Dockerfile -t rag-api .
#                      ^ the recipe            ^ the context (repo root)
#
#  Starts:  uvicorn serving app/api/main.py on $PORT
#
#  This image also contains app/retrieval/ and app/ingestion/, because
#  main.py imports from both. There is no Dockerfile in app/retrieval/
#  because retrieval has no entrypoint -- it is a library that runs inside
#  this process. One Dockerfile per process that starts, not one per folder.
# ============================================================================

FROM public.ecr.aws/docker/library/python:3.12-slim

# PYTHONUNBUFFERED makes log output reach CloudWatch immediately instead of
# sitting in a buffer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, application code second. Docker caches each step, so
# editing app/ does not reinstall the packages.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Containers run as root by default. Dropping to an unprivileged user means a
# bug in the app cannot write anywhere important.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT}"]
