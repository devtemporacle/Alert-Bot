"""Central configuration: env vars, filter thresholds, blocklist.

All tunable knobs for the bot live here. The rest of the codebase should
import constants from this module rather than reading os.environ directly.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Resolve the project root (two levels up from this file's directory's parent)
# so the .env / SQLite file paths work no matter where the script is launched.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# load_dotenv is a no-op if the file is missing; that's fine for CI/tests.
load_dotenv(PROJECT_ROOT / ".env")


def _env_str(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(
            f"Required environment variable {name!r} is missing. "
            f"Copy .env.example to .env and fill it in."
        )
    return value or ""


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Env var {name}={raw!r} is not a valid integer") from exc


@dataclass(frozen=True)
class FilterThresholds:
    """Numeric pre-filters from strategy_1_graduated_tokens.md (confirmed).

    Frozen because these are policy, not runtime state. Override per-test by
    constructing a new instance, not by mutating fields.
    """

    min_liquidity_usd: float = 15_000.0
    max_pair_age_hours: float = 6.0
    min_pair_age_hours: float = 0.0
    min_txns_1h: int = 200
    min_volume_1h_usd: float = 20_000.0
    min_txns_5m: int = 50
    min_buys_5m: int = 25
    min_volume_5m_usd: float = 5_000.0


@dataclass(frozen=True)
class ScoringConfig:
    """Knobs for the 4/5 Go/No-Go scorer."""

    # Alert if score >= this. Spec calls for 4/5.
    alert_score_threshold: int = 4
    # Top-10 holder concentration ceiling (35% per the strategy doc).
    max_top10_holder_pct: float = 35.0
    # Rugcheck normalized risk score must be <= this to be considered "clean".
    # (rugcheck.xyz returns a numeric score where lower is safer; exact scale
    # is confirmed in rugcheck_client.py once we lock the schema.)
    max_rugcheck_risk_score: float = 40.0
    # Volume "accelerating" = 5m USD volume * (60/5) > 1H USD volume.
    # i.e. the current 5-minute pace projects above the trailing hour average.
    # No extra knob needed — the scorer computes this directly.


@dataclass(frozen=True)
class RuntimeConfig:
    """Process-level config that's safe to log on startup."""

    telegram_bot_token: str
    telegram_chat_id: int
    db_path: Path
    poll_interval_seconds: int = 60
    # Don't re-alert the same contract within this window.
    dedup_window_hours: int = 24
    # Daily "bot still alive" ping. 24h interval; first ping aligns to midnight local.
    health_ping_interval_hours: int = 24
    log_level: str = "INFO"

    def redacted(self) -> dict[str, object]:
        """Dict for safe logging — never leak the bot token."""
        token = self.telegram_bot_token
        masked = f"{token[:6]}…{token[-4:]}" if len(token) > 12 else "***"
        return {
            "telegram_bot_token": masked,
            "telegram_chat_id": self.telegram_chat_id,
            "db_path": str(self.db_path),
            "poll_interval_seconds": self.poll_interval_seconds,
            "dedup_window_hours": self.dedup_window_hours,
            "log_level": self.log_level,
        }


_BRAND_KEYWORDS: tuple[str, ...] = (
    # Big tech (NOTE: tiktok/twitter/instagram/youtube/facebook deliberately
    # excluded — they're the platforms hosting legitimate viral memes and
    # appear naturally in real token descriptions per strategy_1 step 5.
    # Impersonation of those companies still gets caught via the
    # "official X" / "real X" regex patterns below.)
    "apple", "google", "microsoft", "amazon", "tesla", "spacex", "nvidia",
    "intel",
    # Crypto brands & infra
    "phantom", "metamask", "coinbase", "binance", "kraken", "opensea",
    "uniswap", "pumpfun", "pump.fun",
    # Entertainment & IP
    "disney", "marvel", "pokemon", "pokémon", "nintendo", "sony",
    "playstation", "xbox", "netflix", "spotify", "hbo", "pixar", "warner",
    "universal", "dc comics",
    # Sports / fashion / autos
    "nike", "adidas", "puma", "gucci", "louis vuitton", "ferrari",
    "lamborghini", "porsche", "bmw", "mercedes", "rolex",
    # Food / retail
    "mcdonald", "starbucks", "kfc", "coca-cola", "coca cola", "pepsi",
    "walmart", "target",
    # Public figures (high impersonation likelihood)
    "trump", "biden", "elon musk", "bezos", "zuckerberg", "putin", "xi jinping",
    "kim jong", "taylor swift", "kanye", "drake",
)

_IMPERSONATION_PATTERNS: tuple[str, ...] = (
    r"\bofficial\s+\w+",
    r"\breal\s+\w+",
    r"\bverified\s+\w+",
    r"\bowned\s+by\s+\w+",
    r"\bbacked\s+by\s+\w+",
    r"\bpartnered\s+with\s+\w+",
)


@dataclass(frozen=True)
class NarrativeBlocklist:
    """Brand/IP keywords and impersonation patterns for narrative_filter.py.

    Matching is case-insensitive against token name + symbol + description.
    Substring match for brands; regex for impersonation phrases.
    """

    brand_keywords: tuple[str, ...] = _BRAND_KEYWORDS
    impersonation_patterns: tuple[str, ...] = _IMPERSONATION_PATTERNS
    # Strategy 1: "Chinese-text tokens — can't read the community — skip."
    # We detect any CJK character in name/symbol and flag.
    flag_cjk_text: bool = True


def load_runtime_config() -> RuntimeConfig:
    """Read environment variables and assemble a RuntimeConfig.

    Raises RuntimeError on missing required env vars so failures happen at
    startup, not deep inside the poll loop.
    """
    token = _env_str("TELEGRAM_BOT_TOKEN", required=True)
    chat_id_raw = _env_str("TELEGRAM_CHAT_ID", required=True)
    try:
        chat_id = int(chat_id_raw)
    except ValueError as exc:
        raise RuntimeError(
            f"TELEGRAM_CHAT_ID must be an integer, got {chat_id_raw!r}"
        ) from exc

    db_path_raw = _env_str("ALERT_BOT_DB_PATH", default="alert_bot.db")
    db_path = Path(db_path_raw)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path

    return RuntimeConfig(
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        db_path=db_path,
        poll_interval_seconds=_env_int("POLL_INTERVAL_SECONDS", 60),
        log_level=_env_str("LOG_LEVEL", default="INFO"),
    )


# Module-level singletons. These are policy/constants; loading them once is fine.
FILTERS = FilterThresholds()
SCORING = ScoringConfig()
BLOCKLIST = NarrativeBlocklist()


def configure_logging(level: str = "INFO") -> None:
    """Set up a single, consistent log format for the whole process."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


if __name__ == "__main__":
    # Smoke-test: `python -m alert_bot.config` prints the loaded config with
    # the bot token redacted so you can confirm .env is wired up correctly.
    cfg = load_runtime_config()
    configure_logging(cfg.log_level)
    log = logging.getLogger("alert_bot.config")
    log.info("Runtime config loaded: %s", cfg.redacted())
    log.info("Filter thresholds: %s", FILTERS)
    log.info("Scoring config: %s", SCORING)
    log.info("Project root: %s", PROJECT_ROOT)
