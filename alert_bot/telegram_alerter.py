"""Telegram alerting: send candidate cards and listen for button presses.

Uses python-telegram-bot v21+ (async). All public methods are coroutines.

Decoupling note: this module knows nothing about Pair/RugcheckResult/ScoredCandidate.
The caller (main.py) renders a CandidateCard dataclass and registers a
DecisionCallback. Keeps the alerter independent of upstream modules.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, ContextTypes
from telegram.error import RetryAfter, TelegramError, TimedOut

from alert_bot.config import RuntimeConfig

log = logging.getLogger(__name__)

# Decisions a user can make on a candidate. Keep as strings so they're trivially
# serializable into the state store.
Decision = Literal["approve", "skip", "snooze"]


@dataclass(frozen=True)
class CandidateCard:
    """Everything needed to render and route a Telegram alert.

    Built by main.py from a ScoredCandidate; passed to send_candidate_card.
    """

    # Unique key used in callback payloads. We use the token contract address
    # since it's the natural identifier and dedup is per-contract anyway.
    contract: str
    ticker: str
    name: str
    score: int
    score_max: int
    # Pre-rendered, ordered checklist lines like "✅ Rugcheck: Good (12/100)".
    # Keeping rendering responsibility in the scorer/main wiring layer keeps
    # this module free of trading-domain logic.
    checklist_lines: list[str]
    mcap_usd: float
    liquidity_usd: float
    age_hours: float
    dexscreener_url: str
    pumpfun_url: str | None = None


# Callback signature for "user pressed a button". Async so handlers can write
# to SQLite or send follow-up messages without blocking.
DecisionCallback = Callable[[str, Decision], Awaitable[None]]


def _format_card(card: CandidateCard) -> str:
    """Render the candidate card as Markdown for Telegram."""
    header = f"🟢 *CANDIDATE — Score {card.score}/{card.score_max}*"
    title = f"${card.ticker} — {card.name}"
    stats = (
        f"MCAP: ${card.mcap_usd:,.0f}  |  "
        f"Liq: ${card.liquidity_usd:,.0f}  |  "
        f"Age: {card.age_hours:.1f}h"
    )
    body = "\n".join(card.checklist_lines)
    links = f"[Chart]({card.dexscreener_url})"
    if card.pumpfun_url:
        links += f"  |  [Pump.fun]({card.pumpfun_url})"

    return f"{header}\n*{title}*\n{stats}\n\n{body}\n\n{links}"


def _build_keyboard(contract: str) -> InlineKeyboardMarkup:
    """Inline buttons for Approve / Skip / Snooze.

    Telegram callback_data is limited to 64 bytes — we keep payloads short by
    prefixing with the verb and using the contract address (which is base58
    and ~32-44 chars).
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👍 Approve", callback_data=f"approve|{contract}"),
                InlineKeyboardButton("👎 Skip", callback_data=f"skip|{contract}"),
                InlineKeyboardButton("⏸ Snooze", callback_data=f"snooze|{contract}"),
            ]
        ]
    )


async def _send_with_retry(coro_factory, *, attempts: int = 3) -> None:
    """Send-and-retry with exponential backoff for transient Telegram errors.

    Telegram raises RetryAfter with an explicit cooldown when we hit rate limits;
    respect it rather than guessing. Other transient errors get 1s/2s/4s waits.
    """
    delay = 1.0
    for attempt in range(1, attempts + 1):
        try:
            await coro_factory()
            return
        except RetryAfter as exc:
            wait = float(exc.retry_after) + 0.5
            log.warning("Telegram rate-limited; sleeping %.1fs (attempt %d/%d)", wait, attempt, attempts)
            await asyncio.sleep(wait)
        except (TimedOut, TelegramError) as exc:
            if attempt == attempts:
                log.exception("Telegram send failed after %d attempts: %s", attempts, exc)
                raise
            log.warning("Telegram send failed (%s); retrying in %.1fs", exc, delay)
            await asyncio.sleep(delay)
            delay *= 2


class TelegramAlerter:
    """High-level facade for sending alerts and handling button presses.

    Lifecycle:
        alerter = TelegramAlerter(cfg, on_decision=...)
        await alerter.start()           # begins listening for button presses
        await alerter.send_candidate_card(card)
        ...
        await alerter.stop()
    """

    def __init__(
        self,
        cfg: RuntimeConfig,
        on_decision: DecisionCallback | None = None,
    ) -> None:
        self._cfg = cfg
        self._on_decision = on_decision
        # Application is the long-running handler host; Bot is the send-side.
        # We share one Application's Bot instance for both rather than
        # maintaining two connections.
        self._app: Application = Application.builder().token(cfg.telegram_bot_token).build()
        self._app.add_handler(CallbackQueryHandler(self._handle_callback))

    @property
    def bot(self) -> Bot:
        return self._app.bot

    async def start(self) -> None:
        """Initialize the Application and begin polling for callback queries."""
        await self._app.initialize()
        await self._app.start()
        # Start the updater so button presses come in via long-polling.
        await self._app.updater.start_polling(allowed_updates=["callback_query"])
        log.info("Telegram alerter started; listening for button presses")

    async def stop(self) -> None:
        """Gracefully shut down the Application."""
        if self._app.updater and self._app.updater.running:
            await self._app.updater.stop()
        if self._app.running:
            await self._app.stop()
        await self._app.shutdown()
        log.info("Telegram alerter stopped")

    async def send_hello(self) -> None:
        """Smoke test: send a small message to confirm bot+chat are configured."""
        async def _do() -> None:
            await self.bot.send_message(
                chat_id=self._cfg.telegram_chat_id,
                text="✅ Alert bot wired up. (Strategy 1)",
            )
        await _send_with_retry(_do)

    async def send_text(self, text: str) -> None:
        """Send a plain text message — used for daily health pings + errors."""
        async def _do() -> None:
            await self.bot.send_message(chat_id=self._cfg.telegram_chat_id, text=text)
        await _send_with_retry(_do)

    async def send_candidate_card(self, card: CandidateCard) -> None:
        """Send a formatted candidate card with Approve/Skip/Snooze buttons."""
        async def _do() -> None:
            await self.bot.send_message(
                chat_id=self._cfg.telegram_chat_id,
                text=_format_card(card),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_build_keyboard(card.contract),
                disable_web_page_preview=True,
            )
        await _send_with_retry(_do)
        log.info("Sent candidate card for %s (score %d/%d)", card.ticker, card.score, card.score_max)

    async def _handle_callback(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        """Parse a button press, ack it, persist the decision."""
        query = update.callback_query
        if query is None or query.data is None:
            return

        # Always answer the callback or the user sees a spinner forever.
        await query.answer()

        try:
            verb, contract = query.data.split("|", 1)
        except ValueError:
            log.warning("Malformed callback_data: %r", query.data)
            return

        decision: Decision
        if verb == "approve":
            decision = "approve"
            confirm = "👍 Approved"
        elif verb == "skip":
            decision = "skip"
            confirm = "👎 Skipped"
        elif verb == "snooze":
            decision = "snooze"
            confirm = "⏸ Snoozed"
        else:
            log.warning("Unknown callback verb: %r", verb)
            return

        # Strip the keyboard from the original message so the user can't
        # double-click. Editing the message also gives visual feedback.
        try:
            if query.message is not None:
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text(f"{confirm}: `{contract[:8]}…`", parse_mode=ParseMode.MARKDOWN)
        except TelegramError as exc:
            log.warning("Failed to update message after callback: %s", exc)

        if self._on_decision is not None:
            try:
                await self._on_decision(contract, decision)
            except Exception:  # noqa: BLE001 — handler must not crash the loop
                log.exception("Decision handler raised for contract=%s decision=%s", contract, decision)


async def _hello_world() -> None:
    """Entry point for `python -m alert_bot.telegram_alerter` smoke test."""
    from alert_bot.config import configure_logging, load_runtime_config

    cfg = load_runtime_config()
    configure_logging(cfg.log_level)
    alerter = TelegramAlerter(cfg)
    await alerter.start()
    try:
        await alerter.send_hello()
        log.info("Hello-world message sent. Waiting 3s for delivery...")
        await asyncio.sleep(3)
    finally:
        await alerter.stop()


if __name__ == "__main__":
    asyncio.run(_hello_world())
