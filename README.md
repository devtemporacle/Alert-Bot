# Memecoin Alert Bot

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
   5M vol ≥ $5K.
3. **Rugcheck** each surviving contract via `rugcheck.xyz/v1/tokens/{mint}/report`.
   Parse mint/freeze authority state, top-10 holder concentration, LP
   protection (locked or burned), insider count, danger risks.
4. **Narrative filter:** substring match against a brand/IP blocklist plus
   "official X / real X / verified X" regex patterns, plus CJK-text detection.
   Catches the impersonation failure mode (PHANNY-style) that Rugcheck can't see.
5. **Score.** Five binary checks: Rugcheck clean / holders distributed (top-10
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
├── scorer.py              # 4/5 Go/No-Go pure function (unit-tested)
├── state_store.py         # SQLite: candidates_seen / alerts_sent / decisions / trades
├── telegram_alerter.py    # v21+ async, candidate cards, callback handler
└── main.py                # asyncio loop, signal handling, daily health ping
tests/
└── test_scorer.py         # 23 tests
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

# 4. (Optional) Smoke-test config
python -m alert_bot.config

# 5. Send a hello-world message to verify the Telegram wiring
python -m alert_bot.telegram_alerter

# 6. Run the bot
python -m alert_bot.main
```

If `Activate.ps1` is blocked:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### Getting a Telegram bot token + chat ID

1. Open Telegram, talk to `@BotFather`, run `/newbot`, follow the prompts.
   Paste the token into `TELEGRAM_BOT_TOKEN`.
2. Open a chat with your new bot and press Start.
3. Talk to `@userinfobot` — it will reply with your numeric ID. Paste it into
   `TELEGRAM_CHAT_ID`.

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
