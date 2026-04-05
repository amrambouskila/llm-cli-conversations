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

WORKDIR /app

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

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5050"]
