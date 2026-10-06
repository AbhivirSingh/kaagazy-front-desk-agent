# ==============================================================================
# Multi-stage Dockerfile for SwasthiQ Front Desk Agent
# ==============================================================================

# --- Stage 1: Build React Frontend ---
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Production Python Backend ---
FROM python:3.11-slim
WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code, starter pack, and adversarial suite
COPY backend/ ./backend/
COPY swasthiq-front-desk-agent-starter-pack/ ./swasthiq-front-desk-agent-starter-pack/
COPY adversarial/ ./adversarial/

# Copy built frontend assets to the expected location
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Expose port (default 8000, configurable via PORT env variable)
ENV PORT=8000
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:${PORT}/api/llm/status || exit 1

# Start Uvicorn server
CMD uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}
