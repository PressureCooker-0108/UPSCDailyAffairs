# ──────────────────────────────────────────────
# ╔══════════════════════════════════════════════╗
# ║  DEPRECATED — use ./Dockerfile (repo root)   ║
# ╚══════════════════════════════════════════════╝
# ──────────────────────────────────────────────
# This file is kept for local reference only.
# Render now builds from the Dockerfile at the repo root.
#
# The root Dockerfile uses `COPY backend/...` paths to work
# correctly with Render's repo-root build context.
# ──────────────────────────────────────────────

FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user --only-binary :all: -r requirements.txt || \
    pip install --no-cache-dir --user -r requirements.txt


FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /root/.local /root/.local

ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY . .

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8001}/')" || exit 1

EXPOSE 8001

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001}"]
