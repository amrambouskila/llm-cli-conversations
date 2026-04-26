---
name: endpoints
description: List all API endpoints and which module they belong to
---

Scan `browser/backend/app.py` and `browser/backend/routes/*.py` (if the routes directory exists) for all FastAPI route definitions. Report each endpoint with:
- HTTP method and path
- Which file it's in
- One-line description of what it does