"""
main.py
=======
The Telegram bot: onboarding, inline keyboards, location sharing, free chat.

This module is deliberately thin. It translates Telegram updates into calls to
``agent.ask_agent`` and formats the replies — no product logic lives here.
Localization strings and language detection live in ``i18n.py``.

Two things worth knowing before editing:

1. ``run_polling()`` is called from the main thread. It is a blocking method
   that builds and manages its own event loop, so it must not be wrapped in
   ``asyncio.run()`` or moved onto a worker thread.
2. ``agent.ask_agent`` is synchronous and can block for seconds. It is handed to
   ``asyncio.to_thread`` so one user's slow turn doesn't freeze the bot for
   everyone else.

Language: the free-text conversation is handled entirely by the agent, which
detects the user's language on its own (see ``agent.STABLE_SYSTEM``). The
onboarding UI below (buttons, /start, /help, /update) never touches the agent,
so it is localized separately via ``i18n.py``, based on what the user has
actually typed, then their Telegram client language, then a default.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    User,
)
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import agent
import i18n

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

# Every paid Anthropic call goes through _reply_via_agent, so one gate there
# caps what a single chat can spend. Generous for a person typing (one message
# every five seconds sustained), low enough to stop a flood. Held in memory:
# a restart clears it, which is fine for a cap meant to stop an attack in
# progress rather than to bill anyone.
RATE_LIMIT_MESSAGES = 12
RATE_LIMIT_WINDOW_SECONDS = 60
_recent_messages: dict[int, list[float]] = {}


def _is_rate_limited(user_id: int) -> bool:
    """True when this user has already used up their window."""
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    timestamps = [t for t in _recent_messages.get(user_id, []) if t > cutoff]

    if len(timestamps) >= RATE_LIMIT_MESSAGES:
        _recent_messages[user_id] = timestamps
        return True

    timestamps.append(now)
    _recent_messages[user_id] = timestamps
    return False


def _lang(user: User | None) -> str:
    """Resolve the UI language for a user via i18n.resolve_lang."""
    if user is None:
        return i18n.DEFAULT_LANG
    profile = agent.get_profile(user.id)
    return i18n.resolve_lang(profile, getattr(user, "language_code", None))


def _t(lang: str, key: str, **kwargs) -> str:
    return i18n.t(lang, key, **kwargs)


def _category_label(key: str, lang: str) -> str:
    return i18n.category_label(key, lang)


# on_location builds "LOCATION_SHARED: lat,lng" itself and the system prompt
# treats it as real coordinates. Typed by hand in a normal message it would be
# taken just as seriously, so it is defanged on the way in.
_TRUSTED_MARKER = re.compile(r"LOCATION_SHARED\s*:", re.IGNORECASE)


def _defang_trusted_markers(text: str) -> str:
    """Neutralize in-band markers the system prompt is told to trust."""
    return _TRUSTED_MARKER.sub("location mentioned by the user:", text)


def _mentions_location_keywords(text: str, lang: str) -> bool:
    """True if free text hints the user wants nearby stores without one shared yet."""
    needle = text.lower()
    keywords = i18n.LOCATION_KEYWORDS.get(lang, i18n.LOCATION_KEYWORDS[i18n.DEFAULT_LANG])
    return any(kw in needle for kw in keywords)


# ── Keyboards ─────────────────────────────────────────────────────────────────
def _category_keyboard(lang: str, prefix: str = "cat") -> InlineKeyboardMarkup:
    labels = i18n.CATEGORY_LABELS_BY_LANG.get(lang, i18n.CATEGORY_LABELS_BY_LANG[i18n.DEFAULT_LANG])
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"{prefix}:{key}")]
        for key, label in labels.items()
    ]
    buttons.append([InlineKeyboardButton(_t(lang, "category_other"), callback_data=f"{prefix}:any")])
    return InlineKeyboardMarkup(buttons)


def _budget_keyboard(lang: str, prefix: str = "budget") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(option.get(lang, option["en"]), callback_data=f"{prefix}:{option['value']}")]
        for option in i18n.BUDGET_OPTIONS
    ]
    buttons.append([InlineKeyboardButton(_t(lang, "budget_no_limit"), callback_data=f"{prefix}:0")])
    return InlineKeyboardMarkup(buttons)


def _location_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(_t(lang, "share_location_button"), request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder=_t(lang, "location_placeholder"),
    )


def _update_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(lang, "update_field_category"), callback_data="upd:category")],
        [InlineKeyboardButton(_t(lang, "update_field_budget"), callback_data="upd:budget")],
        [InlineKeyboardButton(_t(lang, "update_field_location"), callback_data="upd:location")],
    ])


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _send(update: Update, text: str, **kwargs) -> None:
    """Send a reply, splitting anything past Telegram's length cap.

    Falls back to plain text if the Markdown doesn't parse — an unmatched
    ``*`` or ``_`` in a model-generated reply makes Telegram reject the whole
    message rather than rendering it loosely.
    """
    chat = update.effective_chat
    if not chat:
        return
    for i in range(0, len(text), TELEGRAM_MAX_CHARS):
        chunk = text[i : i + TELEGRAM_MAX_CHARS]
        # Keyboards only ride along with the final chunk.
        is_last = i + TELEGRAM_MAX_CHARS >= len(text)
        send_kwargs = kwargs if is_last else {}
        try:
            await chat.send_message(chunk, **send_kwargs)
        except BadRequest as exc:
            if send_kwargs.get("parse_mode") and "parse" in str(exc).lower():
                logger.warning("Markdown parse failed, retrying as plain text: %s", exc)
                fallback = {k: v for k, v in send_kwargs.items() if k != "parse_mode"}
                await chat.send_message(chunk, **fallback)
            else:
                raise


async def _reply_via_agent(update: Update, message: str) -> None:
    """Run one agent turn with a typing indicator, then send the reply."""
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return

    if _is_rate_limited(user.id):
        logger.warning("Rate limit hit for user %s", user.id)
        await _send(update, _t(_lang(user), "rate_limited"))
        return

    await chat.send_action(ChatAction.TYPING)
    # ask_agent is blocking (network + tool calls) — keep it off the event loop.
    reply = await asyncio.to_thread(agent.ask_agent, str(user.id), message)

    lang = _lang(user)
    profile = agent.get_profile(user.id)

    # Claude can't attach a Telegram keyboard itself. Re-offer the relevant
    # keyboard when the reply would otherwise leave the agent to type the
    # options out as a sentence:
    keyboard = None
    if not profile.get("category"):
        keyboard = _category_keyboard(lang)
    elif not profile.get("lat") and not profile.get("city") and _mentions_location_keywords(message, lang):
        keyboard = _location_keyboard(lang)

    await _send(update, reply, parse_mode="Markdown", reply_markup=keyboard)


# ── Commands ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — greet and begin onboarding: category → budget → location.

    A returning user with a completed profile gets a short welcome-back
    instead of being forced through onboarding again; their saved category,
    budget and location are left untouched.
    """
    user = update.effective_user
    if not user:
        return
    lang = _lang(user)

    agent.reset_conversation(user.id)

    if agent.get_profile(user.id).get("onboarding_complete"):
        await _send(update, _t(lang, "welcome_back", name=user.first_name), parse_mode="Markdown")
        return

    agent.update_profile(user.id, name=user.first_name, onboarding_complete=False)

    # Two messages, matching the reference bot's rhythm: a bold capabilities
    # card first, then the actual question with its keyboard attached.
    await _send(update, _t(lang, "greeting", name=user.first_name), parse_mode="Markdown")
    await _send(update, _t(lang, "ask_category"), reply_markup=_category_keyboard(lang))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help — what this bot can do."""
    lang = _lang(update.effective_user)
    await _send(update, _t(lang, "help"), parse_mode="Markdown")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/reset — forget the conversation but keep the profile."""
    user = update.effective_user
    if not user:
        return
    lang = _lang(user)
    agent.reset_conversation(user.id)
    await _send(update, _t(lang, "reset"))


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/update — change one saved profile field without a full /reset."""
    user = update.effective_user
    if not user:
        return
    lang = _lang(user)
    await _send(update, _t(lang, "update_menu_prompt"), reply_markup=_update_menu_keyboard(lang))


# ── Onboarding callbacks ──────────────────────────────────────────────────────
async def on_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Category chosen — store it and ask for a budget."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    lang = _lang(query.from_user)
    category = query.data.split(":", 1)[1]
    user_id = query.from_user.id

    if category == "any":
        agent.update_profile(user_id, category=None)
        label = _t(lang, "category_any_label")
    else:
        agent.update_profile(user_id, category=category)
        label = _category_label(category, lang)

    await query.edit_message_text(_t(lang, "category_confirm", label=label))
    await _send(update, _t(lang, "ask_budget"), reply_markup=_budget_keyboard(lang))


async def on_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Budget chosen — store it and ask where they are."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    lang = _lang(query.from_user)
    budget = int(query.data.split(":", 1)[1])
    user_id = query.from_user.id
    agent.update_profile(user_id, budget=budget or None, onboarding_complete=True)

    shown = _t(lang, "budget_confirm_none") if not budget else _t(lang, "budget_confirm_set", budget=budget)
    await query.edit_message_text(shown)
    await _send(update, _t(lang, "ask_location"), reply_markup=_location_keyboard(lang))


# ── Update-one-field callbacks ─────────────────────────────────────────────────
async def on_update_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User picked which single field to edit from the /update menu."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    lang = _lang(query.from_user)
    field = query.data.split(":", 1)[1]

    if field == "category":
        await _send(update, _t(lang, "ask_category"), reply_markup=_category_keyboard(lang, prefix="updcat"))
    elif field == "budget":
        await _send(update, _t(lang, "ask_budget"), reply_markup=_budget_keyboard(lang, prefix="updbudget"))
    else:
        await _send(update, _t(lang, "ask_location"), reply_markup=_location_keyboard(lang))


async def on_update_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Category edited via /update — confirm, don't chain into budget."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    lang = _lang(query.from_user)
    category = query.data.split(":", 1)[1]
    user_id = query.from_user.id

    if category == "any":
        agent.update_profile(user_id, category=None)
        label = _t(lang, "category_any_label")
    else:
        agent.update_profile(user_id, category=category)
        label = _category_label(category, lang)

    await query.edit_message_text(_t(lang, "category_confirm", label=label))


async def on_update_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Budget edited via /update — confirm, don't chain into location."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    lang = _lang(query.from_user)
    budget = int(query.data.split(":", 1)[1])
    agent.update_profile(query.from_user.id, budget=budget or None)

    shown = _t(lang, "budget_confirm_none") if not budget else _t(lang, "budget_confirm_set", budget=budget)
    await query.edit_message_text(shown)


# ── Message handlers ──────────────────────────────────────────────────────────
async def on_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User shared coordinates — hand them to the agent in a parseable form."""
    message = update.message
    user = update.effective_user
    if not message or not message.location or not user:
        return
    lang = _lang(user)

    lat = message.location.latitude
    lng = message.location.longitude
    agent.update_profile(user.id, lat=lat, lng=lng)

    await message.reply_text(_t(lang, "location_received"), reply_markup=ReplyKeyboardRemove())
    # "LOCATION_SHARED: lat,lng" is a literal marker agent.py's system prompt
    # matches on — keep that prefix in English regardless of UI language.
    await _reply_via_agent(
        update,
        f"LOCATION_SHARED: {lat},{lng}\n{_t(lang, 'location_prompt_to_agent')}",
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Any free-text message goes straight to the agent.

    Also updates the stored UI-language preference when the text gives a
    clear signal — see ``i18n.detect_lang``. The agent's own reply is
    unaffected by this (it already detects language per-message on its own);
    this only changes which language future onboarding UI (menus, /help,
    /update) uses.
    """
    message = update.message
    user = update.effective_user
    if not message or not message.text:
        return

    if user:
        detected = i18n.detect_lang(message.text)
        if detected and agent.get_profile(user.id).get("lang") != detected:
            agent.update_profile(user.id, lang=detected)

    await _reply_via_agent(update, _defang_trusted_markers(message.text))


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
    app.add_handler(CommandHandler("update", update_command))
    app.add_handler(CallbackQueryHandler(on_category, pattern=r"^cat:"))
    app.add_handler(CallbackQueryHandler(on_budget, pattern=r"^budget:"))
    app.add_handler(CallbackQueryHandler(on_update_field, pattern=r"^upd:"))
    app.add_handler(CallbackQueryHandler(on_update_category, pattern=r"^updcat:"))
    app.add_handler(CallbackQueryHandler(on_update_budget, pattern=r"^updbudget:"))
    app.add_handler(MessageHandler(filters.LOCATION, on_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)

    logger.info("ShopBot is up — polling for updates.")
    # Blocking call, main thread, no asyncio.run() wrapper. See module docstring.
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
