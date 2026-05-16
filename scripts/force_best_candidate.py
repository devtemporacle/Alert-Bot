"""Force-alert on the best candidate the market is currently producing.

Runs ONE full evaluation cycle (DexScreener -> Rugcheck -> narrative -> score)
and sends a Telegram card for the highest-scoring pair, **even if it doesn't
clear the 4/5 alert threshold**. Useful for verifying the full alert path
on real market data without waiting for the strategy to find a true candidate.

The card is prefixed with [FORCED] in the message text so you can tell it
apart from real production alerts. Decisions you make on it are still recorded
in SQLite (same code path as a real alert), so you may want to delete the
test rows afterward:

    DELETE FROM decisions WHERE alert_id IN (
        SELECT id FROM alerts_sent WHERE snapshot_json LIKE '%"forced": true%'
    );
    DELETE FROM alerts_sent WHERE snapshot_json LIKE '%"forced": true%';

Selection rule, in order:
  1. Of the pairs that pass the numeric pre-filters, pick the one with the
     highest 4/5 score (ties broken by liquidity, then by 1h volume).
  2. If no pairs pass the pre-filters, fall back to *all* discovered Solana
     pairs and apply the same scoring + ranking. Surfaces the best the
     market has right now even when nothing is truly fresh.

Usage (from project root, with venv activated):
    python scripts/force_best_candidate.py

Stop the main loop first (Ctrl+C) — Telegram allows only one long-poll
connection per bot token.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Iterable

# Make the project root importable when this file is run directly via
# `python scripts/force_best_candidate.py` (which only puts scripts/ on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alert_bot.config import configure_logging, load_runtime_config
from alert_bot.dex_screener_client import DexScreenerClient, Pair
from alert_bot.narrative_filter import check_narrative
from alert_bot.rugcheck_client import RugcheckClient, RugcheckError
from alert_bot.scorer import ScoredCandidate, score_candidate
from alert_bot.state_store import StateStore
from alert_bot.telegram_alerter import CandidateCard, TelegramAlerter

log = logging.getLogger("force-best")


def _to_card(sc: ScoredCandidate, *, forced: bool = True) -> CandidateCard:
    """Same shape as alert_bot.main._to_card, with a [FORCED] tag on the name."""
    label = "[FORCED] " if forced else ""
    return CandidateCard(
        contract=sc.pair.base_token_address,
        ticker=sc.pair.base_token_symbol or "?",
        name=f"{label}{sc.pair.base_token_name or '?'}",
        score=sc.score,
        score_max=sc.score_max,
        checklist_lines=sc.render_checklist(),
        mcap_usd=sc.pair.market_cap_usd or sc.pair.fdv_usd or 0.0,
        liquidity_usd=sc.pair.liquidity_usd,
        age_hours=sc.pair.age_hours,
        dexscreener_url=sc.pair.dexscreener_url,
        pumpfun_url=f"https://pump.fun/coin/{sc.pair.base_token_address}",
    )


def _score_all(
    pairs: Iterable[Pair],
    rc: RugcheckClient,
) -> list[ScoredCandidate]:
    """Evaluate every pair; skip the ones rugcheck can't return data for."""
    scored: list[ScoredCandidate] = []
    for pair in pairs:
        try:
            rug = rc.check(pair.base_token_address)
        except RugcheckError as exc:
            log.warning(
                "rugcheck failed for $%s (%s): %s",
                pair.base_token_symbol,
                pair.base_token_address,
                exc,
            )
            continue
        narrative = check_narrative(name=pair.base_token_name, symbol=pair.base_token_symbol)
        scored.append(score_candidate(pair, rug, narrative))
    return scored


def _rank_key(sc: ScoredCandidate) -> tuple[int, float, float]:
    """Sort key: highest score, then largest liquidity, then 1h volume."""
    return (sc.score, sc.pair.liquidity_usd, sc.pair.volume_h1_usd)


async def main() -> None:
    cfg = load_runtime_config()
    configure_logging(cfg.log_level)

    ds = DexScreenerClient()
    rc = RugcheckClient()
    store = StateStore(cfg.db_path)
    store.init_schema()

    log.info("Fetching live DexScreener pairs...")
    all_pairs = ds.fetch_solana_pairs()
    filtered = ds.filter_pairs(all_pairs)
    log.info(
        "fetched=%d filter-passing=%d",
        len(all_pairs),
        len(filtered),
    )

    # First pass: only filter-passing pairs.
    candidates = _score_all(filtered, rc)
    fallback_used = False
    if not candidates:
        # No pre-filter survivors right now. Fall back to ALL discovered pairs
        # so we still have something to surface — clearly marked as forced.
        log.warning(
            "No pairs passed the numeric pre-filters. Falling back to scoring "
            "all %d discovered pairs.",
            len(all_pairs),
        )
        candidates = _score_all(all_pairs, rc)
        fallback_used = True

    if not candidates:
        log.error("No candidates produced even from fallback set. Nothing to send.")
        return

    candidates.sort(key=_rank_key, reverse=True)
    best = candidates[0]
    log.info(
        "Best candidate: $%s score=%d/%d liq=$%.0f vol1h=$%.0f age=%.1fh fallback=%s",
        best.pair.base_token_symbol,
        best.score,
        best.score_max,
        best.pair.liquidity_usd,
        best.pair.volume_h1_usd,
        best.pair.age_hours,
        fallback_used,
    )

    # Persist the alert so the button-press flow has something to tie to.
    snapshot = {
        "forced": True,
        "fallback_used": fallback_used,
        "ticker": best.pair.base_token_symbol,
        "score": best.score,
        "score_max": best.score_max,
    }
    store.record_alert(best.pair.base_token_address, best.score, snapshot)

    # Send the card and wait briefly so callbacks can land.
    alerter = TelegramAlerter(
        cfg,
        on_decision=lambda contract, decision: asyncio.to_thread(
            store.record_decision, contract, decision
        ),
    )
    await alerter.start()
    try:
        await alerter.send_candidate_card(_to_card(best, forced=True))
        log.info("Forced candidate card sent. Waiting 60s for button presses...")
        await asyncio.sleep(60)
    finally:
        await alerter.stop()


if __name__ == "__main__":
    asyncio.run(main())
