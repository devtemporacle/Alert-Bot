"""Unit tests for the post-spike pre-empt rule.

Threshold is < -15.0% on Dex Screener's priceChange.m5 (strict inequality —
"more than 15% below ATH"). All other parts of the Pair are irrelevant to
this filter, so we use a minimal builder.
"""

from __future__ import annotations

from alert_bot.dex_screener_client import Pair
from alert_bot.post_spike_filter import (
    POST_SPIKE_M5_THRESHOLD_PCT,
    check_post_spike,
)


def _pair_with_m5(m5_pct: float) -> Pair:
    """Minimal Pair carrying only the field this filter looks at."""
    return Pair(
        chain_id="solana",
        dex_id="pumpswap",
        pair_address="PAIR1",
        base_token_address="MINT1",
        base_token_symbol="TEST",
        base_token_name="Test",
        price_usd=0.0001,
        liquidity_usd=30_000.0,
        fdv_usd=100_000.0,
        market_cap_usd=200_000.0,
        volume_h1_usd=60_000.0,
        volume_m5_usd=6_000.0,
        txns_h1=800,
        txns_m5=80,
        buys_m5=50,
        pair_created_at_ms=0,
        socials=(),
        websites=(),
        dexscreener_url="https://dexscreener.com/solana/PAIR1",
        price_change_m5_pct=m5_pct,
        price_change_h1_pct=0.0,
    )


def test_threshold_constant_is_minus_15() -> None:
    """Guard against accidental drift of the rule the user set."""
    assert POST_SPIKE_M5_THRESHOLD_PCT == -15.0


def test_flat_price_is_not_post_spike() -> None:
    result = check_post_spike(_pair_with_m5(0.0))
    assert not result.is_post_spike


def test_modest_drop_is_not_post_spike() -> None:
    result = check_post_spike(_pair_with_m5(-10.0))
    assert not result.is_post_spike


def test_drop_at_exactly_minus_15_is_not_post_spike() -> None:
    """Strict inequality — '> 15% below' means m5 must be < -15.0."""
    result = check_post_spike(_pair_with_m5(-15.0))
    assert not result.is_post_spike


def test_drop_just_below_minus_15_is_post_spike() -> None:
    result = check_post_spike(_pair_with_m5(-15.01))
    assert result.is_post_spike
    assert "15.0%" in result.reason or "15.01%" in result.reason


def test_severe_drop_is_post_spike() -> None:
    result = check_post_spike(_pair_with_m5(-40.0))
    assert result.is_post_spike
    assert "40.0%" in result.reason


def test_price_increase_is_not_post_spike() -> None:
    """Upward-moving price never triggers the filter."""
    result = check_post_spike(_pair_with_m5(+25.0))
    assert not result.is_post_spike


def test_result_carries_raw_m5_value() -> None:
    result = check_post_spike(_pair_with_m5(-22.5))
    assert result.price_change_m5_pct == -22.5
