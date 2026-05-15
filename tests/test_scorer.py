"""Unit tests for scorer.py — the module that encodes the trading rules.

The scorer is the single most important module to test: it's the bridge
between "raw market data" and "send an alert", and the entire portfolio
case rests on these rules being applied consistently.

Tests use small builder functions for Pair/RugcheckResult/NarrativeCheck
so each test only needs to specify the fields it cares about.
"""

from __future__ import annotations

import time

import pytest

from alert_bot.config import SCORING
from alert_bot.dex_screener_client import Pair
from alert_bot.narrative_filter import NarrativeCheck
from alert_bot.rugcheck_client import RugcheckResult
from alert_bot.scorer import (
    ScoredCandidate,
    score_candidate,
)


# --- builders --------------------------------------------------------------

def make_pair(
    *,
    age_hours: float = 3.0,
    liquidity_usd: float = 30_000.0,
    volume_h1_usd: float = 60_000.0,
    volume_m5_usd: float = 6_000.0,  # 6_000 * 12 = 72k > 60k -> accelerating
    txns_h1: int = 800,
    txns_m5: int = 80,
    buys_m5: int = 50,
    socials: tuple[str, ...] = ("twitter", "telegram"),
    websites: tuple[str, ...] = (),
    base_token_symbol: str = "TEST",
    base_token_name: str = "Test Token",
) -> Pair:
    now_ms = time.time() * 1000.0
    pair_created_at_ms = int(now_ms - age_hours * 3_600_000.0)
    return Pair(
        chain_id="solana",
        dex_id="pumpswap",
        pair_address="PAIR1",
        base_token_address="MINT1",
        base_token_symbol=base_token_symbol,
        base_token_name=base_token_name,
        price_usd=0.0001,
        liquidity_usd=liquidity_usd,
        fdv_usd=100_000.0,
        market_cap_usd=200_000.0,
        volume_h1_usd=volume_h1_usd,
        volume_m5_usd=volume_m5_usd,
        txns_h1=txns_h1,
        txns_m5=txns_m5,
        buys_m5=buys_m5,
        pair_created_at_ms=pair_created_at_ms,
        socials=socials,
        websites=websites,
        dexscreener_url="https://dexscreener.com/solana/PAIR1",
    )


def make_rugcheck(
    *,
    score_normalised: int = 16,
    rugged: bool = False,
    mint_off: bool = True,
    freeze_off: bool = True,
    top_10_pct: float = 22.0,
    creator_balance: int = 0,
    insider_count: int = 0,
    danger_risks: tuple[str, ...] = (),
    has_pumpfun_amm: bool = True,
    lp_locked_pct: float = 0.0,
) -> RugcheckResult:
    return RugcheckResult(
        contract="MINT1",
        score_normalised=score_normalised,
        rugged=rugged,
        mint_authority_disabled=mint_off,
        freeze_authority_disabled=freeze_off,
        top_10_holder_pct=top_10_pct,
        creator_balance=creator_balance,
        insider_count=insider_count,
        danger_risks=danger_risks,
        has_pumpfun_amm_market=has_pumpfun_amm,
        lp_locked_pct=lp_locked_pct,
    )


def make_narrative(passed: bool = True, reasons: tuple[str, ...] = ()) -> NarrativeCheck:
    return NarrativeCheck(passed=passed, reasons=reasons)


# --- happy path ------------------------------------------------------------

def test_perfect_candidate_scores_5_of_5() -> None:
    sc = score_candidate(make_pair(), make_rugcheck(), make_narrative())
    assert sc.score == 5
    assert sc.score_max == 5
    assert sc.meets_alert_threshold()
    assert all(c.passed for c in sc.checks)


def test_default_threshold_is_four() -> None:
    # Sanity-check the constant the rest of the bot relies on.
    assert SCORING.alert_score_threshold == 4


# --- individual check failure modes ---------------------------------------

def test_rugged_token_fails_rugcheck_only() -> None:
    sc = score_candidate(make_pair(), make_rugcheck(rugged=True), make_narrative())
    rugcheck_outcome = sc.checks[0]
    assert rugcheck_outcome.name == "Rugcheck"
    assert not rugcheck_outcome.passed
    assert "rugged" in rugcheck_outcome.detail
    assert sc.score == 4  # everything else still passes
    assert sc.meets_alert_threshold()  # 4/5 is still a Go


def test_mint_authority_still_enabled_fails_rugcheck() -> None:
    sc = score_candidate(make_pair(), make_rugcheck(mint_off=False), make_narrative())
    assert not sc.checks[0].passed
    assert "mint authority" in sc.checks[0].detail


def test_freeze_authority_still_enabled_fails_rugcheck() -> None:
    sc = score_candidate(make_pair(), make_rugcheck(freeze_off=False), make_narrative())
    assert not sc.checks[0].passed
    assert "freeze authority" in sc.checks[0].detail


def test_danger_risk_fails_rugcheck() -> None:
    sc = score_candidate(
        make_pair(),
        make_rugcheck(danger_risks=("Mint authority not revoked",)),
        make_narrative(),
    )
    assert not sc.checks[0].passed
    assert "Mint authority not revoked" in sc.checks[0].detail


def test_high_rugcheck_score_fails() -> None:
    sc = score_candidate(make_pair(), make_rugcheck(score_normalised=80), make_narrative())
    assert not sc.checks[0].passed


def test_creator_still_holding_fails_rugcheck() -> None:
    sc = score_candidate(make_pair(), make_rugcheck(creator_balance=10_000), make_narrative())
    assert not sc.checks[0].passed
    assert "creator still holds" in sc.checks[0].detail


def test_no_lp_protection_fails_rugcheck() -> None:
    sc = score_candidate(
        make_pair(),
        make_rugcheck(has_pumpfun_amm=False, lp_locked_pct=0.0),
        make_narrative(),
    )
    assert not sc.checks[0].passed


def test_locked_lp_without_pumpfun_amm_passes() -> None:
    # External locker holds LP, no pumpfun AMM — still counts as protected.
    sc = score_candidate(
        make_pair(),
        make_rugcheck(has_pumpfun_amm=False, lp_locked_pct=95.0),
        make_narrative(),
    )
    assert sc.checks[0].passed


def test_concentrated_holders_fails_check_2() -> None:
    sc = score_candidate(make_pair(), make_rugcheck(top_10_pct=40.0), make_narrative())
    holders = sc.checks[1]
    assert holders.name == "Holders distributed"
    assert not holders.passed
    assert sc.score == 4  # 1 of 5 failed


def test_top_10_exactly_at_threshold_fails() -> None:
    # threshold is < 35%, so 35.0 exactly should NOT pass (strict inequality).
    sc = score_candidate(
        make_pair(), make_rugcheck(top_10_pct=SCORING.max_top10_holder_pct), make_narrative()
    )
    assert not sc.checks[1].passed


def test_flat_volume_fails_acceleration_check() -> None:
    # 5m * 12 == 1h exactly — should NOT pass (we want strictly accelerating).
    sc = score_candidate(
        make_pair(volume_h1_usd=60_000.0, volume_m5_usd=5_000.0),  # 5_000*12 == 60_000
        make_rugcheck(),
        make_narrative(),
    )
    vol = sc.checks[2]
    assert vol.name == "Volume accelerating"
    assert not vol.passed


def test_decelerating_volume_fails() -> None:
    sc = score_candidate(
        make_pair(volume_h1_usd=60_000.0, volume_m5_usd=2_000.0),  # projection 24k < 60k
        make_rugcheck(),
        make_narrative(),
    )
    assert not sc.checks[2].passed


def test_zero_5m_volume_fails_acceleration_even_with_zero_1h() -> None:
    # Edge case: no recent activity at all. Should not count as "accelerating".
    sc = score_candidate(
        make_pair(volume_h1_usd=0.0, volume_m5_usd=0.0),
        make_rugcheck(),
        make_narrative(),
    )
    assert not sc.checks[2].passed


def test_no_socials_or_website_fails_check_4() -> None:
    sc = score_candidate(
        make_pair(socials=(), websites=()),
        make_rugcheck(),
        make_narrative(),
    )
    socials = sc.checks[3]
    assert socials.name == "Socials linked"
    assert not socials.passed


def test_website_only_passes_socials_check() -> None:
    # Some tokens have only a website (no twitter/telegram). Still a signal.
    sc = score_candidate(
        make_pair(socials=(), websites=("https://example.com",)),
        make_rugcheck(),
        make_narrative(),
    )
    assert sc.checks[3].passed


def test_narrative_flag_fails_check_5() -> None:
    sc = score_candidate(
        make_pair(),
        make_rugcheck(),
        make_narrative(passed=False, reasons=("brand:phantom",)),
    )
    nar = sc.checks[4]
    assert nar.name == "Narrative"
    assert not nar.passed
    assert "brand:phantom" in nar.detail


# --- threshold + render ---------------------------------------------------

def test_three_of_five_does_not_meet_threshold() -> None:
    # Fail 2 checks: top-10 too high and narrative flagged.
    sc = score_candidate(
        make_pair(),
        make_rugcheck(top_10_pct=50.0),
        make_narrative(passed=False, reasons=("brand:phantom",)),
    )
    assert sc.score == 3
    assert not sc.meets_alert_threshold()


def test_two_of_five_does_not_meet_threshold() -> None:
    sc = score_candidate(
        make_pair(socials=(), websites=()),
        make_rugcheck(top_10_pct=50.0),
        make_narrative(passed=False, reasons=("brand:phantom",)),
    )
    assert sc.score == 2
    assert not sc.meets_alert_threshold()


def test_render_checklist_has_one_line_per_check() -> None:
    sc = score_candidate(make_pair(), make_rugcheck(), make_narrative())
    lines = sc.render_checklist()
    assert len(lines) == 5
    assert all(line.startswith(("✅", "❌")) for line in lines)


def test_failing_lines_show_red_x() -> None:
    sc = score_candidate(
        make_pair(),
        make_rugcheck(top_10_pct=50.0),
        make_narrative(),
    )
    lines = sc.render_checklist()
    assert any(line.startswith("❌") and "Holders" in line for line in lines)


# --- regression: a realistic 4/5 candidate (John Pork shape) --------------

def test_john_pork_like_candidate_alerts() -> None:
    """Pork passed 4/5 with one yellow flag — insider cluster.
    Insider count is not in the checklist, so it shouldn't reduce the score.
    """
    sc = score_candidate(
        make_pair(
            base_token_symbol="PORK",
            base_token_name="John Pork",
            socials=("twitter", "telegram", "tiktok"),
            volume_h1_usd=80_000.0,
            volume_m5_usd=10_000.0,  # 120K projected
        ),
        make_rugcheck(insider_count=4, top_10_pct=28.0),
        make_narrative(),
    )
    assert sc.score == 5
    assert sc.meets_alert_threshold()
