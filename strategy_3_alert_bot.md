# Strategy 3 — Alert Bot Architecture

**Companion to:** `strategy_1_graduated_tokens.md` (what the bot automates)
**Goal:** A human-in-the-loop alert bot that runs Strategy 1's filter +
rugcheck + checklist scoring automatically, then pings the user on Telegram
with a candidate card. **User approves/rejects manually.** No auto-execution
in v1 — that comes later, after the alert bot has produced a real trade log
that validates the strategy's edge.

This is also a portfolio project. The bar is "well-engineered system that
demonstrates the strategy," not "guaranteed profitable bot."

---

## Why human-in-the-loop, not full auto

Two reasons, both honest:

1. **Sample size.** We have ~2 trades of data on Strategy 1. We do not yet
   know if the strategy is +EV over 30-100 trades. Automating execution before
   knowing this is automating losses if the edge isn't real. The alert bot
   *generates the trade log* needed to find out.
2. **Judgment gap.** The 4/5 checklist has parts a bot does well (numeric
   filters, rugcheck API, holder concentration) and parts it does poorly
   (narrative quality, impersonation detection, chart structure intuition).
   Human approval keeps the irreplaceable parts of the process intact.

v2 (after 30+ logged trades show the strategy is real) can add auto-execution
on high-confidence setups. v1 is alerts only.

---

## High-level flow

```
[Dex Screener API]          [Rugcheck API]          [Pump.fun page scrape]
        │                         │                          │
        └───────────┬─────────────┴──────────────────────────┘
                    ▼
          [Filter + Score module]
                    │
                    ▼
          [Candidate evaluator]  ◄── (optional LLM narrative check)
                    │
                    ▼
          [Deduplication + state store]  ── SQLite
                    │
                    ▼
            [Telegram alerter]  ── pings user with candidate card
                    │
                    ▼
            [Manual decision]
                    │
            ┌───────┴────────┐
            ▼                ▼
        Approve          Reject
            │                │
            ▼                ▼
        [Trade log writer]   (log skip, used for analytics)
```

Every step writes to SQLite. The trade log is the whole point — it's what
turns "the strategy" into "evidence the strategy works or doesn't."

---

## Free stack — what runs where

| Layer | Choice | Cost | Notes |
|---|---|---|---|
| Language | Python 3.11+ | free | Best library support for this domain |
| Hosting | Oracle Cloud free-tier VM (Ampere ARM) | $0 forever | Genuinely always-free, 4 vCPU / 24GB RAM available |
| Database | SQLite | $0 | Local file, sufficient for one-user scale |
| Dex Screener data | Their public API | $0 | Rate-limited, fine for 30-60s polling |
| Rugcheck | rugcheck.xyz public API | $0 | Rate-limited |
| Solana RPC | Public RPCs (api.mainnet-beta.solana.com) | $0 | Slow but works for read-only |
| Alerts | Telegram Bot API | $0 | Best-in-class for this use case |
| Narrative check | Keyword/IP blocklist | $0 | Covers ~70% of impersonation cases for free |
| Narrative check (optional v2) | Claude Haiku API | ~$1-2/mo | Only if blocklist proves insufficient |
| Monitoring | journalctl + Telegram health pings | $0 | Bot pings you if it crashes |

Total operating cost for v1: **$0/month.**

---

## Modules

Organize the code into clear modules — also makes it portfolio-presentable.

### 1. `config.py`
- Load environment variables (Telegram bot token, chat ID, optional API keys)
- Filter thresholds (lifted from Strategy 1: liquidity min $15K, age 0-6h,
  1H txns min 200, 1H vol min $20K, 5M txns min 50, 5M buys min 25,
  5M vol min $5K)
- Poll interval (start at 60s)
- Brand/IP keyword blocklist for narrative check

### 2. `dex_screener_client.py`
- Fetch trending Solana / 1H pairs from Dex Screener's API
  (`https://api.dexscreener.com/latest/dex/...`)
- Parse response into a typed `Pair` dataclass
- Apply numeric filters from `config.py`
- Returns a list of `Pair` objects that pass mechanical filters
- Handle rate limits with exponential backoff

### 3. `rugcheck_client.py`
- Call rugcheck.xyz API for a given contract address
- Parse: risk score, LP locked %, mint authority status, creator balance,
  insider networks, top holders %
- Returns a `RugcheckResult` dataclass
- Cache results in SQLite keyed by contract — never check the same contract
  twice in one session

### 4. `narrative_filter.py`
- Read token name + description
- Check against brand/IP blocklist (Disney, Marvel, Pokemon, Nintendo,
  Tesla, Apple, Nike, Phantom, MetaMask, Coinbase, etc. — be generous)
- Check against "obvious impersonation" patterns (e.g. "Official X",
  "Real X", "X Token" where X is a known brand)
- v1: returns just a bool + reason
- v2 (optional): if no keyword hit, fall through to a Haiku API call with
  a structured prompt — keep this gated behind a config flag so it stays $0
  by default

### 5. `scorer.py`
- Takes a `Pair` + `RugcheckResult` + narrative check result
- Scores against the 4/5 Go/No-Go from Strategy 1:
  1. Rugcheck clean
  2. Holders distributed (top 10 < 35%)
  3. Volume accelerating (5M outpacing hourly average)
  4. Has socials linked
  5. Passes narrative check (no impersonation flag)
- Returns score 0-5 + per-item pass/fail breakdown
- Threshold: only alert on 4/5 or 5/5

### 6. `state_store.py`
- SQLite tables:
  - `candidates_seen` (contract, first_seen_at, last_score)
  - `alerts_sent` (contract, alerted_at, score, snapshot_json)
  - `decisions` (alert_id, decision, decided_at, notes)
  - `trades` (decision_id, entry_mcap, exit_mcap, entry_size, exit_size, pnl_sol)
- Prevents duplicate alerts (don't re-alert on a coin already alerted in last 24h)
- The trade log table is the data you'll eventually analyze to see if
  Strategy 1 is +EV

### 7. `telegram_alerter.py`
- Format a candidate card:
  ```
  🟢 CANDIDATE — Score 4/5
  $TICKER — TokenName
  MCAP: $XXK  |  Liq: $XXK  |  Age: Xh

  ✅ Rugcheck: Good (X/100)
  ✅ Top holders: XX% (distributed)
  ✅ Volume accelerating (5M $XK / 1H avg $XK)
  ✅ Socials linked
  ⚠️ Narrative: borderline (no IP match)

  Chart: <dexscreener link>
  Pump.fun: <link>

  [👍 Approve]  [👎 Skip]  [⏸ Snooze]
  ```
- Inline keyboard buttons for approve/skip/snooze
- Listen for callback queries, write decision to `state_store`

### 8. `main.py`
- Main loop:
  1. Sleep `poll_interval`
  2. Fetch trending list from Dex Screener
  3. For each pair that passes numeric filters:
     - Skip if already alerted in last 24h
     - Run rugcheck
     - Run narrative filter
     - Score
     - If score >= 4: send Telegram alert
  4. Log everything to SQLite
- Send a daily health ping to Telegram at midnight ("bot alive,
  X candidates seen, Y alerts sent")
- Graceful shutdown on SIGTERM

---

## What v1 explicitly does NOT do

Listing these explicitly so the scope stays tight and the build doesn't drag:

- ❌ No auto-execution. Bot suggests, you decide.
- ❌ No on-chain transactions. Bot never signs anything.
- ❌ No portfolio tracking beyond decisions log.
- ❌ No chart-structure analysis (the "is this a staircase" judgment).
  Volume-accelerating proxy is good enough for v1.
- ❌ No multi-user / web UI. Telegram only.
- ❌ No backtesting framework. The whole point is to gather forward-looking
  data via the trade log; historical Pump.fun data is messy anyway.

These are all valid v2/v3 additions. Don't build them yet.

---

## Build sequence (suggested order)

Build module by module, test each before moving on. Each step ends with
something you can run and verify.

1. **Telegram bot setup + `telegram_alerter.py`** — get a hello-world
   alert flowing first. Cheapest dopamine, validates the alerting path.
2. **`config.py` + `dex_screener_client.py`** — fetch the trending list,
   apply numeric filters, print to console.
3. **`rugcheck_client.py`** — call rugcheck for one known contract, parse
   the response cleanly.
4. **`state_store.py`** — SQLite schema + dedup logic.
5. **`scorer.py` + `narrative_filter.py`** — the scoring layer.
6. **`main.py`** — wire it all together, dry-run for an hour with alerts
   pointed to a test Telegram chat.
7. **Deploy to Oracle Cloud free tier**, run for a week, see what alerts
   look like, tune thresholds.
8. **Iterate.** Add the LLM narrative check in v1.1 if the keyword
   blocklist proves insufficient.

Expected total build time for someone with your background
(C#/.NET + AWS + some Python): **one focused weekend for v1**, plus a week
of running and tuning thresholds before it's actually useful.

---

## Validation — the part that turns "code" into "evidence"

After 30+ trades logged through the decision/trades tables, you can answer:
- What % of 4/5 candidates that you approved became winners?
- Average multiplier on winners, average loss on losers?
- Is the strategy +EV after slippage and gas?
- Which checklist items have the strongest correlation with winners?

That analysis is the resume gold, not the bot itself. A bot that runs and
sends alerts is competent engineering. A bot that runs, sends alerts, and
ships with a Jupyter notebook analyzing 60 days of decisions to answer
"does this strategy actually work" is a *real* portfolio piece.

---

## Honest disclaimers (worth keeping in the README)

- This is a tooling project for a personal trading strategy. It is not
  financial advice and the strategy itself is not validated at scale yet.
- The bot does not execute trades. It surfaces candidates. The user is
  responsible for every decision.
- Cryptocurrency trading, especially meme coins, has a high probability of
  total loss. The bot is built to enforce discipline, not to guarantee
  profit.

These belong in the repo README. Recruiters and engineering interviewers
read honesty as a strength, not a weakness.
