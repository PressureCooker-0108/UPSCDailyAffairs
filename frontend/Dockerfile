# ──────────────────────────────────────────────
# News Dashboard — Frontend Dockerfile
# ──────────────────────────────────────────────
# Build:
#   docker build -t news-frontend -f frontend/Dockerfile frontend/
#
# Run:
#   docker run -p 3000:3000 \
#     -e NEXT_PUBLIC_API_URL=https://your-backend.onrender.com \
#     news-frontend
# ──────────────────────────────────────────────

# ── Build stage ──────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install all deps (including devDeps needed for build)
COPY package.json package-lock.json* ./
RUN npm ci && npm cache clean --force

# Copy source
COPY . .

# Build
RUN npm run build


# ── Runtime stage ────────────────────────────
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

# Copy built app from builder
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/next.config.ts ./next.config.ts

EXPOSE 3000

CMD ["npm", "start"]
