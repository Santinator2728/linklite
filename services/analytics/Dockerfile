FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY analytics_service ./analytics_service

RUN useradd --create-home --uid 10001 appuser \
    && mkdir /data && chown appuser /data
USER appuser
ENV CLICK_DB_PATH=/data/clicks.db

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "analytics_service.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
