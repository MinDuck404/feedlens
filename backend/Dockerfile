# FeedLens backend — chế độ cloud (không có trình duyệt; bot lướt chạy trên máy người dùng)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FEEDLENS_MODE=cloud

WORKDIR /app
COPY pyproject.toml ./
COPY feedlens ./feedlens
RUN pip install ".[postgres]" && useradd --create-home app && mkdir -p /app/data && chown app /app/data
USER app

EXPOSE 8000
CMD ["sh", "-c", "uvicorn feedlens.api:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
