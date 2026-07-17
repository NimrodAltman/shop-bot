"""
mcp_server.py
=============
Local MCP-style tool layer: the bridge between the AI agent and the data.

Two things live here:

* ``TOOLS_SCHEMA`` — the tool definitions handed to the Anthropic API.
* ``execute_tool`` — the dispatcher the agent calls when Claude requests a tool.

Every tool returns a plain dict and never raises: a failure comes back as
``{"error": ...}`` so the agent can tell the user something useful instead of
crashing the conversation.

The catalog is demo data (``data/mock_data.py``); orders and reviews go through
``db.py``, which persists to Supabase when configured.
"""

from __future__ import annotations

import math

import db
from data.mock_data import (
    CATEGORY_LABELS,
    get_all_products,
    get_all_stores,
    get_product_by_id,
    get_products_by_store,
    get_store_by_id,
)
from data.mock_data import get_stores_by_city as _stores_by_city

VALID_CATEGORIES = list(CATEGORY_LABELS.keys())


# ── Helpers ───────────────────────────────────────────────────────────────────
def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km between two lat/lng points."""
    radius_km = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    )
    return radius_km * 2 * math.asin(math.sqrt(a))


def _normalize(text: str) -> str:
    """Lowercase and strip punctuation so name matching survives typos in casing."""
    return "".join(c for c in (text or "").lower() if c.isalnum() or c.isspace()).strip()


def _summarize(product: dict) -> dict:
    """A compact product view — keeps tool results small enough to stay cheap."""
    return {
        "id": product["id"],
        "name": product["name"],
        "category": product["category"],
        "brand": product["brand"],
        "price": product["price"],
        "rating": product["rating"],
        "energy_rating": product["energy_rating"],
    }


# ── Store tools ───────────────────────────────────────────────────────────────
def find_nearby_stores(lat: float, lng: float, radius_km: float = 25) -> list:
    """Stores within ``radius_km`` of a point, nearest first."""
    results = []
    for store in get_all_stores():
        distance = _haversine(lat, lng, store["lat"], store["lng"])
        if distance <= radius_km:
            results.append({**store, "distance_km": round(distance, 1)})
    return sorted(results, key=lambda s: s["distance_km"])


def get_stores_by_city(city: str) -> list:
    """Stores in a city (case-insensitive, partial match)."""
    return _stores_by_city(city)


def get_store_inventory(store_id: str) -> dict:
    """Everything a given store carries, with the store's own details."""
    store = get_store_by_id(store_id)
    if not store:
        return {"error": f"No store with id '{store_id}'"}
    products = get_products_by_store(store_id)
    return {
        "store": store,
        "products": [_summarize(p) for p in products],
        "count": len(products),
    }


# ── Product tools ─────────────────────────────────────────────────────────────
def recommend_products(
    category: str | None = None,
    max_price: float | None = None,
    min_rating: float | None = None,
    brand: str | None = None,
    need: str | None = None,
    limit: int = 5,
) -> list:
    """Filter the catalog and rank the matches.

    Ranking is by rating, then by review count — a 4.8 backed by 200 reviews
    should outrank a 4.9 backed by 3.
    """
    results = get_all_products()

    if category:
        results = [p for p in results if p["category"] == category]
    if max_price is not None:
        results = [p for p in results if p["price"] <= max_price]
    if min_rating is not None:
        results = [p for p in results if p["rating"] >= min_rating]
    if brand:
        needle = _normalize(brand)
        results = [p for p in results if needle in _normalize(p["brand"])]
    if need:
        needle = _normalize(need)
        matched = [
            p
            for p in results
            if any(needle in _normalize(tag) for tag in p.get("best_for", []))
            or needle in _normalize(p.get("description", ""))
        ]
        # A need is a soft hint: if nothing matches it, keep the other filters'
        # results rather than telling the user we have nothing at all.
        if matched:
            results = matched

    results = sorted(results, key=lambda p: (-p["rating"], -p["rating_count"]))
    return results[:limit]


def get_product_details(product_id: str) -> dict:
    """Full details for one product, including where to buy it."""
    product = get_product_by_id(product_id)
    if not product:
        return {"error": f"No product with id '{product_id}'"}

    stores = [get_store_by_id(sid) for sid in product.get("available_at", [])]
    reviews = db.get_product_reviews(product_id)
    return {
        "product": product,
        "category_label": CATEGORY_LABELS.get(product["category"], product["category"]),
        "available_at": [s for s in stores if s],
        "user_reviews": reviews,
        "user_review_count": len(reviews),
    }


def find_product_stores(
    product_query: str,
    city: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float = 25,
) -> list:
    """Find products by name and report which stores carry them.

    Narrow by city, or by proximity when the user has shared a location.
    """
    needle = _normalize(product_query)
    matches = [p for p in get_all_products() if needle in _normalize(p["name"])]
    if not matches:
        matches = [p for p in get_all_products() if needle in _normalize(p["brand"])]

    if lat is not None and lng is not None:
        allowed = {s["id"]: s for s in find_nearby_stores(lat, lng, radius_km)}
    elif city:
        allowed = {s["id"]: s for s in get_stores_by_city(city)}
    else:
        allowed = {s["id"]: s for s in get_all_stores()}

    results = []
    for product in matches:
        stores = [allowed[sid] for sid in product.get("available_at", []) if sid in allowed]
        if stores:
            results.append({"product": _summarize(product), "stores": stores})
    return results


# ── Order tools ───────────────────────────────────────────────────────────────
def place_order(user_id: str, product_id: str, store_id: str, quantity: int = 1) -> dict:
    """Place an order after validating that the store actually carries the item."""
    product = get_product_by_id(product_id)
    if not product:
        return {"success": False, "error": f"No product with id '{product_id}'"}

    store = get_store_by_id(store_id)
    if not store:
        return {"success": False, "error": f"No store with id '{store_id}'"}

    if store_id not in product.get("available_at", []):
        return {
            "success": False,
            "error": f"{store['name']} does not carry {product['name']}",
            "available_at": [
                get_store_by_id(sid)["name"]
                for sid in product.get("available_at", [])
                if get_store_by_id(sid)
            ],
        }

    if quantity < 1:
        return {"success": False, "error": "Quantity must be at least 1"}

    order = db.create_order(user_id, product_id, store_id, quantity)
    return {
        "success": True,
        "order_id": order["id"],
        "status": order["status"],
        "product_name": product["name"],
        "store_name": store["name"],
        "quantity": quantity,
        "total_price": product["price"] * quantity,
        "pickup_available": store["pickup"],
        "delivery_available": store["delivery"],
    }


def get_order_status(order_id: str) -> dict:
    """Look up an existing order and expand it with product/store names."""
    order = db.get_order(order_id)
    if not order:
        return {"error": f"No order with id '{order_id}'"}

    product = get_product_by_id(order["product_id"])
    store = get_store_by_id(order["store_id"])
    return {
        "order_id": order["id"],
        "status": order["status"],
        "quantity": order["quantity"],
        "created_at": order["created_at"],
        "product_name": product["name"] if product else order["product_id"],
        "store_name": store["name"] if store else order["store_id"],
        "total_price": product["price"] * order["quantity"] if product else None,
    }


# ── Review tools ──────────────────────────────────────────────────────────────
def save_review(user_id: str, product_id: str, rating: int, comment: str = "") -> dict:
    """Store a user's review of a product they were shown."""
    product = get_product_by_id(product_id)
    if not product:
        return {"success": False, "error": f"No product with id '{product_id}'"}

    review = db.create_review(user_id, product_id, rating, comment)
    return {
        "success": True,
        "review_id": review["id"],
        "product_name": product["name"],
        "rating": review["rating"],
    }


def get_reviews(product_id: str) -> dict:
    """User-submitted reviews for a product, plus the catalog's own rating."""
    product = get_product_by_id(product_id)
    if not product:
        return {"error": f"No product with id '{product_id}'"}

    reviews = db.get_product_reviews(product_id)
    average = round(sum(r["rating"] for r in reviews) / len(reviews), 1) if reviews else None
    return {
        "product_name": product["name"],
        "catalog_rating": product["rating"],
        "catalog_rating_count": product["rating_count"],
        "user_reviews": reviews,
        "user_average": average,
        "count": len(reviews),
    }


# ── Tool schema (handed to the Anthropic API) ─────────────────────────────────
TOOLS_SCHEMA = [
    {
        "name": "find_nearby_stores",
        "description": (
            "Find appliance stores near a lat/lng point, nearest first. "
            "Use this when the user has shared their location."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude"},
                "lng": {"type": "number", "description": "Longitude"},
                "radius_km": {"type": "number", "description": "Search radius, default 25"},
            },
            "required": ["lat", "lng"],
        },
    },
    {
        "name": "get_stores_by_city",
        "description": (
            "Find stores in a named city. Use this when the user names a city "
            "instead of sharing a location."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name, e.g. 'Tel Aviv'"},
            },
            "required": ["city"],
        },
    },
    {
        "name": "get_store_inventory",
        "description": "List every product a specific store carries, by store_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string"},
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "recommend_products",
        "description": (
            "Recommend products, filtered by category, budget, rating, brand, or "
            "a free-text need such as 'bedroom' or 'gaming'. Results are ranked "
            "best-first. This is the main tool for matching a user to a product."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": VALID_CATEGORIES},
                "max_price": {"type": "number", "description": "Budget ceiling in ILS"},
                "min_rating": {"type": "number", "description": "Minimum rating, 1-5"},
                "brand": {"type": "string"},
                "need": {
                    "type": "string",
                    "description": "Free-text use case, e.g. 'bedroom', 'large family', 'gaming'",
                },
                "limit": {"type": "integer", "description": "Max results, default 5"},
            },
            "required": [],
        },
    },
    {
        "name": "get_product_details",
        "description": (
            "Full specs, description, stores carrying it, and user reviews for one "
            "product. Use after recommend_products when the user asks about a specific item."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "find_product_stores",
        "description": (
            "Search products by name or brand and return which stores carry them. "
            "Optionally narrow to a city, or to a radius around a lat/lng."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_query": {"type": "string", "description": "Product name or brand"},
                "city": {"type": "string"},
                "lat": {"type": "number"},
                "lng": {"type": "number"},
                "radius_km": {"type": "number", "description": "Default 25"},
            },
            "required": ["product_query"],
        },
    },
    {
        "name": "place_order",
        "description": (
            "Place an order for a product at a store. Only call this after the user "
            "has explicitly confirmed the product, the store, and the price."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "product_id": {"type": "string"},
                "store_id": {"type": "string"},
                "quantity": {"type": "integer", "description": "Default 1"},
            },
            "required": ["user_id", "product_id", "store_id"],
        },
    },
    {
        "name": "get_order_status",
        "description": "Check the status of an existing order by its order id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "save_review",
        "description": "Save a user's review of a product (rating 1-5, optional comment).",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "product_id": {"type": "string"},
                "rating": {"type": "integer", "description": "1-5"},
                "comment": {"type": "string"},
            },
            "required": ["user_id", "product_id", "rating"],
        },
    },
    {
        "name": "get_reviews",
        "description": "Get user reviews and the catalog rating for a product.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
            },
            "required": ["product_id"],
        },
    },
]


# ── Dispatcher ────────────────────────────────────────────────────────────────
def execute_tool(tool_name: str, tool_input: dict) -> dict:
    """Run a tool by name. Always returns a dict; never raises."""
    try:
        if tool_name == "find_nearby_stores":
            results = find_nearby_stores(
                lat=tool_input["lat"],
                lng=tool_input["lng"],
                radius_km=tool_input.get("radius_km", 25),
            )
            return {"stores": results, "count": len(results)}

        elif tool_name == "get_stores_by_city":
            results = get_stores_by_city(tool_input["city"])
            return {"stores": results, "count": len(results)}

        elif tool_name == "get_store_inventory":
            return get_store_inventory(tool_input["store_id"])

        elif tool_name == "recommend_products":
            results = recommend_products(
                category=tool_input.get("category"),
                max_price=tool_input.get("max_price"),
                min_rating=tool_input.get("min_rating"),
                brand=tool_input.get("brand"),
                need=tool_input.get("need"),
                limit=tool_input.get("limit", 5),
            )
            return {"products": results, "count": len(results)}

        elif tool_name == "get_product_details":
            return get_product_details(tool_input["product_id"])

        elif tool_name == "find_product_stores":
            results = find_product_stores(
                product_query=tool_input["product_query"],
                city=tool_input.get("city"),
                lat=tool_input.get("lat"),
                lng=tool_input.get("lng"),
                radius_km=tool_input.get("radius_km", 25),
            )
            return {"results": results, "count": len(results)}

        elif tool_name == "place_order":
            return place_order(
                user_id=tool_input["user_id"],
                product_id=tool_input["product_id"],
                store_id=tool_input["store_id"],
                quantity=tool_input.get("quantity", 1),
            )

        elif tool_name == "get_order_status":
            return get_order_status(tool_input["order_id"])

        elif tool_name == "save_review":
            return save_review(
                user_id=tool_input["user_id"],
                product_id=tool_input["product_id"],
                rating=tool_input["rating"],
                comment=tool_input.get("comment", ""),
            )

        elif tool_name == "get_reviews":
            return get_reviews(tool_input["product_id"])

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    except KeyError as exc:
        return {"error": f"Missing required parameter for {tool_name}: {exc}"}
    except Exception as exc:
        return {"error": f"{tool_name} failed: {exc}"}
