"""Rugcheck.xyz client: fetch contract safety data, parse into RugcheckResult.

Endpoint: GET https://api.rugcheck.xyz/v1/tokens/{mint}/report
  Returns a dict with the keys we care about:
    - score_normalised  (int; lower = safer; 0-100 scale per their convention)
    - rugged            (bool; explicit rug flag)
    - mintAuthority     (str | null; null means disabled = safe)
    - freezeAuthority   (str | null; null means disabled = safe)
    - creatorBalance    (int)
    - topHolders        (list of {pct, ...}; sort/sum first 10 for concentration)
    - risks             (list of {level, name, description, score})
    - graphInsidersDetected (int; number of insider accounts detected)
    - markets           (list of {marketType, ...}; pump_fun_amm => LP burned)

Public endpoint, no auth required. We cache results in-process keyed by mint —
the strategy says "never check the same contract twice in one session" so a
small dict cache covers that without needing SQLite involvement here.

References:
  https://api.rugcheck.xyz/swagger/index.html
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests

log = logging.getLogger(__name__)

RUGCHECK_BASE_URL = "https://api.rugcheck.xyz/v1"
DEFAULT_TIMEOUT_SECONDS = 15

# Risk levels rugcheck returns on each entry in the `risks` array.
# "danger" is the disqualifying level per the strategy doc ("any red flag = skip").
DANGER_LEVEL = "danger"


@dataclass(frozen=True)
class RugcheckResult:
    """Normalized rugcheck snapshot. Frozen for the same reason as Pair."""

    contract: str
    # rugcheck's normalized 0-100 risk score. Lower is safer.
    score_normalised: int
    # Explicit rug boolean — if true, hard fail regardless of score.
    rugged: bool
    mint_authority_disabled: bool
    freeze_authority_disabled: bool
    # Sum of top-10 holders' pct (each holder's `pct` field is 0-100).
    top_10_holder_pct: float
    # Raw creator wallet balance. We don't need supply here — non-zero usually
    # means the dev still holds bag, and rugcheck flags it as a risk anyway.
    creator_balance: int
    # graphInsidersDetected — flag, not a disqualifier on its own.
    insider_count: int
    # Names of any risks rugcheck flagged at level=danger. Empty = clean.
    danger_risks: tuple[str, ...]
    # Was at least one market a pump.fun AMM? Pump.fun's contract burns LP at
    # graduation, so this is effectively "LP locked" for our purposes.
    has_pumpfun_amm_market: bool
    # Raw lpLockedPct (0-100). Only meaningful if LP is held by a third-party
    # locker; burned LP shows up here as 0 even though it's safer than locked.
    lp_locked_pct: float = 0.0
    # Liquidity reported by rugcheck across all markets. Cross-check vs DexScreener.
    total_market_liquidity_usd: float = 0.0

    @property
    def is_clean(self) -> bool:
        """One-shot 'rugcheck good?' for the scorer's checklist item 1.

        Strategy 1: rugcheck must be "Good", LP locked or burned, mint and
        freeze authorities disabled, creator balance low/sold, no danger flags.
        Insider count is a *note*, not a disqualifier (the strategy doc says
        "or if detected, note the % and watch for sell signal").
        """
        return (
            not self.rugged
            and not self.danger_risks
            and self.mint_authority_disabled
            and self.freeze_authority_disabled
            and self.creator_balance == 0
            and (self.lp_locked_pct > 0.0 or self.has_pumpfun_amm_market)
        )


class RugcheckError(RuntimeError):
    """Raised when rugcheck returns an unrecoverable response."""


def _parse_report(contract: str, raw: dict[str, Any]) -> RugcheckResult:
    """Map a rugcheck /report response into RugcheckResult."""
    risks = raw.get("risks") or []
    danger_names = tuple(
        str(r.get("name", "unknown"))
        for r in risks
        if isinstance(r, dict) and r.get("level") == DANGER_LEVEL
    )

    top_holders = raw.get("topHolders") or []
    # `pct` is already 0-100; just sum the first 10 (rugcheck returns them sorted desc).
    top_10_pct = 0.0
    for entry in top_holders[:10]:
        if isinstance(entry, dict):
            try:
                top_10_pct += float(entry.get("pct") or 0.0)
            except (TypeError, ValueError):
                continue

    markets = raw.get("markets") or []
    has_pumpfun_amm = any(
        isinstance(m, dict) and (m.get("marketType") == "pump_fun_amm")
        for m in markets
    )

    return RugcheckResult(
        contract=contract,
        score_normalised=int(raw.get("score_normalised") or 0),
        rugged=bool(raw.get("rugged")),
        mint_authority_disabled=raw.get("mintAuthority") is None,
        freeze_authority_disabled=raw.get("freezeAuthority") is None,
        top_10_holder_pct=top_10_pct,
        creator_balance=int(raw.get("creatorBalance") or 0),
        insider_count=int(raw.get("graphInsidersDetected") or 0),
        danger_risks=danger_names,
        has_pumpfun_amm_market=has_pumpfun_amm,
        lp_locked_pct=float(raw.get("lpLockedPct") or 0.0),
        total_market_liquidity_usd=float(raw.get("totalMarketLiquidity") or 0.0),
    )


class RugcheckClient:
    """Thin sync wrapper with per-session caching."""

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = 4,
    ) -> None:
        self._session = session or requests.Session()
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts
        # In-process cache for the lifetime of the process. The strategy
        # rule is "never check the same contract twice in one session";
        # SQLite-backed cross-session caching can come later if needed.
        self._cache: dict[str, RugcheckResult] = {}

    def check(self, contract: str) -> RugcheckResult:
        cached = self._cache.get(contract)
        if cached is not None:
            return cached
        url = f"{RUGCHECK_BASE_URL}/tokens/{contract}/report"
        payload = self._get_with_backoff(url)
        result = _parse_report(contract, payload)
        self._cache[contract] = result
        return result

    def _get_with_backoff(self, url: str) -> dict[str, Any]:
        delay = 1.0
        for attempt in range(1, self._max_attempts + 1):
            try:
                resp = self._session.get(
                    url,
                    timeout=self._timeout,
                    headers={"User-Agent": "alert-bot/0.1 (+strategy1)"},
                )
                if resp.status_code == 429:
                    wait = float(resp.headers.get("Retry-After", "5"))
                    log.warning("Rugcheck 429; sleeping %.1fs (attempt %d/%d)", wait, attempt, self._max_attempts)
                    time.sleep(wait + 0.5)
                    continue
                if resp.status_code == 404:
                    # Token not yet indexed by rugcheck. Treat as "we don't know" —
                    # the caller decides if missing data is disqualifying (it is,
                    # per the strategy doc: rugcheck is non-negotiable).
                    raise RugcheckError(f"Rugcheck has no data for {url.split('/')[-2]}")
                if 500 <= resp.status_code < 600:
                    log.warning("Rugcheck %d; retrying in %.1fs (attempt %d/%d)", resp.status_code, delay, attempt, self._max_attempts)
                    time.sleep(delay)
                    delay *= 2
                    continue
                resp.raise_for_status()
                return resp.json()
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == self._max_attempts:
                    raise RugcheckError(f"Rugcheck unreachable after {attempt} attempts: {exc}") from exc
                log.warning("Rugcheck network error (%s); retrying in %.1fs", exc, delay)
                time.sleep(delay)
                delay *= 2
        raise RugcheckError(f"Rugcheck exhausted retries ({self._max_attempts})")


if __name__ == "__main__":
    # Smoke test: hit rugcheck for whichever fresh, filter-passing pair
    # DexScreener returns right now. Demonstrates the full first-hop pipeline.
    from alert_bot.config import configure_logging
    from alert_bot.dex_screener_client import DexScreenerClient, passes_filters

    configure_logging("INFO")
    ds = DexScreenerClient()
    rc = RugcheckClient()
    pairs = ds.fetch_solana_pairs()
    candidates = [p for p in pairs if passes_filters(p)]
    log.info("DexScreener returned %d filter-passing pairs", len(candidates))
    for pair in candidates[:3]:
        try:
            result = rc.check(pair.base_token_address)
        except RugcheckError as exc:
            log.warning("Rugcheck failed for %s: %s", pair.base_token_symbol, exc)
            continue
        log.info(
            "  %s rugcheck: score=%d clean=%s top10=%.1f%% mint_off=%s freeze_off=%s "
            "creator_bal=%d insiders=%d dangers=%s pumpfun_amm=%s lp_locked=%.1f%%",
            pair.base_token_symbol,
            result.score_normalised,
            result.is_clean,
            result.top_10_holder_pct,
            result.mint_authority_disabled,
            result.freeze_authority_disabled,
            result.creator_balance,
            result.insider_count,
            result.danger_risks,
            result.has_pumpfun_amm_market,
            result.lp_locked_pct,
        )
