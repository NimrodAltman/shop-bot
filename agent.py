"""
agent.py
========
The AI core: system prompt + the tool-use loop.

Talks to the Anthropic API, hands Claude the tool schema from ``mcp_server``,
executes whatever tools it asks for, and loops until it produces an answer.

The system prompt is split into two blocks on purpose: a large stable block
(persona and rules) that is prompt-cached, followed by a small volatile block
(the user's profile and today's date). Caching is a prefix match, so anything
that changes per-user or per-day has to come *after* the cache breakpoint —
putting the date at the top would invalidate the cache on every request.
"""

from __future__ import annotations

import json
import logging
import os

import anthropic
from dotenv import load_dotenv

import db
from data.mock_data import CATEGORY_LABELS
from mcp_server import TOOLS_SCHEMA, execute_tool

load_dotenv()

logger = logging.getLogger(__name__)

MODEL_NAME = "claude-sonnet-5"
MAX_TOKENS = 8192
MAX_TOOL_ITERATIONS = 6

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Tools that act on behalf of a specific user. The user id is injected from the
# Telegram context rather than trusted from the model, so a confused turn can't
# place an order or leave a review under someone else's id.
_USER_SCOPED_TOOLS = {"place_order", "save_review"}


# ── System prompt ─────────────────────────────────────────────────────────────
_CATEGORY_LIST = "\n".join(f"- {key}: {label}" for key, label in CATEGORY_LABELS.items())

STABLE_SYSTEM = f"""You are "ShopBot", a home appliance advisor. You help people
choose an appliance that genuinely fits their needs and find a nearby store that
carries it.

## Persona
- Friendly, concise, practical. You sound like a knowledgeable salesperson who
  is not on commission.
- Short, readable messages. No walls of text.
- Emojis sparingly and only when they add something (🛒 📍 ✅).
- Never mention Telegram, buttons, or any interface detail. Talk about what the
  user wants, not about how the app works.

## Language
Detect the language the user writes in and always reply in that language.
If it is unclear, default to English.

## Your job
1. Understand what the user actually needs — the room, the household size, the
   budget, how they'll use it.
2. Recommend products that fit, and explain *why* each one fits them.
3. Tell them which nearby store carries it.
4. Place an order when they ask for one.
5. Answer general questions about appliances (specs, energy ratings, what to
   look for) directly, without tools, when no tool is needed.

## Product categories
{_CATEGORY_LIST}

## Tools
- recommend_products: your main tool. Filter by category, max_price, min_rating,
  brand, and a free-text `need` such as "bedroom", "large family", or "gaming".
- get_product_details: full specs, stores, and reviews for one product. Use it
  when the user asks about a specific item.
- get_stores_by_city: use this when the user names a city.
- find_nearby_stores: use this ONLY when you have actual coordinates. When a
  message contains "LOCATION_SHARED: lat,lng", those are the coordinates.
- find_product_stores: search by product name or brand and see who carries it.
- get_store_inventory: everything one specific store carries.
- place_order / get_order_status: ordering.
- save_review / get_reviews: user reviews.

## Tool rules
- Call recommend_products as soon as you know the category and roughly the
  budget. Don't interrogate the user first — recommend, then refine.
- Always pass max_price when the user has given you a budget. Never recommend
  something well over their budget without saying so explicitly.
- Product and store ids (p_tv_01, st_tlv_01) are internal. Use them in tool
  calls, never in your replies — use the names instead.
- Before place_order, the user must have explicitly confirmed the product, the
  store, and the price. If any of the three is unconfirmed, ask — don't assume.
- After showing recommendations, ask one clear follow-up question. Only one.
- If a tool returns an error, tell the user plainly what went wrong and offer a
  next step. Never invent a product, a store, a price, or an order number.

## Honesty rules
- This is a demo catalog. If asked whether the stores and stock are real, say
  plainly that this is demo data for a portfolio project.
- Never state a price, a spec, or availability that did not come from a tool.
- Don't upsell. If the cheap option genuinely fits their need, say so.
"""


def _build_system(user_id: str) -> list:
    """Stable cached block first, volatile per-user context after the breakpoint."""
    profile = db.get_user(user_id) or {}
    profile_text = json.dumps(profile, ensure_ascii=False) if profile else "{}"

    return [
        {
            "type": "text",
            "text": STABLE_SYSTEM,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": (
                f"## Current user\nuser_id: {user_id}\nprofile: {profile_text}\n\n"
                "If the profile is empty, ask what they're shopping for rather "
                "than guessing."
            ),
        },
    ]


# ── Tool-use loop ─────────────────────────────────────────────────────────────
def ask_agent(user_id: str, user_message: str) -> str:
    """Send a user message through the agent loop and return the reply text."""
    user_id = str(user_id)
    messages = db.get_history(user_id)
    messages.append({"role": "user", "content": user_message})

    system = _build_system(user_id)
    final_text = ""

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            response = client.messages.create(
                model=MODEL_NAME,
                max_tokens=MAX_TOKENS,
                system=system,
                tools=TOOLS_SCHEMA,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                messages=messages,
            )

            if response.stop_reason == "refusal":
                return "Sorry, I can't help with that one. Ask me about appliances and I'm all yours."

            if response.stop_reason == "tool_use":
                # The whole content list goes back, including thinking blocks —
                # dropping or editing them breaks the next turn.
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    tool_input = dict(block.input)
                    if block.name in _USER_SCOPED_TOOLS:
                        tool_input["user_id"] = user_id

                    result = execute_tool(block.name, tool_input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                            "is_error": "error" in result,
                        }
                    )

                # All results go back in a single user message — splitting them
                # teaches the model to stop calling tools in parallel.
                messages.append({"role": "user", "content": tool_results})
                continue

            final_text = "\n".join(b.text for b in response.content if b.type == "text")
            messages.append({"role": "assistant", "content": response.content})
            break
        else:
            logger.warning("Tool loop hit %s iterations for user %s", MAX_TOOL_ITERATIONS, user_id)
            final_text = "That turned into more digging than expected. Could you narrow it down a bit for me?"

    except anthropic.AuthenticationError:
        logger.error("Anthropic authentication failed — check ANTHROPIC_API_KEY")
        return "⚠️ The assistant isn't configured correctly. (Check the API key.)"
    except anthropic.RateLimitError:
        logger.warning("Anthropic rate limit hit")
        return "⏳ I'm a bit overloaded right now. Try again in a moment?"
    except anthropic.APIConnectionError:
        logger.error("Could not reach the Anthropic API")
        return "📡 I couldn't reach the assistant service. Check your connection and try again."
    except Exception as exc:
        logger.exception("Unexpected agent error: %s", exc)
        return "Something went wrong on my end. Try again in a moment 🙏"

    if not final_text:
        final_text = "I didn't quite catch that — could you rephrase?"

    db.save_history(user_id, messages)
    return final_text


# ── Profile helpers (used by the Telegram onboarding flow) ────────────────────
def get_profile(user_id: str) -> dict:
    """Return the stored profile for a user."""
    return db.get_user(user_id) or {}


def update_profile(user_id: str, **fields) -> dict:
    """Merge fields into a user's profile."""
    return db.save_user(user_id, **fields)


def is_onboarded(user_id: str) -> bool:
    """True once the user has been through the /start flow."""
    return bool(get_profile(user_id).get("onboarding_complete"))


def reset_conversation(user_id: str) -> None:
    """Drop the conversation history (but keep the profile)."""
    db.clear_history(user_id)
