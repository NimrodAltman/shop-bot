"""
i18n.py
=======
Localization layer for the bot's fixed system strings.

The agent itself (agent.py) already replies in the user's language via the
system prompt — that path needs no code here. This module handles what
doesn't go through the agent: onboarding, confirmations, errors, and the
keyboards' own labels.

Supported languages: English (en), Hebrew (he), Arabic (ar), Russian (ru).

Language detection is based on the script of the incoming message. A message
with no letters at all (digits, emoji) carries no signal, so the caller
should fall back to whatever language is already on the user's profile.
"""

from __future__ import annotations

import re

from data.mock_data import CATEGORY_LABELS

DEFAULT_LANG = "en"
SUPPORTED_LANGS = ("en", "he", "ru", "ar")

_HEBREW = re.compile(r"[֐-׿]")
_ARABIC = re.compile(r"[؀-ۿ]")
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_LATIN = re.compile(r"[A-Za-z]")


def detect_lang(text: str) -> str | None:
    """Guess a language from the script used in ``text``.

    Returns None when there's no letter at all (digits/emoji only) — the
    caller should keep the existing preference in that case.
    """
    if not text:
        return None
    if _HEBREW.search(text):
        return "he"
    if _ARABIC.search(text):
        return "ar"
    if _CYRILLIC.search(text):
        return "ru"
    if _LATIN.search(text):
        return "en"
    return None


def resolve_lang(profile: dict | None, telegram_lang_code: str | None = None) -> str:
    """Resolve which language to use for the fixed UI strings.

    A language override on the profile (set by ``detect_lang`` on a prior
    free-text message) wins; otherwise fall back to the Telegram client's
    own language, then the default.
    """
    if profile:
        override = profile.get("lang")
        if override in SUPPORTED_LANGS:
            return override
    code = (telegram_lang_code or "").split("-")[0].lower()
    if code in SUPPORTED_LANGS:
        return code
    return DEFAULT_LANG


def t(lang: str, key: str, **kwargs) -> str:
    """Return a translated string, falling back to the default language."""
    entry = STRINGS[key]
    text = entry.get(lang) or entry[DEFAULT_LANG]
    return text.format(**kwargs) if kwargs else text


def category_label(key: str, lang: str) -> str:
    labels = CATEGORY_LABELS_BY_LANG.get(lang, CATEGORY_LABELS_BY_LANG[DEFAULT_LANG])
    return labels.get(key, key)


# ── Category labels, per language ──────────────────────────────────────────
CATEGORY_LABELS_BY_LANG = {
    "en": CATEGORY_LABELS,
    "he": {
        "tv": "טלוויזיה",
        "air_conditioner": "מזגן",
        "refrigerator": "מקרר",
        "washing_machine": "מכונת כביסה",
        "microwave": "מיקרוגל",
    },
    "ru": {
        "tv": "Телевизор",
        "air_conditioner": "Кондиционер",
        "refrigerator": "Холодильник",
        "washing_machine": "Стиральная машина",
        "microwave": "Микроволновая печь",
    },
    "ar": {
        "tv": "تلفاز",
        "air_conditioner": "مكيف هواء",
        "refrigerator": "ثلاجة",
        "washing_machine": "غسالة",
        "microwave": "ميكروويف",
    },
}

# (internal budget ceiling, label per language)
BUDGET_OPTIONS = [
    {"value": 1000, "en": "Under ₪1,000", "he": "עד ₪1,000",
     "ru": "До ₪1,000", "ar": "أقل من ₪1,000"},
    {"value": 3000, "en": "₪1,000–3,000", "he": "₪1,000–3,000",
     "ru": "₪1,000–3,000", "ar": "₪1,000–3,000"},
    {"value": 5000, "en": "₪3,000–5,000", "he": "₪3,000–5,000",
     "ru": "₪3,000–5,000", "ar": "₪3,000–5,000"},
    {"value": 99999, "en": "₪5,000+", "he": "₪5,000 ומעלה",
     "ru": "От ₪5,000", "ar": "أكثر من ₪5,000"},
]

# Free-text signals that the user is asking about stores/location without
# having shared one yet — used to re-offer the location-share keyboard
# outside the onboarding flow.
LOCATION_KEYWORDS = {
    "en": ["store", "stores", "shop", "nearby", "near me", "where can i"],
    "he": ["חנות", "חנויות", "קרוב", "קרובים", "איפה אפשר"],
    "ru": ["магазин", "магазины", "рядом", "где можно"],
    "ar": ["متجر", "متاجر", "قريب", "أين يمكن"],
}


STRINGS = {
    "greeting": {
        "en": (
            "Hi *{name}*! I'm *ShopBot* 🛒\n\n"
            "I'm your personal shopping assistant for home appliances. I can:\n"
            "✅ Find nearby stores that have what you need\n"
            "✅ Give you personalized product recommendations\n"
            "✅ Answer questions about specs and energy ratings\n\n"
            "👇 A couple of quick questions to tailor this to you:"
        ),
        "he": (
            "היי *{name}*! אני *ShopBot* 🛒\n\n"
            "העוזר האישי שלך לבחירת מכשירי חשמל. אני יכול:\n"
            "✅ למצוא חנויות קרובות עם מה שאתה מחפש\n"
            "✅ לתת המלצות מוצר מותאמות אישית\n"
            "✅ לענות על שאלות לגבי מפרטים ודירוגי אנרגיה\n\n"
            "👇 כמה שאלות קצרות כדי להתאים את זה בדיוק לך:"
        ),
        "ru": (
            "Привет, *{name}*! Я *ShopBot* 🛒\n\n"
            "Я ваш персональный помощник по выбору бытовой техники. Я могу:\n"
            "✅ Найти ближайшие магазины с нужным товаром\n"
            "✅ Дать персональные рекомендации по товарам\n"
            "✅ Ответить на вопросы о характеристиках и энергоэффективности\n\n"
            "👇 Пара быстрых вопросов, чтобы подобрать это именно для вас:"
        ),
        "ar": (
            "مرحبًا *{name}*! أنا *ShopBot* 🛒\n\n"
            "أنا مساعدك الشخصي لاختيار الأجهزة المنزلية. يمكنني:\n"
            "✅ إيجاد متاجر قريبة يتوفر لديها ما تحتاجه\n"
            "✅ تقديم توصيات منتجات مخصصة لك\n"
            "✅ الإجابة عن أسئلة حول المواصفات وتصنيفات كفاءة الطاقة\n\n"
            "👇 بضعة أسئلة سريعة لتخصيص هذا لك:"
        ),
    },
    "welcome_back": {
        "en": "Welcome back, *{name}*! 👋 How can I help you today?",
        "he": "ברוך שובך, *{name}*! 👋 איך אפשר לעזור היום?",
        "ru": "С возвращением, *{name}*! 👋 Чем могу помочь сегодня?",
        "ar": "أهلاً بعودتك يا *{name}*! 👋 كيف يمكنني مساعدتك اليوم؟",
    },
    "ask_category": {
        "en": "What are you shopping for?",
        "he": "מה מחפשים?",
        "ru": "Что вы ищете?",
        "ar": "عن ماذا تبحث؟",
    },
    "category_other": {
        "en": "Something else / just browsing",
        "he": "משהו אחר / רק מסתכלים",
        "ru": "Что-то другое / просто смотрю",
        "ar": "شيء آخر / أتصفح فقط",
    },
    "category_any_label": {
        "en": "an appliance",
        "he": "מכשיר חשמלי",
        "ru": "бытовую технику",
        "ar": "جهاز منزلي",
    },
    "category_confirm": {
        "en": "Great — looking for {label}. 👌",
        "he": "מעולה — מחפשים {label}. 👌",
        "ru": "Отлично — ищем {label}. 👌",
        "ar": "رائع — نبحث عن {label}. 👌",
    },
    "ask_budget": {
        "en": "What's your budget?",
        "he": "מה התקציב?",
        "ru": "Какой у вас бюджет?",
        "ar": "ما هي ميزانيتك؟",
    },
    "budget_no_limit": {
        "en": "No budget in mind",
        "he": "אין תקציב מוגדר",
        "ru": "Без ограничения бюджета",
        "ar": "لا توجد ميزانية محددة",
    },
    "budget_confirm_set": {
        "en": "Budget noted: up to ₪{budget:,}.",
        "he": "התקציב נקלט: עד ₪{budget:,}.",
        "ru": "Бюджет учтён: до ₪{budget:,}.",
        "ar": "تم تسجيل الميزانية: حتى ₪{budget:,}.",
    },
    "budget_confirm_none": {
        "en": "No problem.",
        "he": "אין בעיה.",
        "ru": "Хорошо.",
        "ar": "لا مشكلة.",
    },
    "ask_location": {
        "en": "Last thing — where are you? Share your location or just type your city.",
        "he": "עוד דבר אחד — איפה אתם נמצאים? שתפו מיקום או פשוט הקלידו את העיר.",
        "ru": "Последнее — где вы находитесь? Поделитесь местоположением или напишите город.",
        "ar": "آخر شيء — أين أنت؟ شارك موقعك أو اكتب اسم مدينتك فقط.",
    },
    "share_location_button": {
        "en": "📍 Share my location",
        "he": "📍 שיתוף המיקום שלי",
        "ru": "📍 Поделиться местоположением",
        "ar": "📍 مشاركة موقعي",
    },
    "location_placeholder": {
        "en": "…or just type your city",
        "he": "…או פשוט הקלידו את העיר",
        "ru": "…или просто напишите город",
        "ar": "…أو فقط اكتب اسم مدينتك",
    },
    "location_received": {
        "en": "Got your location 📍",
        "he": "קיבלתי את המיקום 📍",
        "ru": "Местоположение получено 📍",
        "ar": "تم استلام موقعك 📍",
    },
    "location_prompt_to_agent": {
        "en": "Which stores are near me, and what do you recommend?",
        "he": "אילו חנויות קרובות אליי, ומה אתם ממליצים?",
        "ru": "Какие магазины рядом со мной и что вы порекомендуете?",
        "ar": "ما هي المتاجر القريبة مني، وبماذا توصي؟",
    },
    "help": {
        "en": (
            "*What I can do*\n\n"
            "• Recommend an appliance for your needs and budget\n"
            "• Tell you which nearby store carries it\n"
            "• Place an order and check its status\n"
            "• Answer questions about specs and energy ratings\n\n"
            "Just tell me what you're looking for — or send /start to go through "
            "the guided flow again. Send /update to change just one saved answer "
            "(category, budget or city).\n\n"
            "_Note: this is a portfolio demo. The stores, stock and orders are "
            "realistic sample data, not a real retailer._"
        ),
        "he": (
            "*מה אני יכול לעשות*\n\n"
            "• להמליץ על מכשיר חשמלי לפי הצרכים והתקציב שלכם\n"
            "• להגיד לכם איזו חנות קרובה מחזיקה אותו\n"
            "• לבצע הזמנה ולבדוק את הסטטוס שלה\n"
            "• לענות על שאלות לגבי מפרטים ודירוגי אנרגיה\n\n"
            "פשוט תגידו לי מה אתם מחפשים — או שלחו /start כדי לעבור שוב על "
            "התהליך המודרך. שלחו /update כדי לשנות רק תשובה אחת (קטגוריה, "
            "תקציב או עיר).\n\n"
            "_הערה: זהו פרויקט הדגמה. החנויות, המלאי וההזמנות הם נתוני דוגמה "
            "ריאליסטיים, לא קמעונאי אמיתי._"
        ),
        "ru": (
            "*Что я умею*\n\n"
            "• Рекомендовать технику под ваши нужды и бюджет\n"
            "• Подсказать, в каком ближайшем магазине она есть\n"
            "• Оформить заказ и проверить его статус\n"
            "• Ответить на вопросы о характеристиках и энергоэффективности\n\n"
            "Просто напишите, что вы ищете — или отправьте /start, чтобы пройти "
            "процесс заново. Отправьте /update, чтобы изменить только один "
            "сохранённый ответ (категорию, бюджет или город).\n\n"
            "_Обратите внимание: это демо-проект для портфолио. Магазины, товары "
            "и заказы — реалистичные демонстрационные данные, а не настоящий продавец._"
        ),
        "ar": (
            "*ما الذي يمكنني فعله*\n\n"
            "• التوصية بجهاز يناسب احتياجاتك وميزانيتك\n"
            "• إخبارك بأقرب متجر يتوفر لديه\n"
            "• تنفيذ طلب والتحقق من حالته\n"
            "• الإجابة عن أسئلة حول المواصفات وتصنيفات كفاءة الطاقة\n\n"
            "فقط أخبرني بما تبحث عنه — أو أرسل /start للمرور بالعملية الموجهة "
            "مرة أخرى. أرسل /update لتغيير إجابة واحدة فقط (الفئة، الميزانية، "
            "أو المدينة).\n\n"
            "_ملاحظة: هذا مشروع تجريبي لملف أعمال. المتاجر والمخزون والطلبات "
            "بيانات عرض واقعية، وليست تاجر تجزئة حقيقي._"
        ),
    },
    "reset": {
        "en": "Fresh start — what are you looking for? 🛒",
        "he": "התחלה חדשה — מה אתם מחפשים? 🛒",
        "ru": "Начнём заново — что вы ищете? 🛒",
        "ar": "بداية جديدة — عن ماذا تبحث؟ 🛒",
    },
    "update_menu_prompt": {
        "en": "What would you like to update?",
        "he": "מה תרצו לעדכן?",
        "ru": "Что вы хотите обновить?",
        "ar": "ما الذي تود تحديثه؟",
    },
    "update_field_category": {
        "en": "Category",
        "he": "קטגוריה",
        "ru": "Категория",
        "ar": "الفئة",
    },
    "update_field_budget": {
        "en": "Budget",
        "he": "תקציב",
        "ru": "Бюджет",
        "ar": "الميزانية",
    },
    "update_field_location": {
        "en": "City / location",
        "he": "עיר / מיקום",
        "ru": "Город / местоположение",
        "ar": "المدينة / الموقع",
    },
}
