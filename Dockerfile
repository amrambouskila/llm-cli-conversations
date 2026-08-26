# =============================================================================
# Multi-stage build: Node builds React, Python runs FastAPI
# =============================================================================

# ---- Stage 1: Build React frontend ----
FROM node:20-alpine AS frontend-build

WORKDIR /build
COPY browser/frontend/package.json browser/frontend/package-lock.json ./
RUN npm ci
COPY browser/frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime ----
FROM python:3.13-slim

# Base-image security patches. The Debian slim bases currently ship a util-linux that Trivy
# flags HIGH (CVE-2026-53612..53615, fixed upstream in 2.41.5). These packages come from the
# base layer, so this is required even though nothing below installs them.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# System packages required by onnxruntime (libgomp for OpenMP runtime)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY browser/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY browser/backend/ ./

# Copy converter scripts (used by the /api/update endpoint)
COPY convert_claude_jsonl_to_md.py /app/convert_claude_jsonl_to_md.py
COPY convert_export.py /app/convert_export.py
COPY convert_codex_sessions.py /app/convert_codex_sessions.py

# Copy built React frontend
COPY --from=frontend-build /build/dist /app/static

# Environment
ENV MARKDOWN_DIR=/data/markdown
ENV RAW_DIR=/data/raw
ENV CLAUDE_PROJECTS_SRC=/data/claude-projects
ENV STATIC_DIR=/app/static
ENV PORT=5050

EXPOSE 5050

# Local-dev container, not a public-facing service, so non-root is exempt per global
# CLAUDE.md section 9. A non-root USER would also break the bind-mounted host directories this
# image reads and writes at runtime. Revisit before any deployment beyond localhost.
# nosemgrep: dockerfile.security.missing-user.missing-user
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5050"]
