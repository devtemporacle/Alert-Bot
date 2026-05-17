"""Post-spike filter — pre-empts the 4/5 scorer for spike-and-dump tokens.

Strategy 1: "The chart already ran = you're the exit liquidity. Never buy a
vertical candle that's already gone parabolic." This module encodes that
constraint as a hard gate that fires BEFORE the normal Go/No-Go scoring.

Rule (v1):
    If priceChange.m5 <= -15%  -> flag as POST-SPIKE, send chart-review
    alert instead of running the normal 4/5 evaluation.

Why m5 vs a 15-minute rolling window: Dex Screener's public API doesn't
expose ATH or a per-token price history endpoint. priceChange.m5 is the
% change from 5 minutes ago to now. A reading of -15% means the price 5
minutes ago was ~17.6% higher than now — which is "ATH within 15 min and
>15% below ATH" by definition (5 min is a subset of 15 min).

A future v1.1 can track our own rolling 15-min history per contract to
catch peaks that happened 5-15 min ago. Skipped in v1 because the m5
proxy covers the most dangerous cases and needs no extra state.
"""

from __future__ import annotations

from dataclasses import dataclass

from alert_bot.dex_screener_client import Pair

# Threshold for the m5 change. Strict inequality matches "more than 15% below."
POST_SPIKE_M5_THRESHOLD_PCT: float = -15.0


@dataclass(frozen=True)
class PostSpikeResult:
    """Outcome of the post-spike check for one pair."""

    is_post_spike: bool
    # Short human-readable explanation — surfaced in the alert card.
    reason: str
    # Raw priceChange.m5 value (negative = drop). Useful for logging.
    price_change_m5_pct: float


def check_post_spike(pair: Pair) -> PostSpikeResult:
    """Apply the post-spike rule.

    Returns a PostSpikeResult; callers decide whether to short-circuit
    normal scoring based on `is_post_spike`.
    """
    m5 = pair.price_change_m5_pct
    if m5 < POST_SPIKE_M5_THRESHOLD_PCT:
        # m5 of -20 means price was ~25% higher 5 min ago; we report the
        # raw figure since it's the most honest number the API gives us.
        return PostSpikeResult(
            is_post_spike=True,
            reason=(
                f"Down {abs(m5):.1f}% in 5 min — recent peak inside the 15-min "
                f"window with current price >15% below it."
            ),
            price_change_m5_pct=m5,
        )
    return PostSpikeResult(
        is_post_spike=False,
        reason=f"5m change {m5:+.1f}% (threshold {POST_SPIKE_M5_THRESHOLD_PCT:.0f}%)",
        price_change_m5_pct=m5,
    )
