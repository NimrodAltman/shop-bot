"""
main.py
=======
The Telegram bot: onboarding, inline keyboards, location sharing, free chat.

This module is deliberately thin. It translates Telegram updates into calls to
``agent.ask_agent`` and formats the replies — no product logic lives here.

Two things worth knowing before editing:

1. ``run_polling()`` is called from the main thread. It is a blocking method
   that builds and manages its own event loop, so it must not be wrapped in
   ``asyncio.run()`` or moved onto a worker thread.
2. ``agent.ask_agent`` is synchronous and can block for seconds. It is handed to
   ``asyncio.to_thread`` so one user's slow turn doesn't freeze the bot for
   everyone else.
"""

from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import agent
from data.mock_data import CATEGORY_LABELS

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Telegram rejects messages longer than 4096 characters.
TELEGRAM_MAX_CHARS = 4096

BUDGET_OPTIONS = [
    ("Under ₪1,000", 1000),
    ("₪1,000–3,000", 3000),
    ("₪3,000–5,000", 5000),
    ("₪5,000+", 99999),
]


# ── Keyboards ─────────────────────────────────────────────────────────────────
def _category_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"cat:{key}")]
        for key, label in CATEGORY_LABELS.items()
    ]
    buttons.append([InlineKeyboardButton("Something else / just browsing", callback_data="cat:any")])
    return InlineKeyboardMarkup(buttons)


def _budget_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"budget:{value}")]
        for label, value in BUDGET_OPTIONS
    ]
    buttons.append([InlineKeyboardButton("No budget in mind", callback_data="budget:0")])
    return InlineKeyboardMarkup(buttons)


def _location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Share my location", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="…or just type your city",
    )


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _send(update: Update, text: str, **kwargs) -> None:
    """Send a reply, splitting anything past Telegram's length cap."""
    chat = update.effective_chat
    if not chat:
        return
    for i in range(0, len(text), TELEGRAM_MAX_CHARS):
        chunk = text[i : i + TELEGRAM_MAX_CHARS]
        # Keyboards only ride along with the final chunk.
        is_last = i + TELEGRAM_MAX_CHARS >= len(text)
        await chat.send_message(chunk, **(kwargs if is_last else {}))


async def _reply_via_agent(update: Update, message: str) -> None:
    """Run one agent turn with a typing indicator, then send the reply."""
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return

    await chat.send_action(ChatAction.TYPING)
    # ask_agent is blocking (network + tool calls) — keep it off the event loop.
    reply = await asyncio.to_thread(agent.ask_agent, str(user.id), message)
    await _send(update, reply)


# ── Commands ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — greet and begin onboarding: category → budget → location."""
    user = update.effective_user
    if not user:
        return

    agent.reset_conversation(user.id)
    agent.update_profile(user.id, name=user.first_name, onboarding_complete=False)

    await _send(
        update,
        f"Hi {user.first_name}! 👋\n\n"
        "I help you pick a home appliance that actually fits your needs, and find "
        "a store near you that has it in stock.\n\n"
        "What are you shopping for?",
        reply_markup=_category_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help — what this bot can do."""
    await _send(
        update,
        "*What I can do*\n\n"
        "• Recommend an appliance for your needs and budget\n"
        "• Tell you which nearby store carries it\n"
        "• Place an order and check its status\n"
        "• Answer questions about specs and energy ratings\n\n"
        "Just tell me what you're looking for — or send /start to go through "
        "the guided flow again.\n\n"
        "_Note: this is a portfolio demo. The stores, stock and orders are "
        "realistic sample data, not a real retailer._",
        parse_mode="Markdown",
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/reset — forget the conversation but keep the profile."""
    user = update.effective_user
    if not user:
        return
    agent.reset_conversation(user.id)
    await _send(update, "Fresh start — what are you looking for? 🛒")


# ── Onboarding callbacks ──────────────────────────────────────────────────────
async def on_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Category chosen — store it and ask for a budget."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    category = query.data.split(":", 1)[1]
    user_id = query.from_user.id

    if category == "any":
        agent.update_profile(user_id, category=None)
        label = "an appliance"
    else:
        agent.update_profile(user_id, category=category)
        label = CATEGORY_LABELS.get(category, category)

    await query.edit_message_text(f"Great — looking for {label}. 👌")
    await _send(update, "What's your budget?", reply_markup=_budget_keyboard())


async def on_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Budget chosen — store it and ask where they are."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    budget = int(query.data.split(":", 1)[1])
    user_id = query.from_user.id
    agent.update_profile(user_id, budget=budget or None, onboarding_complete=True)

    shown = "No problem." if not budget else f"Budget noted: up to ₪{budget:,}."
    await query.edit_message_text(f"{shown} 👌")
    await _send(
        update,
        "Last thing — where are you? Share your location or just type your city.",
        reply_markup=_location_keyboard(),
    )


# ── Message handlers ──────────────────────────────────────────────────────────
async def on_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User shared coordinates — hand them to the agent in a parseable form."""
    message = update.message
    user = update.effective_user
    if not message or not message.location or not user:
        return

    lat = message.location.latitude
    lng = message.location.longitude
    agent.update_profile(user.id, lat=lat, lng=lng)

    await message.reply_text("Got your location 📍", reply_markup=ReplyKeyboardRemove())
    await _reply_via_agent(
        update,
        f"LOCATION_SHARED: {lat},{lng}\nWhich stores are near me, and what do you recommend?",
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Any free-text message goes straight to the agent."""
    message = update.message
    if not message or not message.text:
        return
    await _reply_via_agent(update, message.text)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log handler exceptions instead of letting them die silently."""
    logger.exception("Handler error: %s", context.error)


# ── Entrypoint ────────────────────────────────────────────────────────────────
def main() -> None:
    if not TELEGRAM_TOKEN:
        raise SystemExit(
            "TELEGRAM_TOKEN is not set. Copy .env.example to .env and add a token "
            "from @BotFather."
        )
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add a key "
            "from console.anthropic.com."
        )

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(on_category, pattern=r"^cat:"))
    app.add_handler(CallbackQueryHandler(on_budget, pattern=r"^budget:"))
    app.add_handler(MessageHandler(filters.LOCATION, on_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)

    logger.info("ShopBot is up — polling for updates.")
    # Blocking call, main thread, no asyncio.run() wrapper. See module docstring.
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
