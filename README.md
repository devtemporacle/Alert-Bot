# Alert Bot

A Python alert bot that watches Solana Pump.fun graduated tokens on Dex Screener,
runs each candidate through Rugcheck and a brand/impersonation filter, scores it
against a 4/5 Go/No-Go checklist, and pings Telegram with a candidate card so I
can make the trade call manually.

**The bot does not execute trades.** It surfaces candidates; every entry, exit,
and pass is a human decision.

The strategy this automates lives in
[`strategy_1_graduated_tokens.md`](strategy_1_graduated_tokens.md); the
architecture spec it implements is in
[`strategy_3_alert_bot.md`](strategy_3_alert_bot.md).

---

## Honest disclaimers

- This is a tooling project for a personal trading strategy. It is not financial
  advice and the strategy is not validated at scale.
- The bot does not execute trades. It surfaces candidates. The user is
  responsible for every decision.
- Cryptocurrency trading, especially meme coins, has a high probability of
  total loss. This bot enforces discipline; it does not guarantee profit.

---

## What this project demonstrates

- **System design under real constraints.** Free-tier APIs only (Dex Screener,
  Rugcheck, Telegram Bot API), no paid services, runs on $0/month
  infrastructure.
- **Defensive integration with messy external data.** Tolerant JSON parsing,
  exponential backoff with `Retry-After` handling, per-process and per-session
  caching to stay well under rate limits.
- **Pure-function trading rules.** The scoring logic is isolated in `scorer.py`
  so it can be unit-tested without any HTTP traffic — 23 tests cover the 4/5
  checklist and each individual failure mode.
- **Honest scope management.** A trade-execution version was deliberately
  deferred until the alert bot generates enough decision data (30+ trades) to
  show whether the strategy is +EV. The SQLite trade log is the validation
  dataset.

---

## How the pipeline works

```
DexScreener API ──┐
Rugcheck API ─────┼─► Pre-filters ─► Score (4/5 Go/No-Go) ─► Telegram alert ─► Manual decision ─► SQLite
Narrative filter ─┘
```

1. **Discover.** Every 60s, query Dex Screener for `SOL`, `USDC`, `pump`,
   `pumpswap`, `raydium`, `meme`. Union the results, dedupe by pair address,
   keep only Solana pairs on `pumpswap` / `raydium` (the post-graduation venues
   for Pump.fun tokens).
2. **Pre-filter** by Strategy 1's numeric thresholds: liquidity ≥ $15K, pair
   age 0–6h, 1H txns ≥ 200, 1H vol ≥ $20K, 5M txns ≥ 50, 5M buys ≥ 25,
   5M vol ≥ $5K, **MCAP ≤ $80K** (biases toward freshly-graduated tokens
   before they've already pumped; tune via `FILTERS.max_market_cap_usd`).
3. **Rugcheck** each surviving contract via `rugcheck.xyz/v1/tokens/{mint}/report`.
   Parse mint/freeze authority state, top-10 holder concentration, LP
   protection (locked or burned), insider count, danger risks.
4. **Narrative filter:** substring match against a brand/IP blocklist plus
   "official X / real X / verified X" regex patterns, plus CJK-text detection.
   Catches the impersonation failure mode (PHANNY-style) that Rugcheck can't see.
5. **Post-spike pre-empt.** If `priceChange.m5 < -15%` (price dropped more
   than 15% in the last 5 minutes), short-circuit normal scoring and send a
   `🟡 POST-SPIKE — CHART REVIEW REQUIRED` flag instead. Encodes Strategy 1's
   "the chart already ran = you're the exit liquidity" rule as a hard gate.
6. **Score.** Five binary checks: Rugcheck clean / holders distributed (top-10
   < 35%) / volume accelerating (5M projection > 1H average) / socials linked /
   narrative passes. Alert only on score ≥ 4.
6. **Alert.** Telegram message with a formatted card and Approve / Skip / Snooze
   inline buttons. Decisions write back to SQLite.
7. **Dedup.** Same contract is not re-alerted within 24h.

---

## Module layout

```
alert_bot/
├── config.py              # env vars + filter thresholds + blocklist
├── dex_screener_client.py # fetch, parse, filter
├── rugcheck_client.py     # contract safety check + parsing
├── narrative_filter.py    # brand + impersonation + CJK regex
├── post_spike_filter.py   # priceChange.m5 < -15% pre-empt (chart-already-ran)
├── scorer.py              # 4/5 Go/No-Go pure function (unit-tested)
├── state_store.py         # SQLite: candidates_seen / alerts_sent / decisions / trades
├── telegram_alerter.py    # v21+ async, candidate cards, callback handler
└── main.py                # asyncio loop, signal handling, daily health ping
tests/
├── test_scorer.py             # 23 tests
└── test_post_spike_filter.py  # 8 tests
```

Type hints throughout. Domain objects (`Pair`, `RugcheckResult`,
`NarrativeCheck`, `ScoredCandidate`) are frozen dataclasses.

---

## Setup (Windows 11 / PowerShell)

Requires Python 3.11+. No WSL needed — every dependency has Windows wheels.

```powershell
# 1. Create and activate a virtualenv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure secrets
Copy-Item .env.example .env
notepad .env   # fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
```

If `Activate.ps1` is blocked, run this once in PowerShell:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### Getting a Telegram bot token + chat ID

1. Open Telegram, talk to `@BotFather`, run `/newbot`, follow the prompts.
   Paste the token into `TELEGRAM_BOT_TOKEN`.
2. **Open a chat with your new bot and press Start.** Until you do this, the
   bot is not allowed to send you messages.
3. Talk to `@userinfobot` — it will reply with your numeric ID. Paste it into
   `TELEGRAM_CHAT_ID`.

---

## Running the bot

There are two ways to test it: wait for the strategy to find a real candidate
(production mode), or force the bot to surface the best coin trading *right
now* regardless of whether it meets the 4/5 threshold (debug mode).

### Mode A — Wait for a real candidate (production)

This is how the bot is meant to run. It polls Dex Screener every 60s and
alerts only when something hits the 4/5 Go/No-Go threshold. Most cycles will
log `fetched=N filtered=0` — by design. The strategy says "saying no most of
the time is correct."

```powershell
# Optional but recommended on the first run: verify the Telegram wiring
python -m alert_bot.telegram_alerter
# -> should land "✅ Alert bot wired up. (Strategy 1)" in your chat

# Then run the bot proper
python -m alert_bot.main
```

You will see:

- Immediate Telegram message: `🚀 Alert bot started (Strategy 1).`
- Terminal log every 60s: `Cycle: fetched=98 filtered=N`
- When a real 4/5 candidate appears: a card in Telegram with **👍 Approve /
  👎 Skip / ⏸ Snooze** buttons
- Daily (every 24h): a health ping with running counters

Stop the bot with `Ctrl+C` — it shuts down cleanly.

### Mode B — Force a candidate now (debug)

Runs a single full pipeline cycle (Dex Screener → Rugcheck → narrative →
score) on live market data, picks the **highest-scoring pair available right
now even if it's below 4/5**, and sends you a card prefixed with `[FORCED]`.
Useful for end-to-end validation when you don't want to wait.

```powershell
# IMPORTANT: stop the main loop first (Ctrl+C). Telegram allows only one
# long-poll connection per bot token, so they would conflict.

python scripts/force_best_candidate.py
```

If no pair currently passes the numeric pre-filters, the script falls back to
scoring every Solana pair it found and surfaces the best of those — so you
always get a card back unless Dex Screener is down.

There's also `scripts/send_test_card.py` which sends a fixed sample card
(ICED at 4/5 — same data as a forced run from earlier). It doesn't hit Dex
Screener or Rugcheck, so it's a pure render/keyboard test:

```powershell
python scripts/send_test_card.py
```

Decisions made on `[FORCED]` cards write to SQLite the same way real alerts
do. To clean them out afterward:

```sql
-- in any SQLite browser, against alert_bot.db
DELETE FROM decisions WHERE alert_id IN (
    SELECT id FROM alerts_sent WHERE snapshot_json LIKE '%"forced": true%'
);
DELETE FROM alerts_sent WHERE snapshot_json LIKE '%"forced": true%';
```

---

## Running the tests

```powershell
python -m pytest -q
```

Scorer tests live in `tests/test_scorer.py` and cover each individual rule of
the 4/5 checklist plus the threshold logic.

---

## What v1 explicitly does not do

- ❌ No on-chain transactions. The bot never signs anything.
- ❌ No auto-execution. The bot surfaces; the user decides.
- ❌ No chart-structure analysis. Volume-acceleration is the v1 proxy for
  "the chart is healthy."
- ❌ No web UI or multi-user support. Telegram only.
- ❌ No backtesting. The trade log generated by real decisions is the
  forward-looking validation dataset.

These are valid v2 additions, deliberately deferred.

---

## Tech stack

| Layer            | Choice                              | Cost          |
|------------------|-------------------------------------|---------------|
| Language         | Python 3.11+                        | free          |
| Async runtime    | asyncio                             | stdlib        |
| HTTP             | `requests` (sync)                   | free          |
| Telegram         | `python-telegram-bot` 21+ (async)   | free          |
| Persistence      | SQLite                              | stdlib        |
| Config           | `python-dotenv`                     | free          |
| Tests            | `pytest`                            | free          |
| Hosting (target) | Oracle Cloud free-tier (Ampere ARM) | $0/month      |
