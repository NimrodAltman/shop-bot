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

Language: the free-text conversation is handled entirely by the agent, which
detects the user's language on its own (see ``agent.STABLE_SYSTEM``). The
onboarding UI below (buttons, /start, /help) never touches the agent, so it is
localized separately here, based on the user's Telegram client language
(``update.effective_user.language_code``) — no manual language switch needed.
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
    User,
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

# ── Localization ────────────────────────────────────────────────────────────
# Only the onboarding UI lives here. Free-text chat is localized by the agent
# itself, per-message, and isn't affected by any of this.
SUPPORTED_LANGS = ("en", "he")

CATEGORY_LABELS_HE = {
    "tv": "טלוויזיה",
    "air_conditioner": "מזגן",
    "refrigerator": "מקרר",
    "washing_machine": "מכונת כביסה",
    "microwave": "מיקרוגל",
}

# (internal budget ceiling, English label, Hebrew label)
BUDGET_OPTIONS = [
    (1000, "Under ₪1,000", "עד ₪1,000"),
    (3000, "₪1,000–3,000", "₪1,000–3,000"),
    (5000, "₪3,000–5,000", "₪3,000–5,000"),
    (99999, "₪5,000+", "₪5,000 ומעלה"),
]

STRINGS = {
    "en": {
        "greeting": (
            "Hi {name}! 👋\n\n"
            "I help you pick a home appliance that actually fits your needs, and "
            "find a store near you that has it in stock.\n\n"
            "What are you shopping for?"
        ),
        "category_other": "Something else / just browsing",
        "category_any_label": "an appliance",
        "category_confirm": "Great — looking for {label}. 👌",
        "ask_budget": "What's your budget?",
        "budget_no_limit": "No budget in mind",
        "budget_confirm_set": "Budget noted: up to ₪{budget:,}.",
        "budget_confirm_none": "No problem.",
        "ask_location": "Last thing — where are you? Share your location or just type your city.",
        "share_location_button": "📍 Share my location",
        "location_placeholder": "…or just type your city",
        "location_received": "Got your location 📍",
        "location_prompt_to_agent": "Which stores are near me, and what do you recommend?",
        "help": (
            "*What I can do*\n\n"
            "• Recommend an appliance for your needs and budget\n"
            "• Tell you which nearby store carries it\n"
            "• Place an order and check its status\n"
            "• Answer questions about specs and energy ratings\n\n"
            "Just tell me what you're looking for — or send /start to go through "
            "the guided flow again.\n\n"
            "_Note: this is a portfolio demo. The stores, stock and orders are "
            "realistic sample data, not a real retailer._"
        ),
        "reset": "Fresh start — what are you looking for? 🛒",
    },
    "he": {
        "greeting": (
            "היי {name}! 👋\n\n"
            "אני עוזר לבחור מכשיר חשמלי שבאמת מתאים לצרכים שלך, ולמצוא חנות "
            "קרובה שיש לה אותו במלאי.\n\n"
            "מה מחפשים?"
        ),
        "category_other": "משהו אחר / רק מסתכלים",
        "category_any_label": "מכשיר חשמלי",
        "category_confirm": "מעולה — מחפשים {label}. 👌",
        "ask_budget": "מה התקציב?",
        "budget_no_limit": "אין תקציב מוגדר",
        "budget_confirm_set": "התקציב נקלט: עד ₪{budget:,}.",
        "budget_confirm_none": "אין בעיה.",
        "ask_location": "עוד דבר אחד — איפה אתם נמצאים? שתפו מיקום או פשוט הקלידו את העיר.",
        "share_location_button": "📍 שיתוף המיקום שלי",
        "location_placeholder": "…או פשוט הקלידו את העיר",
        "location_received": "קיבלתי את המיקום 📍",
        "location_prompt_to_agent": "אילו חנויות קרובות אליי, ומה אתם ממליצים?",
        "help": (
            "*מה אני יכול לעשות*\n\n"
            "• להמליץ על מכשיר חשמלי לפי הצרכים והתקציב שלכם\n"
            "• להגיד לכם איזו חנות קרובה מחזיקה אותו\n"
            "• לבצע הזמנה ולבדוק את הסטטוס שלה\n"
            "• לענות על שאלות לגבי מפרטים ודירוגי אנרגיה\n\n"
            "פשוט תגידו לי מה אתם מחפשים — או שלחו /start כדי לעבור שוב על "
            "התהליך המודרך.\n\n"
            "_הערה: זהו פרויקט הדגמה. החנויות, המלאי וההזמנות הם נתוני דוגמה "
            "ריאליסטיים, לא קמעונאי אמיתי._"
        ),
        "reset": "התחלה חדשה — מה אתם מחפשים? 🛒",
    },
}


def _lang(user: User | None) -> str:
    """Map a Telegram user's client language to a supported UI language."""
    code = (getattr(user, "language_code", None) or "en").split("-")[0].lower()
    return code if code in SUPPORTED_LANGS else "en"


def _t(lang: str, key: str, **kwargs) -> str:
    return STRINGS[lang][key].format(**kwargs)


def _category_label(key: str, lang: str) -> str:
    labels = CATEGORY_LABELS_HE if lang == "he" else CATEGORY_LABELS
    return labels.get(key, key)


# ── Keyboards ─────────────────────────────────────────────────────────────────
def _category_keyboard(lang: str) -> InlineKeyboardMarkup:
    labels = CATEGORY_LABELS_HE if lang == "he" else CATEGORY_LABELS
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"cat:{key}")]
        for key, label in labels.items()
    ]
    buttons.append([InlineKeyboardButton(_t(lang, "category_other"), callback_data="cat:any")])
    return InlineKeyboardMarkup(buttons)


def _budget_keyboard(lang: str) -> InlineKeyboardMarkup:
    label_idx = 2 if lang == "he" else 1
    buttons = [
        [InlineKeyboardButton(option[label_idx], callback_data=f"budget:{option[0]}")]
        for option in BUDGET_OPTIONS
    ]
    buttons.append([InlineKeyboardButton(_t(lang, "budget_no_limit"), callback_data="budget:0")])
    return InlineKeyboardMarkup(buttons)


def _location_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(_t(lang, "share_location_button"), request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder=_t(lang, "location_placeholder"),
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
    lang = _lang(user)

    agent.reset_conversation(user.id)
    agent.update_profile(user.id, name=user.first_name, onboarding_complete=False)

    await _send(
        update,
        _t(lang, "greeting", name=user.first_name),
        reply_markup=_category_keyboard(lang),
    )


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
