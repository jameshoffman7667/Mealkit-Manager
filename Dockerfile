FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    TZ=America/Toronto \
    PORT=8044 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# tini forwards SIGTERM so the container stops cleanly. Tesseract reads photographed promo codes.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini tesseract-ocr tesseract-ocr-eng tesseract-ocr-fra tzdata curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chromium for the account connectors (adds roughly 400 MB to the image).
RUN playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/*

COPY VERSION ./VERSION
COPY app ./app

# Run as 1000:100 so the data folder owner matches the server standard.
RUN useradd --system --uid 1000 --gid 100 --no-create-home app \
    && mkdir -p /data && chown 1000:100 /data
USER 1000:100
VOLUME /data
EXPOSE 8044

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/healthz" >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --timeout-graceful-shutdown 8"]
