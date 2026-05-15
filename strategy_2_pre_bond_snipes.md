# Strategy 2 — Pre-Bond Snipes (The Early Play)

**Part 2 of 2.** This is the higher-risk tier: tokens in the $10-38K MCAP range
that have NOT yet bonded/graduated. Companion file: *Strategy 1 — Graduated Tokens*
(real liquidity, readable charts, larger sizing).

The thesis: get in before a coin bonds (~$40K, when it migrates to a real DEX),
because some run hard after bonding. The reward is bigger — you're earlier. The
risk is also bigger, in ways that are easy to underestimate. Read the whole
"why this is harder" section before using this.

---

## ⚠️ Read this first — why pre-bond is harder than Strategy 1

Strategy 1 worked because graduated tokens give you **real liquidity and a
readable chart.** Pre-bond tokens give you neither. Specifically:

- **There is barely a chart.** A coin that's minutes-to-hours old at $15K MCAP has
  almost no price history. The core Strategy 1 edge — reading staircase vs. spike —
  mostly doesn't exist here. You're trading on holder data and dev behavior, not
  structure.
- **Liquidity is brutal.** Many of these have $3-15K liquidity. A 0.1 SOL buy moves
  the price; your exit moves it harder. Round-trip slippage can eat 15-20% before
  the coin does anything.
- **Most never bond.** The large majority of "almost bond" coins die on the curve.
  Survivorship bias makes this tier look better than it is — you remember the one
  that ran, not the ten that didn't.
- **Graduation is often a SELL event, not a buy event.** Snipers who got in early
  take profit exactly when the coin bonds — i.e. exactly when your "it graduated!"
  thesis fires. "Sometimes they go high after bonding" is true. "Usually they dump
  on bonding" is also true.
- **GMGN's data fields are not rugcheck.** The icons and %s are useful triage, but
  you still paste the contract into rugcheck.xyz before buying. The checklist gets
  MORE important here, not less — and slower per coin, not faster.

**Bottom line:** this is not a beginner's strategy and it is never a "trade #3 of a
long day right after a loss" strategy. Run it fresh, early in a session, with a
clear head, or don't run it.

---

## The platform stack

Same as Strategy 1, plus:

| Platform | Role |
|---|---|
| GMGN (gmgn.ai) | Primary radar for pre-bond — the "Trenches" / New + Almost Bond columns |
| Dex Screener | Secondary — once a coin is bonding/bonded, for any chart that exists |
| Rugcheck.xyz | Contract safety — non-negotiable, every time, even at $12K MCAP |
| Pump.fun | Holder distribution, dev wallet, bonding curve % |
| Photon | Execution + auto TP/SL (fund the Photon wallet ahead of time) |

---

## Understanding the GMGN "Trenches" view

Three columns, left to right, tracking a coin's life:

- **New** — just launched. Too early even for this strategy. Mostly noise.
- **Almost Bond** — the target zone. ~$10-38K MCAP, climbing the bonding curve
  toward the ~$40K graduation point. This is where Strategy 2 operates.
- **Migrated** — already bonded/graduated. At this point it's a Strategy 1 candidate,
  not a Strategy 2 one.

Each row shows a cluster of small data fields. The ones that matter most:

- **MC** — market cap. Target the $10-38K band. Under ~$10K is too early/thin.
- **Bonding progress** — how close to graduation. Higher = closer = less time for
  the thesis to play out, but also more confirmation it has demand.
- **Holder count** — more distinct holders = more organic. Very low = sniper/bot.
- **Top holder / dev %** — high concentration = coordinated dump risk.
- **DS (Dev Sold) / dev status** — whether the dev still holds. Dev sold = neutral
  to good (can't dump on you). Dev holding a big % = risk.
- **Volume + TX count** — real activity vs. a coin that's frozen.
- **Paid icons / socials** — has the project paid for DexScreener enhancement, has
  it linked socials. Presence of real socials matters; absence is a flag.

GMGN puts a lot on screen. Don't let the density rush you — the density is the trap.

---

## Step 1 — Configure the GMGN filter panel

GMGN's filter panel (the funnel icon on the Almost Bond column) does the screening
*before* you ever look at a coin. Setting it well is most of the edge in this
strategy — it takes you from ~50 rows to maybe 2-3 worth examining. Open the filter,
make sure you're on the **"Almost bonded"** tab, and set the following.

### Checkboxes (top of the panel) — turn ON:

- **Dev Sell All** OR **Dev Burnt** — pick one. The dev can't dump on you. This
  does the "dev behavior" checklist work up front.
- **Exclude Wash Trading**, **Exclude Dev Wash Trading**, **Exclude Insiders Wash
  Trading** — turn on all three. Kills the fake-volume coins (the absurd "+744,000%"
  garbage). Biggest single noise reduction.
- **Original Socials** — on. Forces real linked socials (part of the 4/5 checklist).
- Leave **Pump Livestream** and the **Exclude Vamped** options alone — not core.

### Numeric ranges — set these:

| Filter | Min | Max | Why |
|---|---|---|---|
| MKT Cap | 10K | 38K | The Strategy 2 target band |
| B. Curve (bonding) | 50% | — | Meaningfully up the curve, not just-entered |
| Liquidity | 8K | — | Cuts the brutal sub-$8K micro-pools |
| Total Holders | 150 | — | Filters out sniper-only coins |
| Volume | 30K | — | Real, ongoing activity, not a frozen coin |
| Age | 10 min | — | Skips the chaotic first few minutes |

### The scam-detection fields (further down the panel) — the real gold:

| Filter | Max | Why |
|---|---|---|
| Top 10 Holding | 30-35% | Enforces "holders distributed" |
| Dev Holding | ~5% | Dev can't dump a big bag |
| Insiders | ~10% | Limits coordinated insider supply |
| Bundlers | low | High % = supply sniped in coordinated chunks at launch |
| Snipers Hold | low | How much is held by launch snipers waiting to dump |
| Rug % | as low as possible | GMGN's own rug-likelihood score |

Hit **Apply**. Whatever survives is your short list of *candidates to evaluate* —
not coins to buy.

**Critical caveat:** the filter panel is triage, NOT a substitute for rugcheck.
GMGN's fields are estimates. A coin that passes every filter here still gets its
contract pasted into rugcheck.xyz before it's a real candidate. The filters get
you from 50 coins to 2-3 worth examining — they do not get you to "buy."

---

## Step 2 — Pre-screen the filtered list, skip fast

Step 1's filter panel does most of the heavy lifting, but it can't catch
everything — names and narratives need a human eye. Scan the surviving list and
skip immediately:

- **Identical/templated names** — multiple "oil reserve" coins, multiple copies of
  one meme, whole clusters of one theme (e.g. ICEMAN / ICE / ICETROLL / ICEHOUSE
  all at once). No organic energy. (Seen repeatedly in live sessions.)
- **Absurd, identical %s across multiple coins** — if the wash-trading filters were
  off or missed something: +744K%, +45,946%, multiple coins with the exact same
  numbers = wash trading / broken data, not real moves.
- **Chinese-text tokens** — can't read the community.
- **No real socials** — even if "Original Socials" was checked, eyeball them: a
  linked-but-dead or bot-filled social counts as no social.
- **MC already near or past ~$40K** — that's a Strategy 1 candidate now, evaluate
  it under Strategy 1's rules instead.

---

## Step 3 — Rugcheck (NON-NEGOTIABLE, even at $12K MCAP)

Paste the contract into rugcheck.xyz. Need:

- Risk Analysis: **Good**
- **LP Locked or burned**
- **Mint Authority disabled**
- **Freeze Authority disabled**
- Creator balance: **low or sold**
- **No insider networks** — or if detected, note the size and treat it as a dump
  signal to watch for
- Check the creator's token history — a string of dead launches is a flag

Also read the token description for **narrative risk** rugcheck can't catch:
impersonation of a real company/brand = skip (this is what killed the PHANNY
candidate in the Strategy 1 sessions).

A clean rugcheck is a *safety check, not a buy signal.* It means the coin probably
won't rug — it says nothing about whether it'll bond or run.

---

## Step 4 — The pre-bond Go / No-Go

Because there's barely a chart, the checklist weights shift. You're judging
**people and structure**, not price action. Need **YES on at least 4 of 5**:

1. **Rugcheck clean** (same as always — non-negotiable)
2. **Holders distributed** — decent distinct holder count, no single wallet
   dominating, dev not holding a big bag
3. **Bonding progress is meaningful AND still climbing** — not stalled near the
   bottom of the curve, not already basically bonded
4. **Volume / TX activity is real and ongoing** — buys present in the live feed,
   not a frozen coin
5. **Real narrative + real socials** — an actual meme with linked, non-bot socials

3/5 or less = skip. There is always another coin entering the Almost Bond column.

Note what's NOT on this list: "the chart looks good." At this stage there isn't
enough chart to judge. Don't invent structure that isn't there.

---

## Step 5 — Size and execute

Pre-bond is the higher-risk tier, so size DOWN from Strategy 1:

- **Position size: 0.1 SOL.** Not 0.2, not 0.3. Assume it goes to zero.
- **Max per trade: 1-3% of bankroll** (tighter than Strategy 1's 1-5%)
- Trade settings: **slippage 10-15%** (thin liquidity needs more room — but be aware
  high slippage means high sandwich risk, hence:), **MEV protection ON**, speed
  **Turbo**
- The instant the buy fills, record: **entry MCAP, token amount, time, bonding %**

Expect meaningful entry slippage on a thin pool. That's priced in — it's why the
size is small.

---

## Step 6 — Exit ladder (set before/at entry)

The exit logic is different from Strategy 1 because **bonding is the key event.**

| Trigger | Action |
|---|---|
| **Coin bonds / hits ~$40K** | **Sell 50%.** Bonding is often where snipers dump. Take half off the table AT graduation. Don't assume the post-bond run. |
| **2x from entry** | Sell another 25% |
| **3x+ from entry** | Sell another 15% |
| **Moon bag** | Hold last 10% |
| **STOP: -25% from entry** | **Sell 100%, no negotiation** |
| **Stalls on the curve** | If bonding progress flatlines and volume dries up — the coin is dying on the curve. Close it, don't wait for the stop. |

The single most important rung: **sell 50% at bonding.** The whole strategy thesis
is "get in before the bond." Once the bond happens, the thesis has *played out* —
you were right, now collect. If it runs further after, great, you still have 50%.
If it dumps on graduation (common), you already took half off at the top.

---

## Behavioral rules (same backbone as Strategy 1, plus pre-bond specifics)

- Don't refresh tick-by-tick. The GMGN data density makes this worse — slow down.
- Don't add to a position because it's climbing the curve.
- Don't move a stop down.
- **Take the 50% at bonding even if it "looks like it's still going."**
- Never chase the next coin while a live position is unmanaged.
- Survivorship bias is strongest in this tier — for every coin that ran post-bond,
  many died on the curve. Don't let the winners you remember set your expectations.
- After a win, watch yourself. After a loss, do NOT "win it back" with a pre-bond
  trade — escalating risk right after a loss is the classic account-killer.
- This strategy demands sharp judgment. If you're tired, several hours in, or just
  closed a trade — that's a skip. The setup that fails the checklist most often is
  your own state.
- Closing the laptop on a green day is always a valid move.

---

## How this differs from Strategy 1 — quick reference

| | Strategy 1 — Graduated | Strategy 2 — Pre-Bond |
|---|---|---|
| Target | Graduated Pump.fun tokens | $10-38K MCAP, not yet bonded |
| Primary radar | Dex Screener trending | GMGN "Almost Bond" column |
| Liquidity | $15K+ (filtered) | Often $3-15K — much thinner |
| Chart | Readable — structure is a core signal | Barely exists — not a core signal |
| What you judge | Chart structure + momentum + fundamentals | Holders + dev behavior + bonding progress |
| Key event | Breakout / momentum confirmation | Bonding / graduation (~$40K) |
| Position size | 0.2-0.3 SOL | 0.1 SOL |
| Max per trade | 1-5% bankroll | 1-3% bankroll |
| Slippage | 10% | 10-15% |
| First profit-take | ~+40% on weak setups, else 2x | 50% AT bonding |
| Risk tier | Lower | Higher |

---

## Reminder

Both strategies share the same core: clean rugcheck, distributed holders, real
narrative, pre-decided exits, small size, and the discipline to skip. Strategy 2
is not "Strategy 1 but for bigger gains" — it's a genuinely higher-risk game with
less information to work from. Treat it that way. Run it fresh, run it small, and
when nothing on the list passes the 4/5 checklist, the answer is the same as it
always is: skip, and that's the win.
