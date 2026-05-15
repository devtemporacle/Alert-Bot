"""Narrative / IP filter — catches what rugcheck can't see.

Strategy 1: rugcheck flags contract risk but is blind to legal/longevity
risk from brand impersonation (the "PHANNY" failure mode — token claimed
affiliation with Phantom Wallet, hit a cease-and-desist, died).

This module does keyword + regex matching only. v1.1 may add an LLM check
behind a config flag if false negatives become a problem.

Returns a NarrativeCheck dataclass so the scorer/alert card can show *why*
something was flagged, not just a yes/no.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from alert_bot.config import BLOCKLIST, NarrativeBlocklist

# Unicode ranges covering CJK Unified Ideographs + extensions + Japanese kana
# + Korean Hangul. Any one match in name/symbol is enough to flag.
# Using \u escapes (not literal CJK glyphs) so the source stays ASCII-safe.
_CJK_RE = re.compile(
    "["
    "一-鿿"  # CJK Unified Ideographs
    "㐀-䶿"  # CJK Extension A
    "　-〿"  # CJK Symbols and Punctuation
    "぀-ゟ"  # Hiragana
    "゠-ヿ"  # Katakana
    "가-힯"  # Hangul Syllables
    "]"
)


@dataclass(frozen=True)
class NarrativeCheck:
    """Outcome of the narrative filter for one token."""

    passed: bool
    reasons: tuple[str, ...]  # empty if passed; one or more short reason codes if not

    @property
    def reason_summary(self) -> str:
        return ", ".join(self.reasons) if self.reasons else "clean"


def _compile_patterns(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


def check_narrative(
    name: str,
    symbol: str,
    description: str = "",
    *,
    blocklist: NarrativeBlocklist = BLOCKLIST,
) -> NarrativeCheck:
    """Run brand + impersonation + CJK checks on a token's text.

    All matching is case-insensitive. Brand keywords match as substrings
    against the combined (name + symbol + description) haystack — so
    "Disney" hits "DisneyWorld" or "official disney". Description is
    optional; some Dex Screener pairs come without one.
    """
    haystack_parts = [name or "", symbol or "", description or ""]
    haystack = " ".join(haystack_parts)
    haystack_lower = haystack.lower()

    reasons: list[str] = []

    # 1. CJK detection on name/symbol only (an English description containing
    # one stray kanji shouldn't disqualify; the rule is "can't read the community").
    if blocklist.flag_cjk_text:
        if _CJK_RE.search(name or "") or _CJK_RE.search(symbol or ""):
            reasons.append("cjk-text")

    # 2. Brand keyword substring match.
    for brand in blocklist.brand_keywords:
        if brand and brand.lower() in haystack_lower:
            reasons.append(f"brand:{brand}")
            # Don't break — a token can hit multiple brands; useful to surface all.

    # 3. Impersonation regex patterns.
    for pattern in _compile_patterns(blocklist.impersonation_patterns):
        m = pattern.search(haystack)
        if m:
            reasons.append(f"impersonation:{m.group(0).strip().lower()}")

    return NarrativeCheck(passed=not reasons, reasons=tuple(reasons))


if __name__ == "__main__":
    # Quick demonstration with a handful of plausible / known-bad names.
    cases = [
        ("John Pork", "PORK", "viral tiktok pig man"),
        ("Phanny", "PHANNY", "the official phantom wallet token"),
        ("Real Pikachu", "RPIKA", "an unofficial pokemon meme"),
        ("BasedDoge", "BDOGE", "doge but based"),
        ("中国币", "CHN", ""),   # "Chinese coin" in Chinese
        ("Trump 2028", "TRUMP", "official trump campaign token"),
    ]
    for name, sym, desc in cases:
        r = check_narrative(name, sym, desc)
        print(f"{name!r:25} symbol={sym!r:10} -> passed={r.passed!s:<5} reasons={r.reasons}")
