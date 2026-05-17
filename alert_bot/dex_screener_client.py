"""Dex Screener client: fetch Solana pairs and apply numeric pre-filters.

Discovery strategy (v1):
  GET https://api.dexscreener.com/latest/dex/search?q=SOL
    -> response.pairs[]  (an array of Pair-shaped JSON objects across chains)
    -> filter to chainId == "solana" and dexId in {pumpfun, pumpswap, raydium}
    -> map to Pair dataclass
    -> apply numeric thresholds from FilterThresholds

Public endpoint, no auth required, rate limit ~300 req/min (per their docs).
We poll every 60s with a single request, so we're nowhere near the limit, but
we still handle 429s gracefully because shared IPs and transient blips happen.

References:
  https://docs.dexscreener.com/api/reference
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

from alert_bot.config import FILTERS, FilterThresholds

log = logging.getLogger(__name__)

DEXSCREENER_SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"
DEFAULT_TIMEOUT_SECONDS = 15

# Strategy 1 explicitly targets *graduated* Pump.fun tokens. Pre-graduation
# pairs are tagged dexId="pumpfun" and have liquidity.usd=0 (bonding curve,
# no LP yet); post-graduation they migrate to "pumpswap" (current launchpad
# default) or "raydium" (legacy). So we restrict to those two.
ALLOWED_DEX_IDS: frozenset[str] = frozenset({"pumpswap", "raydium"})

# Discovery: Dex Screener has no public "trending pairs" endpoint, so we
# search for a handful of meme-relevant terms each cycle and union the
# results. This biases toward pairs already noticed by other searchers,
# which is fine for v1 — the numeric filters do the heavy lifting.
DEFAULT_QUERIES: tuple[str, ...] = (
    "SOL",
    "USDC",
    "pump",
    "pumpswap",
    "raydium",
    "meme",
)


@dataclass(frozen=True)
class Pair:
    """A normalized Dex Screener pair. Frozen so callers can't mutate state."""

    chain_id: str
    dex_id: str
    pair_address: str
    base_token_address: str
    base_token_symbol: str
    base_token_name: str
    price_usd: float | None
    liquidity_usd: float
    fdv_usd: float | None
    market_cap_usd: float | None
    volume_h1_usd: float
    volume_m5_usd: float
    txns_h1: int
    txns_m5: int
    buys_m5: int
    pair_created_at_ms: int
    socials: tuple[str, ...]
    websites: tuple[str, ...]
    dexscreener_url: str
    # Percent change over the last 5 minutes / 1 hour, as reported by
    # Dex Screener. Used by the post-spike filter. Defaults to 0.0 so older
    # callers/tests that don't populate them stay valid.
    price_change_m5_pct: float = 0.0
    price_change_h1_pct: float = 0.0

    @property
    def age_hours(self) -> float:
        """Pair age in hours from now (UTC), using local clock.

        Dex Screener returns pairCreatedAt in unix ms. time.time() is also
        unix seconds, so the math is straightforward.
        """
        now_ms = time.time() * 1000.0
        return max(0.0, (now_ms - self.pair_created_at_ms) / 3_600_000.0)

    @property
    def has_socials(self) -> bool:
        return len(self.socials) > 0


class DexScreenerError(RuntimeError):
    """Raised when Dex Screener returns an unrecoverable response."""


def _get_number(d: dict[str, Any], key: str, default: float = 0.0) -> float:
    """Tolerant float coercion — Dex Screener occasionally returns nulls."""
    v = d.get(key)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _get_int(d: dict[str, Any], key: str, default: int = 0) -> int:
    v = d.get(key)
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _parse_pair(raw: dict[str, Any]) -> Pair | None:
    """Map one raw Dex Screener pair object into our Pair dataclass.

    Returns None if the JSON is missing fields we treat as mandatory
    (chainId, dexId, baseToken.address, pairCreatedAt). Soft fields default
    to 0/None.
    """
    chain_id = raw.get("chainId")
    dex_id = raw.get("dexId")
    base_token = raw.get("baseToken") or {}
    base_addr = base_token.get("address")
    pair_address = raw.get("pairAddress")
    pair_created_at = raw.get("pairCreatedAt")

    if not chain_id or not dex_id or not base_addr or not pair_address or pair_created_at is None:
        return None

    liquidity = raw.get("liquidity") or {}
    volume = raw.get("volume") or {}
    txns = raw.get("txns") or {}
    txns_h1_obj = txns.get("h1") or {}
    txns_m5_obj = txns.get("m5") or {}
    price_change = raw.get("priceChange") or {}
    info = raw.get("info") or {}

    socials_raw = info.get("socials") or []
    # Each social is {"type": "twitter", "url": "..."} — keep just the type
    # for the "has socials" check; the URL isn't needed in v1.
    socials = tuple(
        s.get("type", "")
        for s in socials_raw
        if isinstance(s, dict) and s.get("type")
    )

    websites_raw = info.get("websites") or []
    websites = tuple(
        w.get("url", "")
        for w in websites_raw
        if isinstance(w, dict) and w.get("url")
    )

    return Pair(
        chain_id=str(chain_id),
        dex_id=str(dex_id),
        pair_address=str(pair_address),
        base_token_address=str(base_addr),
        base_token_symbol=str(base_token.get("symbol") or ""),
        base_token_name=str(base_token.get("name") or ""),
        price_usd=_get_number(raw, "priceUsd", default=0.0) or None,
        liquidity_usd=_get_number(liquidity, "usd"),
        fdv_usd=_get_number(raw, "fdv") or None,
        market_cap_usd=_get_number(raw, "marketCap") or None,
        volume_h1_usd=_get_number(volume, "h1"),
        volume_m5_usd=_get_number(volume, "m5"),
        txns_h1=_get_int(txns_h1_obj, "buys") + _get_int(txns_h1_obj, "sells"),
        txns_m5=_get_int(txns_m5_obj, "buys") + _get_int(txns_m5_obj, "sells"),
        buys_m5=_get_int(txns_m5_obj, "buys"),
        pair_created_at_ms=int(pair_created_at),
        socials=socials,
        websites=websites,
        dexscreener_url=str(raw.get("url") or f"https://dexscreener.com/{chain_id}/{pair_address}"),
        price_change_m5_pct=_get_number(price_change, "m5"),
        price_change_h1_pct=_get_number(price_change, "h1"),
    )


def passes_filters(pair: Pair, thresholds: FilterThresholds = FILTERS) -> bool:
    """Strategy 1 numeric pre-filters. All conditions must hold."""
    age = pair.age_hours
    # Use market_cap_usd when available; fall back to fdv_usd (which is
    # essentially the same for tokens with no vesting/lockups). 0 means
    # the upstream returned no data — treat that as "unknown, don't filter".
    mcap = pair.market_cap_usd or pair.fdv_usd or 0.0
    mcap_ok = (
        thresholds.max_market_cap_usd <= 0.0
        or mcap <= 0.0  # unknown MCAP — skip the check rather than block
        or mcap <= thresholds.max_market_cap_usd
    )
    return (
        pair.chain_id == "solana"
        and pair.dex_id in ALLOWED_DEX_IDS
        and pair.liquidity_usd >= thresholds.min_liquidity_usd
        and thresholds.min_pair_age_hours <= age <= thresholds.max_pair_age_hours
        and pair.txns_h1 >= thresholds.min_txns_1h
        and pair.volume_h1_usd >= thresholds.min_volume_1h_usd
        and pair.txns_m5 >= thresholds.min_txns_5m
        and pair.buys_m5 >= thresholds.min_buys_5m
        and pair.volume_m5_usd >= thresholds.min_volume_5m_usd
        and mcap_ok
    )


class DexScreenerClient:
    """Thin sync HTTP wrapper. Sync is fine — we make one call per poll cycle."""

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = 4,
    ) -> None:
        # A single Session reuses the underlying TCP connection — small win,
        # but it costs nothing and matches what production clients do.
        self._session = session or requests.Session()
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts

    def fetch_solana_pairs(
        self,
        queries: tuple[str, ...] = DEFAULT_QUERIES,
    ) -> list[Pair]:
        """Hit the search endpoint for each query, union results, dedupe by pair address.

        Does NOT apply numeric filters — that's filter_pairs(). Separating them
        means the caller can log "fetched X, filtered to Y" for observability.
        """
        # Dedupe by pair_address — different queries return overlapping results.
        # First write wins; later identical entries are equivalent anyway.
        deduped: dict[str, Pair] = {}
        for q in queries:
            payload = self._get_with_backoff({"q": q})
            raw_pairs = payload.get("pairs") or []
            for raw in raw_pairs:
                if not isinstance(raw, dict):
                    continue
                pair = _parse_pair(raw)
                if pair is None:
                    continue
                if pair.chain_id != "solana" or pair.dex_id not in ALLOWED_DEX_IDS:
                    continue
                deduped.setdefault(pair.pair_address, pair)
        log.info(
            "Fetched %d unique Solana pairs on allowed DEXes across %d queries",
            len(deduped),
            len(queries),
        )
        return list(deduped.values())

    @staticmethod
    def filter_pairs(pairs: list[Pair], thresholds: FilterThresholds = FILTERS) -> list[Pair]:
        return [p for p in pairs if passes_filters(p, thresholds)]

    def _get_with_backoff(self, params: dict[str, str]) -> dict[str, Any]:
        """GET with exponential backoff. Respects 429 Retry-After when given.

        Why custom instead of urllib3 Retry: we want fine-grained logging at
        each retry and we want to honor Retry-After in seconds (not just
        retry blindly). Easy to swap to urllib3 Retry later if needed.
        """
        delay = 1.0
        for attempt in range(1, self._max_attempts + 1):
            try:
                resp = self._session.get(
                    DEXSCREENER_SEARCH_URL,
                    params=params,
                    timeout=self._timeout,
                    headers={"User-Agent": "alert-bot/0.1 (+strategy1)"},
                )
                if resp.status_code == 429:
                    wait = float(resp.headers.get("Retry-After", "5"))
                    log.warning("DexScreener 429; sleeping %.1fs (attempt %d/%d)", wait, attempt, self._max_attempts)
                    time.sleep(wait + 0.5)
                    continue
                if 500 <= resp.status_code < 600:
                    log.warning("DexScreener %d; retrying in %.1fs (attempt %d/%d)", resp.status_code, delay, attempt, self._max_attempts)
                    time.sleep(delay)
                    delay *= 2
                    continue
                resp.raise_for_status()
                return resp.json()
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == self._max_attempts:
                    raise DexScreenerError(f"DexScreener unreachable after {attempt} attempts: {exc}") from exc
                log.warning("DexScreener network error (%s); retrying in %.1fs", exc, delay)
                time.sleep(delay)
                delay *= 2
        raise DexScreenerError(f"DexScreener exhausted retries ({self._max_attempts})")


if __name__ == "__main__":
    # Smoke test: fetch live data, show how many pairs pass each layer.
    # Doesn't require .env (no auth needed for Dex Screener).
    from alert_bot.config import configure_logging

    configure_logging("INFO")
    client = DexScreenerClient()
    pairs = client.fetch_solana_pairs()
    filtered = client.filter_pairs(pairs)
    log.info("Fetched %d Solana pairs; %d pass numeric filters", len(pairs), len(filtered))
    for p in filtered[:10]:
        log.info(
            "  $%s (%s) liq=$%.0f age=%.1fh vol1h=$%.0f txns1h=%d vol5m=$%.0f buys5m=%d",
            p.base_token_symbol,
            p.dex_id,
            p.liquidity_usd,
            p.age_hours,
            p.volume_h1_usd,
            p.txns_h1,
            p.volume_m5_usd,
            p.buys_m5,
        )
