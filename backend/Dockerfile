FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini pytest.ini ./
COPY app ./app
COPY scripts ./scripts

# Listing verification falls back to an HTTP check unless a browser is present.
# To verify with a rendered page instead, set PLAYWRIGHT_ENABLED=true and
# uncomment the next line, which adds roughly 400MB to the image.
# RUN playwright install --with-deps chromium

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/var/resumes \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
