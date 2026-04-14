"""Smoke test: schema initializes via init_db (in db_engine fixture) and tables are empty."""
from __future__ import annotations

from sqlalchemy import text


async def test_sessions_table_initialized_and_empty(db_engine):
    async with db_engine.connect() as conn:
        result = await conn.execute(text("SELECT count(*) FROM conversations.sessions"))
        assert result.scalar_one() == 0
