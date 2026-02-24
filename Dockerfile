# ============================================================
# Argus — The All-Seeing Code Reviewer
# Multi-stage Docker build: React frontend + Python backend
# ============================================================

# --- Stage 1: Build React Dashboard ---
FROM node:20-alpine AS frontend-build

WORKDIR /app/dashboard

# Install dependencies first (layer caching)
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm install

# Copy source and build
COPY dashboard/ ./
RUN npm run build

# --- Stage 2: Python Runtime ---
FROM python:3.12-slim

# System dependencies (git is needed for CLI local reviews)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY cli/ ./cli/
COPY pyproject.toml ./

# Install the package (registers `argus` CLI command)
RUN pip install --no-cache-dir -e .

# Copy React build from stage 1
COPY --from=frontend-build /app/dashboard/dist ./dashboard/dist

# Copy entrypoint (sed fixes Windows CRLF line endings)
COPY docker-entrypoint.sh ./
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

# Create data directory for SQLite database
RUN mkdir -p /data

# Default environment variables
ENV APP_HOST=0.0.0.0
ENV APP_PORT=8000
ENV LOG_LEVEL=info
ENV DATABASE_URL=sqlite+aiosqlite:////data/codereview.db

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["server"]
