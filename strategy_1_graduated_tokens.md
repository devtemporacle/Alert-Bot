# Strategy 1 — Graduated Tokens (The Liquidity Play)

**Part 1 of 2.** This is the lower-risk tier: graduated Pump.fun tokens with real
liquidity and a readable chart. Companion file: *Strategy 2 — Pre-Bond Snipes*
(smaller caps, $10-38K MCAP, thinner liquidity, higher risk).

Use this one when you want a readable chart, room to size up, and easier exits.
Use Strategy 2 when you're hunting earlier and accept more risk for more upside.

A repeatable process for trading Solana meme coins, built from the John Pork trade
that worked. The edge here is **process, not prediction.** Catalysts you can see
coming (album drops, news) are already priced in. The repeatable money is in fresh
launches with clean fundamentals and disciplined exits.

---

## Core principles

- **Only winners or high-probability setups.** If it doesn't clearly pass the
  checklist, skip it. Saying no most of the time is correct.
- **The chart already ran = you're the exit liquidity.** Never buy a vertical
  candle that's already gone parabolic.
- **Decide the exit before entering.** No exception.
- **Size assuming the position goes to zero.** If losing it would hurt, it's too big.
- **Don't move stops down. Don't add to a position because it's pumping.**
- **House-money effect is real.** After a win you feel sharp and invincible — that
  is statistically when traders give it all back. Consider stopping on a green day.

---

## The platform stack

| Platform | Role |
|---|---|
| Dex Screener | Radar — find tokens, apply filters, read charts |
| Rugcheck.xyz | Contract safety check — non-negotiable before every buy |
| Pump.fun | Launchpad — where tokens are born, holder distribution data |
| Photon | Execution terminal — use from the START for auto TP/SL (own wallet, fund it ahead) |

Note: Photon generates its own wallet separate from Phantom. To use its auto-sell
features, fund the Photon wallet first and buy through Photon directly. If you buy
via Phantom on Pump.fun, you must monitor the stop manually.

---

## Step 1 — Dex Screener filters

Set these and hit Apply. The list should shrink dramatically — that's the point.

- Platform: **Pump.fun** only (cuts noise while focused on Solana)
- Liquidity: **min $15,000**
- Pair age: **0–6 hours**
- 1H txns: **min 200**
- 1H volume: **min $20,000**
- 5M txns: **min 50**
- 5M buys: **min 25**
- 5M volume: **min $5,000**

Use **Trending → 1H** view, not 6H. The 6H view shows tokens that already moved;
the 1H view shows what's moving *now*.

---

## Step 2 — Pre-screen the list (skip fast)

Skip immediately, don't even open:

- Duplicate/copycat tickers (multiple "degen", "BULL", etc.)
- Chinese-text tokens (can't read the community)
- ETH / WBNB / USDT pairs (stay on Solana/SOL pairs)
- Old established tokens (SHIB, WOJAK, MAGA, etc. — not fresh plays)
- Anything 1+ day old that's bleeding on 1H
- Under ~110 traders or under ~$20K liquidity (too thin, fake % gains)

Open and investigate: fresh age, high trader count relative to MCAP, accelerating
volume, real narrative.

---

## Step 3 — Read the chart on Dex Screener

- **Want:** a staircase — pumps, small pullbacks, continuation. Higher lows.
- **Want:** a dip-recovery base — pumped, dumped, consolidated, now grinding back
  up on green volume with a wall of buys in the transaction feed. (This was the
  Pork setup — a "second-leg" play.)
- **Skip:** a single vertical candle with no history (someone's exit / wash trading).
- **Skip:** parabolic with no base, especially if 5M is already negative.
- Check buys vs sells ratio and buy volume vs sell volume — buyers should lead.

---

## Step 4 — Rugcheck (NON-NEGOTIABLE)

Paste the contract into rugcheck.xyz. Need to see:

- Risk Analysis: **Good** (low score)
- **LP Locked or burned** (dev can't pull liquidity)
- **Mint Authority disabled** (no one can print more)
- **Freeze Authority disabled**
- Creator balance: **low or sold** (dev can't dump on you)
- **No insider networks** detected — or if detected, note the % and watch for that
  size of sell as a dump signal
- Top 10 holders: ideally **under 30–35%**

Any red "danger" flag = skip. Check the creator's token history too — a pattern of
dead low-cap launches is a yellow flag.

Note: rugcheck won't catch *narrative* risk. Read the token description — if it's
built on impersonation (e.g. faking affiliation with a real company), skip it.
That's a legal/longevity time bomb rugcheck can't see. (This is what killed PHANNY.)

---

## Step 5 — Holder + community check

- Pump.fun / Photon: top 10 holders combined under ~35%, dev wallet no recent sells,
  not sniper-dominated at launch
- Token should have real socials linked (Twitter + Telegram, ideally TikTok for a
  meme with actual viral history)
- Dead or bot-filled Telegram = skip

---

## Step 6 — Go / No-Go

Need **YES on at least 4 of 5**:

1. Rugcheck is clean
2. Chart is a staircase or a healthy recovery base — not a spike
3. Holders are distributed
4. Volume is accelerating (5M outpacing the hourly average)
5. Community is alive + real narrative

3/5 or less = pass. There's always another coin.

---

## Step 7 — Size and execute

- Thin liquidity (~$10–40K): position size **0.3 SOL**. Can add later only if
  momentum *confirms* — never as FOMO into a pump.
- Max per trade: **1–5% of bankroll**
- Trade settings: **slippage 10%**, speed **Turbo**, **MEV protection ON**
  (critical when slippage is above 3% — stops bots sandwiching the trade)
- The moment the buy fills, record: **entry MCAP, token amount, time.**

---

## Step 8 — Exit ladder (set before/at entry)

Track **MCAP**, not price. Example ladder for a ~$220K entry:

| Target | Multiplier | Action |
|---|---|---|
| 2x | $440K | Sell 40% |
| 3x | $660K | Sell 30% |
| 5x | $1.1M | Sell 20% |
| Moon | — | Hold last 10% as a free moon bag |
| **Stop** | **-30% from entry** | **Sell 100%, no negotiation** |

Adjustments that worked on the Pork trade:
- When a trade tests you early (dumps right after entry), **hold to the pre-set
  stop** — don't panic-sell the bottom, don't move the stop down.
- When it recovers and **reclaims your entry**, consider taking ~20–40% off there.
  Getting your initial back removes all stress; the rest runs as house money.
- A **vertical breakout candle** is the highest-probability place to take profit —
  pull a ladder rung forward rather than waiting for the exact target.
- Then move the stop UP to your entry on whatever's left.

---

## Behavioral rules (the part that actually matters)

- Don't refresh tick-by-tick. Check every 2–3 minutes.
- Don't add to a position because it's pumping.
- Don't move a stop loss down.
- Take partial profits at targets even if it "looks like it's still going."
- Never chase the next coin while a live position is unmanaged.
- Catalysts everyone can see (album drops, news) are priced in — not an edge.
- After a win, watch yourself. The winner's high is when discipline slips.
- Closing the laptop on a green day is always a valid move.

---

## The Pork trade (reference example — what "right" looks like)

- Found on Dex Screener 1H trending, passed filters
- Rugcheck: Good, LP locked 99.99%, mint disabled, creator balance ~0%.
  One yellow flag: small insider cluster (~4.3%) — noted, not disqualifying.
- Chart: dip-recovery base — had pumped to ~$343K ATH, dumped to ~$120K,
  consolidated, was grinding back up with buy-dominated tape. A second-leg setup.
- Real narrative: John Pork is a genuine viral TikTok meme (not impersonation),
  socials linked including TikTok
- Entry: ~$221K MCAP, 0.3 SOL, slippage 10%, MEV on
- Trade immediately went to -13%. Held to the pre-set stop, did NOT move it down.
- It based, then broke out vertically past entry.
- Took profit on the breakout instead of getting greedy. Closed the full position.
- Outcome: profitable. More importantly — executed the process correctly start to
  finish, which is the only thing actually in your control.
