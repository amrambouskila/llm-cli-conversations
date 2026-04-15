"""Canonical cost-formula tests (Phase 7.5).

Covers:
- estimate_cost_breakdown: exact per-model cases for opus/sonnet/haiku
- Unknown-model fallback to sonnet pricing
- Explicit 1.25x cache-write premium (5-minute TTL)
- Null/zero token defaults
- total_usd == sum of the four component fields
- recompute_session_costs: idempotency + pre-7.5 row migration delta
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from load import (
    CACHE_READ_DISCOUNT,
    CACHE_WRITE_PREMIUM_5M,
    MODEL_PRICING,
    estimate_cost,
    estimate_cost_breakdown,
    recompute_session_costs,
)
from models import Session as SessionModel

# ---------------------------------------------------------------------------
# Pure function: per-model pricing cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "input_t,output_t,cache_r,cache_c,expected_total",
    [
        # (input_tokens, output_tokens, cache_read, cache_creation, expected_total_usd)
        #
        # Case A: pure input/output, no cache.
        #   input = 10k * 15/1M = 0.15
        #   output = 5k * 75/1M = 0.375
        #   total = 0.525
        (10_000, 5_000, 0, 0, 0.525),
        # Case B: cache-read heavy.
        #   input = 1k * 15/1M = 0.015
        #   output = 1k * 75/1M = 0.075
        #   cache_read = 5M * 15 * 0.1 / 1M = 7.5
        #   total = 7.59
        (1_000, 1_000, 5_000_000, 0, 7.59),
        # Case C: cache-write heavy.
        #   input = 1k * 15/1M = 0.015
        #   output = 1k * 75/1M = 0.075
        #   cache_create = 100k * 15 * 1.25 / 1M = 1.875
        #   total = 1.965
        (1_000, 1_000, 0, 100_000, 1.965),
    ],
)
def test_cost_opus(input_t, output_t, cache_r, cache_c, expected_total):
    breakdown = estimate_cost_breakdown(
        input_tokens=input_t,
        output_tokens=output_t,
        cache_read_tokens=cache_r,
        cache_creation_tokens=cache_c,
        model="claude-opus-4-6",
    )
    assert breakdown.total_usd == pytest.approx(expected_total, abs=0.0001)


@pytest.mark.parametrize(
    "input_t,output_t,cache_r,cache_c,expected_total",
    [
        # Sonnet: input $3, output $15 per 1M
        # Case A: pure input/output
        #   10k * 3/1M + 5k * 15/1M = 0.03 + 0.075 = 0.105
        (10_000, 5_000, 0, 0, 0.105),
        # Case B: cache-read only
        #   1M * 3 * 0.1 / 1M = 0.30
        (0, 0, 1_000_000, 0, 0.30),
        # Case C: cache-write only
        #   1M * 3 * 1.25 / 1M = 3.75
        (0, 0, 0, 1_000_000, 3.75),
    ],
)
def test_cost_sonnet(input_t, output_t, cache_r, cache_c, expected_total):
    breakdown = estimate_cost_breakdown(
        input_tokens=input_t,
        output_tokens=output_t,
        cache_read_tokens=cache_r,
        cache_creation_tokens=cache_c,
        model="claude-sonnet-4-6",
    )
    assert breakdown.total_usd == pytest.approx(expected_total, abs=0.0001)


@pytest.mark.parametrize(
    "input_t,output_t,cache_r,cache_c,expected_total",
    [
        # Haiku: input $0.80, output $4 per 1M
        # Case A: pure input/output
        #   100k * 0.80/1M + 50k * 4/1M = 0.08 + 0.20 = 0.28
        (100_000, 50_000, 0, 0, 0.28),
        # Case B: cache-read
        #   100k * 0.80 * 0.1 / 1M = 0.008
        (0, 0, 100_000, 0, 0.008),
        # Case C: cache-write
        #   100k * 0.80 * 1.25 / 1M = 0.10
        (0, 0, 0, 100_000, 0.10),
    ],
)
def test_cost_haiku(input_t, output_t, cache_r, cache_c, expected_total):
    breakdown = estimate_cost_breakdown(
        input_tokens=input_t,
        output_tokens=output_t,
        cache_read_tokens=cache_r,
        cache_creation_tokens=cache_c,
        model="claude-haiku-4-5",
    )
    assert breakdown.total_usd == pytest.approx(expected_total, abs=0.0001)


# ---------------------------------------------------------------------------
# Fallbacks + edge cases
# ---------------------------------------------------------------------------

def test_unknown_model_falls_back_to_sonnet_pricing():
    """Unknown model names fall through to the default ($3/$15 per 1M) rate."""
    breakdown = estimate_cost_breakdown(
        input_tokens=10_000,
        output_tokens=5_000,
        model="future-model-xyz",
    )
    # Falls back to (3.00, 15.00): 10k*3/1M + 5k*15/1M = 0.030 + 0.075 = 0.105
    assert breakdown.total_usd == pytest.approx(0.105, abs=0.0001)


def test_future_opus_variant_matches_via_prefix():
    """Model like 'claude-opus-5-0' (hypothetical future) should prefix-match opus pricing."""
    # "claude-opus-5-0".rsplit("-", 1)[0] = "claude-opus-5"
    # "claude-opus-4-6".rsplit("-", 1)[0] = "claude-opus-4"
    # "claude-opus-5-0".startswith("claude-opus-4") = False → doesn't match opus-4
    # "claude-opus-5-0".startswith("claude-opus-5") would require an existing "claude-opus-5-X" row.
    # Instead, use a suffix variant of an existing model that triggers the prefix path:
    breakdown = estimate_cost_breakdown(
        input_tokens=10_000,
        output_tokens=5_000,
        model="claude-opus-4-6-preview",  # startswith("claude-opus-4") → opus pricing
    )
    # Should match opus: 10k*15/1M + 5k*75/1M = 0.15 + 0.375 = 0.525
    assert breakdown.total_usd == pytest.approx(0.525, abs=0.0001)


def test_estimate_cost_from_row_char_count_fallback_path():
    """_estimate_cost_from_row hits the char-count path when all token columns are zero."""
    from load import _estimate_cost_from_row

    cost = _estimate_cost_from_row(
        model="claude-opus-4-6",
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        total_chars=40_000,  # 40k chars // 4 = 10k tokens * $3/1M = $0.03
    )
    assert float(cost) == pytest.approx(0.03, abs=0.0001)


def test_estimate_cost_from_row_none_total_chars():
    """_estimate_cost_from_row with None everywhere returns $0."""
    from load import _estimate_cost_from_row

    cost = _estimate_cost_from_row(
        model=None,
        input_tokens=None,
        output_tokens=None,
        cache_read_tokens=None,
        cache_creation_tokens=None,
        total_chars=None,
    )
    assert float(cost) == 0.0


def test_cache_write_uses_5m_premium():
    """Cache-write must be billed at exactly CACHE_WRITE_PREMIUM_5M × input price."""
    # Opus: input_price = 15. 1M tokens * 15 * 1.25 / 1M = 18.75.
    breakdown = estimate_cost_breakdown(
        cache_creation_tokens=1_000_000,
        model="claude-opus-4-6",
    )
    assert breakdown.cache_create_usd == pytest.approx(18.75, abs=0.0001)
    # Also assert explicitly against the naive (no-premium) figure so the
    # premium multiplier is visible in the failure message.
    naive_no_premium = 1_000_000 * 15 / 1_000_000  # 15.00
    assert breakdown.cache_create_usd == pytest.approx(
        naive_no_premium * CACHE_WRITE_PREMIUM_5M, abs=0.0001
    )


def test_cache_read_uses_10pct_discount():
    """Cache-read must be billed at exactly CACHE_READ_DISCOUNT × input price."""
    # Opus: 1M tokens * 15 * 0.1 / 1M = 1.50.
    breakdown = estimate_cost_breakdown(
        cache_read_tokens=1_000_000,
        model="claude-opus-4-6",
    )
    assert breakdown.cache_read_usd == pytest.approx(1.50, abs=0.0001)
    # And against the raw rate:
    naive_input_rate = 1_000_000 * 15 / 1_000_000  # 15.00
    assert breakdown.cache_read_usd == pytest.approx(
        naive_input_rate * CACHE_READ_DISCOUNT, abs=0.0001
    )


def test_null_token_fields_default_to_zero():
    """None values in any token arg must not TypeError — SUM() over nullable cols may return None."""
    breakdown = estimate_cost_breakdown(
        input_tokens=None,
        output_tokens=None,
        cache_read_tokens=None,
        cache_creation_tokens=None,
        model="claude-opus-4-6",
    )
    assert breakdown.input_usd == 0.0
    assert breakdown.output_usd == 0.0
    assert breakdown.cache_read_usd == 0.0
    assert breakdown.cache_create_usd == 0.0
    assert breakdown.total_usd == 0.0


def test_zero_token_fields_produce_zero_breakdown():
    breakdown = estimate_cost_breakdown(model="claude-sonnet-4-6")
    assert breakdown.total_usd == 0.0


def test_total_equals_sum_of_parts():
    """Regression guard against rounding drift — total_usd must be the exact sum of its components."""
    breakdown = estimate_cost_breakdown(
        input_tokens=12_345,
        output_tokens=6_789,
        cache_read_tokens=250_000,
        cache_creation_tokens=40_000,
        model="claude-opus-4-6",
    )
    component_sum = (
        breakdown.input_usd
        + breakdown.output_usd
        + breakdown.cache_read_usd
        + breakdown.cache_create_usd
    )
    # Allow ±0.0002 to absorb a per-component rounding half-ulp on Numeric(10,4).
    assert breakdown.total_usd == pytest.approx(component_sum, abs=0.0002)


def test_none_model_uses_openai_pricing():
    """model=None is the Codex fallback case — picks up 'openai' pricing ($2.50/$10)."""
    breakdown = estimate_cost_breakdown(
        input_tokens=10_000,
        output_tokens=5_000,
        model=None,
    )
    # 10k * 2.50 / 1M + 5k * 10 / 1M = 0.025 + 0.05 = 0.075
    assert breakdown.total_usd == pytest.approx(0.075, abs=0.0001)


def test_estimate_cost_char_count_fallback():
    """estimate_cost() with no meta falls back to char_count // 4 @ $3/1M sonnet-input."""
    cost = estimate_cost(meta=None, model=None, char_count=40_000)
    # 40k chars // 4 = 10k tokens * 3 / 1M = 0.03
    assert float(cost) == pytest.approx(0.03, abs=0.0001)


def test_estimate_cost_uses_breakdown_when_meta_present():
    """estimate_cost() with meta must delegate to estimate_cost_breakdown."""
    from jsonl_reader import SessionMetadata

    meta = SessionMetadata(
        session_id="test",
        model="claude-opus-4-6",
        input_tokens=10_000,
        output_tokens=5_000,
        cache_read_tokens=0,
        cache_creation_tokens=0,
    )
    cost = estimate_cost(meta=meta, model=None, char_count=0)
    # Should match the opus Case A: 0.525
    assert float(cost) == pytest.approx(0.525, abs=0.0001)


def test_estimate_cost_handles_cache_only_session():
    """A session with only cache tokens (no input/output) still uses the breakdown path."""
    from jsonl_reader import SessionMetadata

    meta = SessionMetadata(
        session_id="test",
        model="claude-opus-4-6",
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_creation_tokens=1_000_000,
    )
    # Should hit the breakdown path (not char-count fallback) because cache_creation_tokens > 0.
    # Expected: 1M * 15 * 1.25 / 1e6 = 18.75
    cost = estimate_cost(meta=meta, model=None, char_count=100_000)
    assert float(cost) == pytest.approx(18.75, abs=0.0001)


def test_model_pricing_table_contains_expected_entries():
    """Guard against accidental deletion of a model row."""
    assert "claude-opus-4-6" in MODEL_PRICING
    assert "claude-sonnet-4-6" in MODEL_PRICING
    assert "claude-haiku-4-5" in MODEL_PRICING
    assert "openai" in MODEL_PRICING
    assert MODEL_PRICING["claude-opus-4-6"] == (15.00, 75.00)
    assert MODEL_PRICING["claude-sonnet-4-6"] == (3.00, 15.00)
    assert MODEL_PRICING["claude-haiku-4-5"] == (0.80, 4.00)


# ---------------------------------------------------------------------------
# recompute_session_costs: idempotency + old-formula migration
# ---------------------------------------------------------------------------

def _minimal_session(**overrides) -> SessionModel:
    base = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)
    defaults = dict(
        id="recompute-test",
        provider="claude",
        project="recomputeproj",
        model="claude-opus-4-6",
        conversation_id="conv-r",
        started_at=base,
        ended_at=base + timedelta(hours=1),
        turn_count=1,
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        total_chars=0,
        total_words=0,
        estimated_cost=Decimal("0.0000"),
        source_file=None,
        summary_text="",
        session_type="coding",
    )
    defaults.update(overrides)
    return SessionModel(**defaults)


async def test_recompute_session_costs_is_idempotent(db_session):
    """Running recompute twice in a row should leave the second call with changed=0."""
    # Seed one session with cost EXACTLY matching the new formula.
    # Opus pure input/output: 10k*15/1M + 5k*75/1M = 0.525
    s = _minimal_session(
        id="idempotent-test",
        input_tokens=10_000,
        output_tokens=5_000,
        estimated_cost=Decimal("0.5250"),
    )
    db_session.add(s)
    await db_session.commit()

    checked1, changed1 = await recompute_session_costs()
    assert checked1 == 1
    assert changed1 == 0  # already correct

    checked2, changed2 = await recompute_session_costs()
    assert checked2 == 1
    assert changed2 == 0  # still correct after second run


async def test_recompute_session_costs_fixes_old_formula(db_session):
    """A row written with the pre-7.5 formula (1.0x cache_creation) gets updated to 1.25x."""
    # Opus, 1M cache_creation_tokens, no other tokens.
    # OLD formula (pre-7.5): 1M * 15 / 1M = 15.00
    # NEW formula (Phase 7.5+): 1M * 15 * 1.25 / 1M = 18.75
    # Delta: +3.75
    s = _minimal_session(
        id="old-formula-test",
        cache_creation_tokens=1_000_000,
        estimated_cost=Decimal("15.0000"),  # pre-7.5 value
    )
    db_session.add(s)
    await db_session.commit()

    checked, changed = await recompute_session_costs()
    assert checked == 1
    assert changed == 1

    # Verify the stored value reflects the new formula.
    db_session.expire_all()  # force re-read from DB
    result = await db_session.execute(
        select(SessionModel.estimated_cost).where(SessionModel.id == "old-formula-test")
    )
    new_cost = result.scalar_one()
    assert float(new_cost) == pytest.approx(18.75, abs=0.0001)


async def test_recompute_session_costs_handles_null_tokens(db_session):
    """Sessions with NULL token columns (char-count fallback path) don't crash recompute."""
    # total_chars=4000 → 1000 tokens * $3/1M = $0.003
    s = _minimal_session(
        id="null-tokens-test",
        input_tokens=None,
        output_tokens=None,
        cache_read_tokens=None,
        cache_creation_tokens=None,
        total_chars=4_000,
        estimated_cost=Decimal("0.0030"),  # already matches char-count fallback
    )
    db_session.add(s)
    await db_session.commit()

    checked, changed = await recompute_session_costs()
    assert checked == 1
    # Already correct → no update.
    assert changed == 0
