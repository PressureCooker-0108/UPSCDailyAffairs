# ──────────────────────────────────────────────
# News Dashboard — Backend Dockerfile
# ──────────────────────────────────────────────
# Built from the repo root. Render uses repo root as build context, so all
# paths in COPY are relative to the repo root.
#
# Build locally:
#   docker build -t news-backend -f Dockerfile .
#
# Run with Docker Compose:
#   docker compose up -d
#
# Deploy on Render:
#   Push to GitHub; Render auto-builds from the Dockerfile at the root.
# ──────────────────────────────────────────────

FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies (needed for hdbscan when no wheel exists)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (cached layer)
# --only-binary :all: forces pre-compiled wheels — avoids 10+ min compilation
# of hdbscan/scikit-learn on Render's limited CPU. Falls back to source build
# if a wheel isn't available (unlikely on Linux amd64).
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --user --only-binary :all: -r requirements.txt || \
    pip install --no-cache-dir --user -r requirements.txt


# ── Runtime stage ────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Ensure local binaries are on PATH
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy backend application code — from repo root context, backend/ goes to /app/
COPY backend/ .

# Health check — hits the / endpoint which does not touch the database.
# Uses shell form so $PORT expands correctly (Render sets PORT).
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8001}/')" || exit 1

EXPOSE 8001

# Single worker for Render's 512MB free tier — --workers 2 causes OOM.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001}"]
