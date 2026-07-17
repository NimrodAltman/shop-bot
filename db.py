"""
db.py
=====
Storage layer for the appliance advisor bot.

Two backends, one interface:

* **In-memory** (default) — plain dicts. Nothing to install, nothing to
  configure; clone the repo and it runs.
* **Supabase** — used automatically when both ``SUPABASE_URL`` and
  ``SUPABASE_KEY`` are set in the environment and the ``supabase`` package is
  importable. Falls back to in-memory if the client cannot be created.

Every function below works identically against either backend, so the rest of
the app never asks which one is active.

Expected Supabase tables (see README for the SQL):
    users(user_id text pk, name text, city text, lat float8, lng float8,
          budget int, category text, created_at timestamptz)
    orders(id text pk, user_id text, product_id text, store_id text,
           quantity int, status text, created_at timestamptz)
    reviews(id text pk, user_id text, product_id text, rating int,
            comment text, created_at timestamptz)
    conversations(user_id text pk, history jsonb, updated_at timestamptz)
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Backend selection ─────────────────────────────────────────────────────────
_supabase = None

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client

        _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Storage backend: Supabase")
    except Exception as exc:  # pragma: no cover - depends on env
        logger.warning("Supabase init failed (%s) — falling back to in-memory", exc)
        _supabase = None
else:
    logger.info("Storage backend: in-memory (set SUPABASE_URL/SUPABASE_KEY to persist)")


def using_supabase() -> bool:
    """True when writes are persisted to Supabase rather than process memory."""
    return _supabase is not None


# ── In-memory stores ──────────────────────────────────────────────────────────
_users: dict[str, dict] = {}
_orders: dict[str, dict] = {}
_reviews: dict[str, dict] = {}
_conversations: dict[str, list] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ── Users ─────────────────────────────────────────────────────────────────────
def get_user(user_id: str) -> dict | None:
    """Return the stored profile for a user, or None if they are unknown."""
    user_id = str(user_id)
    if _supabase:
        try:
            res = _supabase.table("users").select("*").eq("user_id", user_id).execute()
            return res.data[0] if res.data else None
        except Exception as exc:
            logger.error("get_user failed: %s", exc)
            return None
    return _users.get(user_id)


def save_user(user_id: str, **fields) -> dict:
    """Create or update a user profile.

    Only the fields passed in are touched; existing values are preserved.
    Returns the full profile after the write.
    """
    user_id = str(user_id)
    existing = get_user(user_id) or {"user_id": user_id, "created_at": _now()}
    profile = {**existing, **fields, "user_id": user_id}

    if _supabase:
        try:
            _supabase.table("users").upsert(profile).execute()
            return profile
        except Exception as exc:
            logger.error("save_user failed: %s", exc)
            return profile

    _users[user_id] = profile
    return profile


# ── Orders ────────────────────────────────────────────────────────────────────
def create_order(
    user_id: str,
    product_id: str,
    store_id: str,
    quantity: int = 1,
) -> dict:
    """Record a new order in ``pending`` status and return it."""
    order = {
        "id": _new_id("ord"),
        "user_id": str(user_id),
        "product_id": product_id,
        "store_id": store_id,
        "quantity": quantity,
        "status": "pending",
        "created_at": _now(),
    }

    if _supabase:
        try:
            _supabase.table("orders").insert(order).execute()
            return order
        except Exception as exc:
            logger.error("create_order failed: %s", exc)
            return order

    _orders[order["id"]] = order
    return order


def get_order(order_id: str) -> dict | None:
    """Return a single order by id, or None if there is no such order."""
    if _supabase:
        try:
            res = _supabase.table("orders").select("*").eq("id", order_id).execute()
            return res.data[0] if res.data else None
        except Exception as exc:
            logger.error("get_order failed: %s", exc)
            return None
    return _orders.get(order_id)


def get_user_orders(user_id: str) -> list:
    """Return every order placed by a user, newest first."""
    user_id = str(user_id)
    if _supabase:
        try:
            res = (
                _supabase.table("orders")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )
            return res.data or []
        except Exception as exc:
            logger.error("get_user_orders failed: %s", exc)
            return []
    orders = [o for o in _orders.values() if o["user_id"] == user_id]
    return sorted(orders, key=lambda o: o["created_at"], reverse=True)


def update_order_status(order_id: str, status: str) -> dict | None:
    """Set an order's status. Returns the updated order, or None if missing."""
    if _supabase:
        try:
            res = (
                _supabase.table("orders")
                .update({"status": status})
                .eq("id", order_id)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception as exc:
            logger.error("update_order_status failed: %s", exc)
            return None
    order = _orders.get(order_id)
    if not order:
        return None
    order["status"] = status
    return order


# ── Reviews ───────────────────────────────────────────────────────────────────
def create_review(user_id: str, product_id: str, rating: int, comment: str = "") -> dict:
    """Store a product review (rating is clamped to 1-5) and return it."""
    review = {
        "id": _new_id("rev"),
        "user_id": str(user_id),
        "product_id": product_id,
        "rating": max(1, min(5, int(rating))),
        "comment": comment,
        "created_at": _now(),
    }

    if _supabase:
        try:
            _supabase.table("reviews").insert(review).execute()
            return review
        except Exception as exc:
            logger.error("create_review failed: %s", exc)
            return review

    _reviews[review["id"]] = review
    return review


def get_product_reviews(product_id: str) -> list:
    """Return every review for a product, newest first."""
    if _supabase:
        try:
            res = (
                _supabase.table("reviews")
                .select("*")
                .eq("product_id", product_id)
                .order("created_at", desc=True)
                .execute()
            )
            return res.data or []
        except Exception as exc:
            logger.error("get_product_reviews failed: %s", exc)
            return []
    reviews = [r for r in _reviews.values() if r["product_id"] == product_id]
    return sorted(reviews, key=lambda r: r["created_at"], reverse=True)


# ── Conversation history ──────────────────────────────────────────────────────
# The agent needs the running message list for each chat. Kept here so a
# Supabase-backed deployment survives a restart mid-conversation.
MAX_HISTORY_MESSAGES = 40


def get_history(user_id: str) -> list:
    """Return the stored Anthropic message list for a user (empty if none)."""
    user_id = str(user_id)
    if _supabase:
        try:
            res = (
                _supabase.table("conversations")
                .select("history")
                .eq("user_id", user_id)
                .execute()
            )
            return res.data[0]["history"] if res.data else []
        except Exception as exc:
            logger.error("get_history failed: %s", exc)
            return []
    return _conversations.get(user_id, [])


def save_history(user_id: str, history: list) -> None:
    """Persist a user's message list, trimmed to the most recent exchanges."""
    user_id = str(user_id)
    trimmed = history[-MAX_HISTORY_MESSAGES:]

    if _supabase:
        try:
            _supabase.table("conversations").upsert(
                {"user_id": user_id, "history": trimmed, "updated_at": _now()}
            ).execute()
        except Exception as exc:
            logger.error("save_history failed: %s", exc)
        return

    _conversations[user_id] = trimmed


def clear_history(user_id: str) -> None:
    """Drop a user's conversation history (used by /start and /reset)."""
    user_id = str(user_id)
    if _supabase:
        try:
            _supabase.table("conversations").delete().eq("user_id", user_id).execute()
        except Exception as exc:
            logger.error("clear_history failed: %s", exc)
        return
    _conversations.pop(user_id, None)
