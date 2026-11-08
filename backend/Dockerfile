# Runner Sidekick API and sync (one image; docker-compose.yml at the repo root runs it twice).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    RSK_DATA_DIR=/data

# Time zones for zoneinfo
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY sidekick ./sidekick

# Runs as an unprivileged user; /data (tokens, Garmin tokens, secrets.json) is a volume
RUN useradd --system --uid 10001 --home-dir /data sidekick && mkdir -p /data && chown sidekick /data && chmod 700 /data
USER sidekick
VOLUME /data

EXPOSE 8765
# Plain HTTP inside the container; TLS comes from a reverse proxy in front (docs/SELF_HOSTING.md)
CMD ["python", "-m", "sidekick", "serve", "--host", "0.0.0.0", "--port", "8765", "--behind-proxy"]
