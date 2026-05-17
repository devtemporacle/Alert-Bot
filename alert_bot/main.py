"""Main loop: poll DexScreener, score, alert, log.

Single-process, single-thread (asyncio). The hot path runs:
    every POLL_INTERVAL seconds:
        1. fetch + filter pairs from DexScreener
        2. for each pair not alerted within 24h:
            - rugcheck
            - narrative check
            - score
            - record candidate snapshot
            - if score >= threshold: send Telegram alert + record
    every 24h:
        send a health ping to Telegram

DexScreener / Rugcheck are sync (`requests`). We wrap their blocking calls
in `asyncio.to_thread` so they don't stall the Telegram callback handler
running in the same event loop. Two HTTP libraries (one sync, one async)
would be more complexity than this bot warrants.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from alert_bot.config import (
    FILTERS,
    SCORING,
    configure_logging,
    load_runtime_config,
)
from alert_bot.dex_screener_client import DexScreenerClient, Pair
from alert_bot.narrative_filter import check_narrative
from alert_bot.post_spike_filter import check_post_spike
from alert_bot.rugcheck_client import RugcheckClient, RugcheckError
from alert_bot.scorer import ScoredCandidate, score_candidate
from alert_bot.state_store import StateStore
from alert_bot.telegram_alerter import (
    CandidateCard,
    Decision,
    PostSpikeCard,
    TelegramAlerter,
)

log = logging.getLogger(__name__)

# Health ping cadence in seconds (24h). Spec calls for a daily ping.
HEALTH_PING_INTERVAL_SECONDS = 24 * 60 * 60


def _snapshot_for_log(sc: ScoredCandidate) -> dict[str, Any]:
    """Serializable snapshot of an evaluation — stored in candidates_seen / alerts_sent."""
    return {
        "ticker": sc.pair.base_token_symbol,
        "name": sc.pair.base_token_name,
        "dex": sc.pair.dex_id,
        "pair_address": sc.pair.pair_address,
        "score": sc.score,
        "score_max": sc.score_max,
        "mcap_usd": sc.pair.market_cap_usd,
        "liquidity_usd": sc.pair.liquidity_usd,
        "age_hours": sc.pair.age_hours,
        "volume_h1_usd": sc.pair.volume_h1_usd,
        "volume_m5_usd": sc.pair.volume_m5_usd,
        "rugcheck_score": sc.rugcheck.score_normalised,
        "top_10_holder_pct": sc.rugcheck.top_10_holder_pct,
        "insider_count": sc.rugcheck.insider_count,
        "narrative_reasons": list(sc.narrative.reasons),
        "checklist": sc.render_checklist(),
    }


def _pumpfun_url(pair: Pair) -> str:
    """Pump.fun's coin page is keyed by base token address."""
    return f"https://pump.fun/coin/{pair.base_token_address}"


def _to_card(sc: ScoredCandidate) -> CandidateCard:
    return CandidateCard(
        contract=sc.pair.base_token_address,
        ticker=sc.pair.base_token_symbol or "?",
        name=sc.pair.base_token_name or "?",
        score=sc.score,
        score_max=sc.score_max,
        checklist_lines=sc.render_checklist(),
        mcap_usd=sc.pair.market_cap_usd or sc.pair.fdv_usd or 0.0,
        liquidity_usd=sc.pair.liquidity_usd,
        age_hours=sc.pair.age_hours,
        dexscreener_url=sc.pair.dexscreener_url,
        pumpfun_url=_pumpfun_url(sc.pair),
    )


def _to_post_spike_card(pair: Pair, reason: str) -> PostSpikeCard:
    return PostSpikeCard(
        contract=pair.base_token_address,
        ticker=pair.base_token_symbol or "?",
        name=pair.base_token_name or "?",
        mcap_usd=pair.market_cap_usd or pair.fdv_usd or 0.0,
        liquidity_usd=pair.liquidity_usd,
        age_hours=pair.age_hours,
        reason=reason,
        dexscreener_url=pair.dexscreener_url,
        pumpfun_url=_pumpfun_url(pair),
    )


class AlertBot:
    """Top-level service: owns the loop, the clients, and the state store."""

    def __init__(self) -> None:
        self.cfg = load_runtime_config()
        configure_logging(self.cfg.log_level)
        self.store = StateStore(self.cfg.db_path)
        self.store.init_schema()
        self.ds = DexScreenerClient()
        self.rc = RugcheckClient()
        self.alerter = TelegramAlerter(self.cfg, on_decision=self._on_decision)
        self._stop = asyncio.Event()

    # --- callbacks from Telegram --------------------------------------

    async def _on_decision(self, contract: str, decision: Decision) -> None:
        # Write to state store on a worker thread — sqlite3 is sync.
        await asyncio.to_thread(self.store.record_decision, contract, decision)
        log.info("Recorded decision=%s for contract=%s", decision, contract)

    # --- main poll loop ------------------------------------------------

    async def _evaluate_pair(self, pair: Pair) -> ScoredCandidate | None:
        """Run rugcheck + narrative + score for one pair. Returns None on rugcheck failure."""
        try:
            rugcheck = await asyncio.to_thread(self.rc.check, pair.base_token_address)
        except RugcheckError as exc:
            log.warning("Rugcheck failed for %s (%s): %s", pair.base_token_symbol, pair.base_token_address, exc)
            return None
        narrative = check_narrative(
            name=pair.base_token_name,
            symbol=pair.base_token_symbol,
            description="",
        )
        return score_candidate(pair, rugcheck, narrative)

    async def _process_one_pair(self, pair: Pair) -> None:
        # Skip if we alerted on this contract recently. Cheap query, do it first.
        already = await asyncio.to_thread(
            self.store.alerted_within, pair.base_token_address, self.cfg.dedup_window_hours
        )
        if already:
            log.info(
                "Skip $%s — already alerted within last %dh (dedup)",
                pair.base_token_symbol,
                self.cfg.dedup_window_hours,
            )
            return

        # Post-spike pre-empt: if the price just dumped, flag as chart-review
        # and skip normal scoring (per strategy: "the chart already ran").
        # Runs before rugcheck so we don't burn an API call on a disqualified pair.
        post_spike = check_post_spike(pair)
        if post_spike.is_post_spike:
            log.info(
                "Post-spike $%s — %s",
                pair.base_token_symbol,
                post_spike.reason,
            )
            snapshot = {
                "post_spike": True,
                "reason": post_spike.reason,
                "price_change_m5_pct": post_spike.price_change_m5_pct,
                "ticker": pair.base_token_symbol,
                "mcap_usd": pair.market_cap_usd,
                "liquidity_usd": pair.liquidity_usd,
                "age_hours": pair.age_hours,
            }
            await asyncio.to_thread(
                self.store.upsert_candidate_seen,
                pair.base_token_address,
                0,  # not a 4/5 score — it was pre-empted
                snapshot,
            )
            try:
                await self.alerter.send_post_spike_alert(
                    _to_post_spike_card(pair, post_spike.reason)
                )
            except Exception:  # noqa: BLE001
                log.exception("Failed to send post-spike alert for $%s", pair.base_token_symbol)
                return
            # Record AFTER successful send (same ordering as candidate alerts).
            await asyncio.to_thread(
                self.store.record_alert, pair.base_token_address, 0, snapshot
            )
            return

        scored = await self._evaluate_pair(pair)
        if scored is None:
            return

        snapshot = _snapshot_for_log(scored)
        await asyncio.to_thread(
            self.store.upsert_candidate_seen,
            pair.base_token_address,
            scored.score,
            snapshot,
        )

        if not scored.meets_alert_threshold():
            log.info(
                "Skip $%s score=%d/%d (below threshold %d)",
                pair.base_token_symbol,
                scored.score,
                scored.score_max,
                SCORING.alert_score_threshold,
            )
            return

        # Order matters: send first, record on success only. If the send fails
        # we don't want to mark this contract as "alerted" and dedup-skip it
        # for 24h — we'd silently drop a real candidate.
        try:
            await self.alerter.send_candidate_card(_to_card(scored))
        except Exception:  # noqa: BLE001
            log.exception("Failed to send Telegram alert for $%s", pair.base_token_symbol)
            return
        await asyncio.to_thread(
            self.store.record_alert, pair.base_token_address, scored.score, snapshot
        )

    async def _poll_once(self) -> None:
        try:
            pairs = await asyncio.to_thread(self.ds.fetch_solana_pairs)
        except Exception:  # noqa: BLE001 — fetch can fail in many ways; log and skip the cycle
            log.exception("DexScreener fetch failed; skipping this cycle")
            return
        filtered = self.ds.filter_pairs(pairs)
        log.info(
            "Cycle: fetched=%d filtered=%d (thresholds=%s)",
            len(pairs),
            len(filtered),
            FILTERS,
        )
        for pair in filtered:
            if self._stop.is_set():
                return
            await self._process_one_pair(pair)

    async def _poll_loop(self) -> None:
        log.info("Poll loop starting (interval=%ds)", self.cfg.poll_interval_seconds)
        while not self._stop.is_set():
            try:
                await self._poll_once()
            except Exception:  # noqa: BLE001 — keep the loop alive at all costs
                log.exception("Unhandled error in poll cycle")
            # Wait with cancellation: stop event interrupts the sleep early.
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.cfg.poll_interval_seconds)
            except asyncio.TimeoutError:
                pass
        log.info("Poll loop exiting")

    async def _health_loop(self) -> None:
        # First ping after the interval, not immediately — gives the user a
        # silent grace window when starting/restarting the bot.
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=HEALTH_PING_INTERVAL_SECONDS)
                return  # stop was set
            except asyncio.TimeoutError:
                pass
            counts = await asyncio.to_thread(self.store.counts)
            try:
                await self.alerter.send_text(
                    f"✅ Bot alive. "
                    f"Candidates seen: {counts['candidates_seen']}, "
                    f"alerts sent: {counts['alerts_sent']}, "
                    f"decisions logged: {counts['decisions']}"
                )
            except Exception:  # noqa: BLE001
                log.exception("Health ping failed")

    # --- lifecycle -----------------------------------------------------

    async def run(self) -> None:
        await self.alerter.start()
        # Announce startup so the user knows a fresh process is live.
        try:
            await self.alerter.send_text("🚀 Alert bot started (Strategy 1).")
        except Exception:  # noqa: BLE001
            log.warning("Startup ping failed; continuing anyway")

        self._install_signal_handlers()
        await asyncio.gather(self._poll_loop(), self._health_loop())
        await self.alerter.stop()
        log.info("Shutdown complete")

    def _install_signal_handlers(self) -> None:
        """Wire SIGINT / SIGTERM to the stop event for clean shutdown.

        add_signal_handler isn't supported on Windows. On Windows, asyncio
        already maps Ctrl+C to KeyboardInterrupt which propagates out of
        asyncio.run(), so we just skip the handler install there and rely
        on the KeyboardInterrupt path in main().
        """
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._stop.set)
            except (NotImplementedError, RuntimeError):
                # Windows hits NotImplementedError; some test envs hit RuntimeError.
                pass


async def _async_main() -> None:
    bot = AlertBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        # Windows path: Ctrl+C raises here. Set stop and let the gather unwind.
        log.info("KeyboardInterrupt — shutting down")
        bot._stop.set()


def main() -> None:
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        # asyncio.run re-raises KeyboardInterrupt after cleanup on some Pythons.
        pass


if __name__ == "__main__":
    main()
