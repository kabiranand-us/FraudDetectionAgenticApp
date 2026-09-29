# Investigator console for Cloud Run: React frontend built, then served by FastAPI.
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

WORKDIR /app
# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY fraud_agent ./fraud_agent
RUN uv sync --frozen --no-dev
COPY --from=frontend /app/frontend/dist ./frontend/dist

# Cloud Run sets PORT (8080). Settings come from environment variables, not .env.
ENV PORT=8080
CMD ["sh", "-c", "exec /app/.venv/bin/python -m uvicorn fraud_agent.api.main:app --host 0.0.0.0 --port ${PORT}"]
