# FeedLens backend — chế độ cloud.
# Có Chromium (headless shell) cho chế độ "Server": lướt bằng cookie user đã lưu, không cần agent trên máy.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FEEDLENS_MODE=cloud \
    FEEDLENS_BROWSER_CHANNEL=chromium \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app
COPY pyproject.toml ./
COPY feedlens ./feedlens
RUN pip install ".[postgres]" \
 && python -m playwright install --with-deps --only-shell chromium \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home app && mkdir -p /app/data && chown app /app/data
USER app

EXPOSE 8000
CMD ["sh", "-c", "uvicorn feedlens.api:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
