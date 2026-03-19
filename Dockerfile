FROM node:20-slim AS frontend-build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json vite.config.ts tailwind.config.ts postcss.config.js components.json ./
COPY client/ client/
COPY shared/ shared/
COPY server/ server/
COPY script/ script/
COPY attached_assets/ attached_assets/

RUN npm run build


FROM python:3.11-slim AS python-deps

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1 \
    ffmpeg \
    rubberband-cli \
    librubberband-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    aiohttp bcrypt beautifulsoup4 ebooklib edge-tts fastapi gradio-client \
    httpx lxml mutagen numpy psycopg2-binary pydantic pydub pyrubberband \
    python-multipart scipy soprano-tts soundfile sqlalchemy textblob \
    torch torchaudio uvicorn \
    --extra-index-url https://download.pytorch.org/whl/cpu


FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libsndfile1 \
    ffmpeg \
    rubberband-cli \
    librubberband-dev \
    libpq5 \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=python-deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-deps /usr/local/bin /usr/local/bin

COPY --from=frontend-build /app/dist ./dist
COPY --from=frontend-build /app/node_modules ./node_modules
COPY --from=frontend-build /app/package.json ./

COPY backend/ backend/
COPY shared/ shared/
COPY docs/ docs/
COPY voice_samples/ voice_samples/

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

RUN mkdir -p /app/uploads /app/backend/uploads

ENV NODE_ENV=production
ENV PORT=5000
ENV PYTHON_BACKEND_URL=http://127.0.0.1:8000
ENV SKIP_PYTHON_SPAWN=1

EXPOSE 5000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
