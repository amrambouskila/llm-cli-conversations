---
name: schema
description: Show the current database schema and compare against DESIGN.md
---

Compare the actual database state against what DESIGN.md §5 specifies.

1. Read DESIGN.md §5 (Data Model) to get the intended schema.
2. Check if a schema file exists (e.g., `browser/backend/schema.sql`, `browser/backend/migrate.py`, or similar).
3. If found, compare the implemented schema against the design and report:
   - Tables/columns that match the design
   - Tables/columns missing from implementation
   - Tables/columns in implementation but not in design
4. If no schema file exists yet, report that and summarize what needs to be built per the design.