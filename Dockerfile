# BOT MATRIX — production image for Railway / Docker
# Node serves SPA + proxies /api → Python (bound to 127.0.0.1 only)
# Keep image light: no torch / opencv / numpy (optional extras only)

FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app
COPY package.json package-lock.json* ./
# Prefer npm ci when lock is in sync; fall back to npm install so missing
# lock entries (e.g. @tonconnect/sdk) do not fail the Railway build.
RUN npm ci || npm install
COPY index.html vite.config.ts tsconfig.json metadata.json ./
COPY public ./public
COPY src ./src
ENV NODE_ENV=production
RUN npx vite build

FROM node:22-bookworm-slim AS production
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    build-essential libffi-dev libssl-dev \
    libjpeg62-turbo libpng16-16 \
    curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json* ./
RUN (npm ci --omit=dev || npm install --omit=dev) && npm install esbuild --no-save

COPY --from=frontend-build /app/dist ./dist

COPY server.ts tsconfig.json ./
RUN npx esbuild server.ts --bundle --platform=node --format=cjs --packages=external --outfile=dist/server.cjs

COPY backend ./backend
RUN python3 -m pip install --no-cache-dir --break-system-packages -r backend/requirements.txt

RUN mkdir -p /app/storage /app/storage/captcha

ENV NODE_ENV=production \
    API_PORT=5001 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=8s --start-period=45s --retries=5 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-3000}/health" || exit 1

CMD ["node", "dist/server.cjs"]
