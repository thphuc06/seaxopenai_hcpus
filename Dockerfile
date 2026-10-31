# Keep Node/Python aligned with the S0 gate and the OCR Python constraint.
FROM node:24.22.1-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_USE_MOCK=0
RUN npm run build

FROM python:3.11.18-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/backend \
    LLM_MODE=fallback \
    WORKER_INLINE=1 \
    WEB_SEARCH=off \
    OCR_ENABLED=0 \
    AGENTS_TRACING=0 \
    OPENAI_AGENTS_DISABLE_TRACING=1 \
    DB_PATH=/tmp/passport.db \
    PORT=10000
WORKDIR /app/backend
# Optional OCR stays disabled; this image does not add an OCR system-library stack.
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && pip check
COPY backend/app ./app
COPY backend/tests/PHASE ./tests/PHASE
COPY fixtures /app/fixtures
COPY scripts/dev/render /app/scripts/dev/render
COPY scripts/capture_page.py /app/scripts/capture_page.py
COPY --from=frontend /build/frontend/dist /app/frontend/dist
RUN useradd --create-home --uid 10001 passport
USER passport
EXPOSE 10000
CMD ["python", "-m", "scripts.dev.render.server"]
