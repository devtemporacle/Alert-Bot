"""Send a sample candidate card to verify the Telegram alert path end-to-end.

Optional smoke test — only useful if you want to see what an alert looks like
without waiting for the market to produce a real 4/5 candidate. Stops itself
after 60s so the bot disconnects cleanly.

Run it with the bot's main loop NOT running (Telegram allows only one
long-poll connection per token).

Usage (from project root, with venv activated):
    python scripts/send_test_card.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make the project root importable when this file is run directly via
# `python scripts/send_test_card.py` (which only puts scripts/ on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alert_bot.config import configure_logging, load_runtime_config
from alert_bot.telegram_alerter import CandidateCard, TelegramAlerter


async def main() -> None:
    cfg = load_runtime_config()
    configure_logging("INFO")
    alerter = TelegramAlerter(cfg)
    await alerter.start()
    try:
        card = CandidateCard(
            contract="C2U9BWSV9cxCu9cB8zDKKuAE27ZX9UFiFeEZxoTfpump",
            ticker="ICED",
            name="ICED (test card)",
            score=4,
            score_max=5,
            checklist_lines=[
                "✅ Rugcheck: clean (risk score 16/40)",
                "❌ Holders distributed: top10 53.7% (cap 35%)",
                "✅ Volume accelerating: 5m $5,056 * 12 = $60,668 vs 1h $55,427",
                "✅ Socials linked: linked: twitter",
                "✅ Narrative: no IP/brand match",
            ],
            mcap_usd=221_000,
            liquidity_usd=32_000,
            age_hours=4.6,
            dexscreener_url=(
                "https://dexscreener.com/solana/"
                "C2U9BWSV9cxCu9cB8zDKKuAE27ZX9UFiFeEZxoTfpump"
            ),
            pumpfun_url=(
                "https://pump.fun/coin/"
                "C2U9BWSV9cxCu9cB8zDKKuAE27ZX9UFiFeEZxoTfpump"
            ),
        )
        await alerter.send_candidate_card(card)
        print("Card sent. Waiting 60s for you to press a button...")
        await asyncio.sleep(60)
    finally:
        await alerter.stop()


if __name__ == "__main__":
    asyncio.run(main())
