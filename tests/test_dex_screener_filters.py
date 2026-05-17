"""Unit tests for the numeric pre-filter applied to Dex Screener pairs.

Most of the filter logic is exercised end-to-end by the scorer tests via
fully-built Pair objects. This file focuses on edge cases of the max-MCAP
cap added for the 'freshly-graduated, low MCAP' bias.
"""

from __future__ import annotations

import time
from dataclasses import replace

from alert_bot.config import FilterThresholds
from alert_bot.dex_screener_client import Pair, passes_filters


def _baseline_pair(**overrides) -> Pair:
    """A pair that passes every check by default; tests override individual fields."""
    now_ms = time.time() * 1000.0
    base = Pair(
        chain_id="solana",
        dex_id="pumpswap",
        pair_address="PAIR1",
        base_token_address="MINT1",
        base_token_symbol="TEST",
        base_token_name="Test",
        price_usd=0.0001,
        liquidity_usd=30_000.0,
        fdv_usd=60_000.0,
        market_cap_usd=60_000.0,
        volume_h1_usd=40_000.0,
        volume_m5_usd=6_000.0,
        txns_h1=800,
        txns_m5=80,
        buys_m5=50,
        pair_created_at_ms=int(now_ms - 3 * 3_600_000.0),
        socials=("twitter",),
        websites=(),
        dexscreener_url="https://dexscreener.com/solana/PAIR1",
        price_change_m5_pct=0.0,
        price_change_h1_pct=0.0,
    )
    return replace(base, **overrides)


def test_baseline_pair_passes() -> None:
    assert passes_filters(_baseline_pair())


def test_mcap_at_default_80k_cap_passes() -> None:
    # Default cap is exactly 80_000; equality should pass (<= comparison).
    assert passes_filters(_baseline_pair(market_cap_usd=80_000.0))


def test_mcap_just_above_default_cap_fails() -> None:
    assert not passes_filters(_baseline_pair(market_cap_usd=80_001.0))


def test_high_mcap_fails_even_when_everything_else_is_perfect() -> None:
    assert not passes_filters(_baseline_pair(market_cap_usd=250_000.0))


def test_zero_mcap_is_treated_as_unknown_and_does_not_block() -> None:
    # Some pairs come back with 0 MCAP from Dex Screener. We don't want a
    # missing data point to silently disqualify an otherwise-valid candidate.
    pair = _baseline_pair(market_cap_usd=0.0, fdv_usd=0.0)
    assert passes_filters(pair)


def test_fdv_used_as_fallback_when_market_cap_is_zero() -> None:
    # market_cap missing -> fall through to fdv -> apply same cap.
    assert passes_filters(_baseline_pair(market_cap_usd=0.0, fdv_usd=60_000.0))
    assert not passes_filters(_baseline_pair(market_cap_usd=0.0, fdv_usd=200_000.0))


def test_disabling_mcap_cap_lets_high_mcap_through() -> None:
    # max_market_cap_usd <= 0 disables the cap.
    pair = _baseline_pair(market_cap_usd=500_000.0)
    relaxed = FilterThresholds(max_market_cap_usd=0.0)
    assert passes_filters(pair, relaxed)
