"""Score a candidate against the Strategy 1 Go/No-Go 4/5 checklist.

The five checks (from strategy_1_graduated_tokens.md step 6):
  1. Rugcheck is clean
  2. Holders are distributed (top-10 < 35%)
  3. Volume is accelerating (5M projection outpacing the hourly average)
  4. Community is alive (socials linked)
  5. Passes narrative check (no IP/brand impersonation)

Pure function — no I/O, no side effects. Easy to unit test, which is the
whole point of pulling the trading rules into a separate module.
"""

from __future__ import annotations

from dataclasses import dataclass

from alert_bot.config import SCORING, ScoringConfig
from alert_bot.dex_screener_client import Pair
from alert_bot.narrative_filter import NarrativeCheck
from alert_bot.rugcheck_client import RugcheckResult


@dataclass(frozen=True)
class CheckOutcome:
    """One row of the 4/5 checklist: did it pass, and what's the human-readable detail."""

    name: str
    passed: bool
    detail: str

    def render(self) -> str:
        icon = "✅" if self.passed else "❌"
        return f"{icon} {self.name}: {self.detail}"


@dataclass(frozen=True)
class ScoredCandidate:
    """End-to-end evaluation result for one pair. Consumed by main.py."""

    pair: Pair
    rugcheck: RugcheckResult
    narrative: NarrativeCheck
    checks: tuple[CheckOutcome, ...]

    @property
    def score(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def score_max(self) -> int:
        return len(self.checks)

    def render_checklist(self) -> list[str]:
        return [c.render() for c in self.checks]

    def meets_alert_threshold(self, cfg: ScoringConfig = SCORING) -> bool:
        return self.score >= cfg.alert_score_threshold


# ---------------------------------------------------------------------------
# Individual check functions. Each returns (passed, detail) so render is uniform.
# Pulled out so unit tests can target each rule in isolation.
# ---------------------------------------------------------------------------

def _check_rugcheck(rc: RugcheckResult, cfg: ScoringConfig) -> CheckOutcome:
    """Item 1: rugcheck overall. Mirrors RugcheckResult.is_clean + score cap."""
    score_ok = rc.score_normalised <= cfg.max_rugcheck_risk_score
    passed = rc.is_clean and score_ok
    if passed:
        detail = f"clean (risk score {rc.score_normalised}/{int(cfg.max_rugcheck_risk_score)})"
    else:
        # Build a tight reason string. The first failing condition wins for the
        # one-liner, but we still pass through danger names if any.
        if rc.rugged:
            detail = "marked rugged by rugcheck"
        elif rc.danger_risks:
            detail = f"danger risks: {', '.join(rc.danger_risks)}"
        elif not rc.mint_authority_disabled:
            detail = "mint authority still enabled"
        elif not rc.freeze_authority_disabled:
            detail = "freeze authority still enabled"
        elif rc.creator_balance > 0:
            detail = f"creator still holds (bal={rc.creator_balance})"
        elif not (rc.lp_locked_pct > 0 or rc.has_pumpfun_amm_market):
            detail = "LP neither locked nor burned"
        elif not score_ok:
            detail = f"risk score {rc.score_normalised} > {int(cfg.max_rugcheck_risk_score)}"
        else:
            detail = "failed (composite)"
    return CheckOutcome(name="Rugcheck", passed=passed, detail=detail)


def _check_holders(rc: RugcheckResult, cfg: ScoringConfig) -> CheckOutcome:
    """Item 2: top-10 holder concentration below threshold."""
    passed = rc.top_10_holder_pct < cfg.max_top10_holder_pct
    detail = f"top10 {rc.top_10_holder_pct:.1f}% (cap {cfg.max_top10_holder_pct:.0f}%)"
    return CheckOutcome(name="Holders distributed", passed=passed, detail=detail)


def _check_volume_acceleration(pair: Pair) -> CheckOutcome:
    """Item 3: 5m USD volume projected to the hour > the hourly average.

    A 5-minute bar covers 1/12th of an hour, so the simple "is the current
    pace above hourly average" test is: m5 * 12 > h1.
    """
    projected_h1 = pair.volume_m5_usd * 12.0
    passed = projected_h1 > pair.volume_h1_usd and pair.volume_m5_usd > 0
    detail = f"5m ${pair.volume_m5_usd:,.0f} * 12 = ${projected_h1:,.0f} vs 1h ${pair.volume_h1_usd:,.0f}"
    return CheckOutcome(name="Volume accelerating", passed=passed, detail=detail)


def _check_socials(pair: Pair) -> CheckOutcome:
    """Item 4: at least one social link present (twitter / telegram / tiktok / website)."""
    has_any = pair.has_socials or len(pair.websites) > 0
    if has_any:
        listed = list(pair.socials) + (["website"] if pair.websites else [])
        detail = f"linked: {', '.join(listed)}"
    else:
        detail = "no socials or website linked"
    return CheckOutcome(name="Socials linked", passed=has_any, detail=detail)


def _check_narrative(nc: NarrativeCheck) -> CheckOutcome:
    """Item 5: narrative/IP filter result."""
    detail = nc.reason_summary if not nc.passed else "no IP/brand match"
    return CheckOutcome(name="Narrative", passed=nc.passed, detail=detail)


def score_candidate(
    pair: Pair,
    rugcheck: RugcheckResult,
    narrative: NarrativeCheck,
    *,
    cfg: ScoringConfig = SCORING,
) -> ScoredCandidate:
    """Compose the 5 checks into a ScoredCandidate.

    Ordering matches strategy_1_graduated_tokens.md step 6 for human readability
    in the Telegram card.
    """
    checks = (
        _check_rugcheck(rugcheck, cfg),
        _check_holders(rugcheck, cfg),
        _check_volume_acceleration(pair),
        _check_socials(pair),
        _check_narrative(narrative),
    )
    return ScoredCandidate(pair=pair, rugcheck=rugcheck, narrative=narrative, checks=checks)
