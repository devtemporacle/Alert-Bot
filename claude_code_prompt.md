# Claude Code Prompt — Strategy 1 Alert Bot

Copy and paste the prompt below into Claude Code in your terminal. Before
you do, make sure you have:

- The spec file `strategy_3_alert_bot.md` saved somewhere accessible (e.g.
  in the project root, or you can paste its contents into the prompt)
- The strategy file `strategy_1_graduated_tokens.md` available for reference
- Python 3.11+ installed
- A new empty directory where you want the project to live
- A Telegram account (you'll need to talk to BotFather to create a bot
  token — Claude Code will walk you through this)

---

## The prompt

```
I want you to build a Strategy 1 Alert Bot — a Python application that
watches Solana meme coins on Dex Screener, applies a filter + rugcheck +
scoring pipeline, and sends Telegram alerts on high-scoring candidates so I
can decide whether to trade them manually.

This is a portfolio project. The bar is well-engineered code that
demonstrates the strategy, not a guaranteed-profitable trading system. The
bot does NOT execute trades — it sends alerts, I decide manually.

I have two reference documents I want you to read first before doing
anything:

1. `strategy_1_graduated_tokens.md` — the trading strategy this bot
   automates. Read this so you understand the filters, the 4/5 Go/No-Go
   checklist, and the rules.

2. `strategy_3_alert_bot.md` — the architecture spec for this bot.
   Read this carefully. It defines the modules, the data flow, the free
   tech stack, and the explicit v1 scope (what's IN and what's OUT).

Both files should be in the project directory. If you can't find them, stop
and ask me to provide them before going further.

**Before writing any code, do these things in order:**

1. Read both .md files end-to-end.
2. Summarize back to me, in 5-10 bullets, what you understood the bot
   should and shouldn't do. I want to confirm we're aligned on scope
   before you start.
3. Lay out a build plan: what modules you'll create, in what order, and
   what each one will do at minimum to be testable. Show me the plan as
   a checklist.
4. Wait for me to confirm before writing any code.

**Constraints — non-negotiable:**

- Python 3.11+, standard library + minimal dependencies (requests,
  python-telegram-bot, sqlite3 from stdlib, python-dotenv). No bloated
  frameworks.
- All secrets via `.env` file with `.env.example` committed and `.env`
  in `.gitignore`. Never commit a real Telegram token.
- SQLite for state. No external database.
- No on-chain transactions, no wallet signing, no auto-execution.
  v1 sends alerts only.
- Free APIs only — Dex Screener public API, rugcheck.xyz public API,
  Telegram Bot API. If something requires a paid key, stop and ask.
- Modular structure as specified in `strategy_3_alert_bot.md`. One
  responsibility per file.
- Type hints throughout. Dataclasses for domain objects (Pair,
  RugcheckResult, ScoredCandidate).
- Graceful error handling — the bot must not crash on API rate limits
  or transient failures. Retry with exponential backoff, log clearly.
- Tests for the scoring logic specifically (`scorer.py`) — that module
  encodes the trading rules and must be correct. Other modules can have
  light smoke tests or be tested manually.
- A clean README.md with setup instructions, the honest disclaimers
  from the spec, and a "how to run locally" section.
- A requirements.txt or pyproject.toml.

**Build sequence — follow this order from the spec:**

1. Project skeleton: directory structure, requirements.txt, .env.example,
   .gitignore, README.md stub, empty module files.
2. `config.py` — load env vars, define filter thresholds and blocklist.
3. `telegram_alerter.py` — get a hello-world alert working FIRST. This
   validates the most fragile external dependency before anything else
   is built.
4. `dex_screener_client.py` — fetch trending pairs, apply numeric
   filters, return typed Pair objects.
5. `rugcheck_client.py` — call the rugcheck API for a contract, return
   typed RugcheckResult.
6. `state_store.py` — SQLite schema for candidates_seen, alerts_sent,
   decisions, trades. Dedup logic.
7. `narrative_filter.py` — keyword/brand blocklist check on token name
   and description.
8. `scorer.py` — combine all the above into the 4/5 Go/No-Go score.
   This is the module that gets unit tests.
9. `main.py` — the main loop. Wire it all together.
10. End-to-end dry run on real Dex Screener data, alerts pointed to a
    test Telegram chat.

After each module is built, run it standalone (a small `if __name__ ==
'__main__':` test) to verify it works before moving to the next one.

**Decision points where I want you to stop and ask, not assume:**

- The exact Dex Screener API endpoint and response shape. Look at their
  current public docs and confirm the schema with me before parsing it.
- Whether to use `python-telegram-bot` v20+ (async) or v13.x (sync).
  Confirm with me — I want to know what we're committing to.
- The exact filter thresholds from the spec — confirm them with me by
  echoing them back before hardcoding.
- The keyword/IP blocklist contents — generate a starter list and let
  me review it before committing it.
- Anything in the spec that's ambiguous or you'd otherwise have to guess.

**Honest disclaimers — put these in the README verbatim:**

- This is a tooling project for a personal trading strategy. It is not
  financial advice and the strategy is not validated at scale.
- The bot does not execute trades. It surfaces candidates. The user is
  responsible for every decision.
- Cryptocurrency trading, especially meme coins, has a high probability
  of total loss. This bot enforces discipline; it does not guarantee
  profit.

**Final reminder:** I'm coming from a C#/.NET + React + AWS background.
Python is not my daily language. Write code that's readable and
well-commented, and when you make non-obvious choices (e.g. async vs sync,
specific library quirks), drop a one-line comment explaining why. This
helps me learn the codebase as I read it.

Start by reading the two .md files and summarizing back what you
understood. Don't write any code until I confirm.
```

---

## After Claude Code finishes building

A few honest things to do before you call it done:

1. **Run it in dry-run mode for at least 24 hours** before you trust any
   alert. The first day will surface API quirks, rate-limit issues, and
   weird edge cases.

2. **Compare what the bot alerts on against what you'd have picked
   manually** from the same Dex Screener view. If the bot is alerting on
   stuff you'd skip, the filters or scoring need tightening. If the bot
   is silent on stuff you'd take, the filters are too tight.

3. **Track decisions in the trades table from day one.** That log is the
   thing that turns this from "a bot" into "evidence of a strategy" —
   without it, you've built a tool with no validation story.

4. **Don't trade real money on the bot's alerts until you have at least
   2 weeks of dry-run data showing it surfaces sensible candidates.**
   The bot can have a bug that consistently misranks tokens; you want to
   find that in dry-run, not in live trades.

5. **Put it on GitHub** when it's working. Recruiter-friendly repo
   structure: clear README, screenshots of a Telegram alert, a short
   "lessons learned" section, the honest disclaimers. This is the
   resume artifact.

---

## If Claude Code goes off the rails

If at any point the bot starts including features outside the v1 scope —
auto-execution, on-chain transactions, wallet integration, a web UI,
unnecessary frameworks — stop it and remind it of the scope from
`strategy_3_alert_bot.md`. The most common failure mode for AI coding tools
is scope creep "to be helpful." The whole value of the spec is that it
defines what NOT to build.

Good luck. Build it well, run it long enough to learn something, and let
the trade log do the talking.
