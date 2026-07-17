"""
mock_data.py
============
Demo dataset for the appliance advisor bot: stores and products.

This is DEMO DATA, generated for end-to-end testing of the system.
It is the only module that needs to be replaced when connecting a real
catalog/inventory source (retailer API, partner feed, etc.). Keep the same
function signatures and return shapes and nothing else in the codebase changes
— every other layer (bot, agent, tools) talks to these functions, never to raw
data.
"""

# ── Stores ────────────────────────────────────────────────────────────────────
STORES = [
    {
        "id": "st_tlv_01",
        "name": "ElectroMax Tel Aviv",
        "address": "Dizengoff 120, Tel Aviv",
        "city": "Tel Aviv",
        "lat": 32.0793,
        "lng": 34.7741,
        "phone": "03-5551201",
        "hours": "Sun-Thu 09:00-21:00, Fri 09:00-14:00",
        "delivery": True,
        "pickup": True,
    },
    {
        "id": "st_tlv_02",
        "name": "HomeTech Ramat Aviv",
        "address": "Einstein 40, Tel Aviv",
        "city": "Tel Aviv",
        "lat": 32.1133,
        "lng": 34.8044,
        "phone": "03-5559930",
        "hours": "Sun-Thu 10:00-20:00, Fri 09:00-13:00",
        "delivery": True,
        "pickup": True,
    },
    {
        "id": "st_hfa_01",
        "name": "ElectroMax Haifa",
        "address": "HaNassi 55, Haifa",
        "city": "Haifa",
        "lat": 32.8156,
        "lng": 34.9892,
        "phone": "04-5552210",
        "hours": "Sun-Thu 09:00-20:00, Fri 09:00-14:00",
        "delivery": True,
        "pickup": True,
    },
    {
        "id": "st_jlm_01",
        "name": "SmartHome Jerusalem",
        "address": "Yafo 97, Jerusalem",
        "city": "Jerusalem",
        "lat": 31.7857,
        "lng": 35.2073,
        "phone": "02-5553340",
        "hours": "Sun-Thu 09:00-19:00, Fri 09:00-13:00",
        "delivery": False,
        "pickup": True,
    },
    {
        "id": "st_bsh_01",
        "name": "ElectroMax Beer Sheva",
        "address": "Rager 22, Beer Sheva",
        "city": "Beer Sheva",
        "lat": 31.2530,
        "lng": 34.7915,
        "phone": "08-5554450",
        "hours": "Sun-Thu 09:00-20:00, Fri 09:00-14:00",
        "delivery": True,
        "pickup": True,
    },
    {
        "id": "st_hrz_01",
        "name": "HomeTech Herzliya",
        "address": "Sokolov 15, Herzliya",
        "city": "Herzliya",
        "lat": 32.1624,
        "lng": 34.8447,
        "phone": "09-5556670",
        "hours": "Sun-Thu 10:00-21:00, Fri 09:00-14:00",
        "delivery": True,
        "pickup": False,
    },
]

# ── Products ──────────────────────────────────────────────────────────────────
# category: tv | air_conditioner | refrigerator | washing_machine | microwave
PRODUCTS = [
    # ---- TVs ----
    {
        "id": "p_tv_01",
        "name": "Samsung 55\" Crystal UHD 4K",
        "category": "tv",
        "brand": "Samsung",
        "price": 1890,
        "rating": 4.5,
        "rating_count": 312,
        "energy_rating": "B",
        "specs": {"screen_size_inch": 55, "resolution": "4K", "smart_tv": True, "refresh_hz": 60},
        "description": "Solid all-round 4K TV for a living room. Great value for the price.",
        "best_for": ["living room", "general use", "budget conscious"],
        "available_at": ["st_tlv_01", "st_hfa_01", "st_bsh_01"],
    },
    {
        "id": "p_tv_02",
        "name": "LG 65\" OLED evo C4",
        "category": "tv",
        "brand": "LG",
        "price": 6490,
        "rating": 4.9,
        "rating_count": 178,
        "energy_rating": "A",
        "specs": {"screen_size_inch": 65, "resolution": "4K", "smart_tv": True, "refresh_hz": 120},
        "description": "Premium OLED with perfect blacks and 120Hz — excellent for movies and gaming.",
        "best_for": ["home cinema", "gaming", "premium"],
        "available_at": ["st_tlv_02", "st_hrz_01"],
    },
    {
        "id": "p_tv_03",
        "name": "Hisense 43\" FHD Smart",
        "category": "tv",
        "brand": "Hisense",
        "price": 899,
        "rating": 4.0,
        "rating_count": 456,
        "energy_rating": "C",
        "specs": {"screen_size_inch": 43, "resolution": "FHD", "smart_tv": True, "refresh_hz": 60},
        "description": "Compact and affordable. Good for a bedroom or a small space.",
        "best_for": ["bedroom", "small room", "budget conscious"],
        "available_at": ["st_tlv_01", "st_jlm_01", "st_bsh_01"],
    },

    # ---- Air conditioners ----
    {
        "id": "p_ac_01",
        "name": "Electra Inverter 12K",
        "category": "air_conditioner",
        "brand": "Electra",
        "price": 2790,
        "rating": 4.4,
        "rating_count": 289,
        "energy_rating": "A",
        "specs": {"btu": 12000, "room_size_sqm": 20, "inverter": True, "wifi": True},
        "description": "Efficient inverter unit for a standard room. Quiet and economical.",
        "best_for": ["bedroom", "small living room", "energy saving"],
        "available_at": ["st_tlv_01", "st_hfa_01", "st_jlm_01"],
    },
    {
        "id": "p_ac_02",
        "name": "Tadiran Alpha 18K Inverter",
        "category": "air_conditioner",
        "brand": "Tadiran",
        "price": 4190,
        "rating": 4.7,
        "rating_count": 156,
        "energy_rating": "A",
        "specs": {"btu": 18000, "room_size_sqm": 32, "inverter": True, "wifi": True},
        "description": "Powerful inverter for large open spaces. Strong cooling with low noise.",
        "best_for": ["large living room", "open space", "energy saving"],
        "available_at": ["st_tlv_02", "st_hrz_01", "st_bsh_01"],
    },
    {
        "id": "p_ac_03",
        "name": "Tornado Basic 9K",
        "category": "air_conditioner",
        "brand": "Tornado",
        "price": 1690,
        "rating": 3.9,
        "rating_count": 512,
        "energy_rating": "C",
        "specs": {"btu": 9000, "room_size_sqm": 14, "inverter": False, "wifi": False},
        "description": "Entry-level unit for a small room. No frills, low price.",
        "best_for": ["small bedroom", "budget conscious"],
        "available_at": ["st_bsh_01", "st_jlm_01"],
    },

    # ---- Refrigerators ----
    {
        "id": "p_fr_01",
        "name": "Samsung 4-Door French Door 550L",
        "category": "refrigerator",
        "brand": "Samsung",
        "price": 7990,
        "rating": 4.8,
        "rating_count": 94,
        "energy_rating": "A",
        "specs": {"capacity_liters": 550, "doors": 4, "no_frost": True, "water_dispenser": True},
        "description": "Spacious 4-door fridge for a large family. Premium build with water dispenser.",
        "best_for": ["large family", "premium"],
        "available_at": ["st_tlv_02", "st_hrz_01"],
    },
    {
        "id": "p_fr_02",
        "name": "Beko Top-Freezer 375L",
        "category": "refrigerator",
        "brand": "Beko",
        "price": 2290,
        "rating": 4.2,
        "rating_count": 233,
        "energy_rating": "B",
        "specs": {"capacity_liters": 375, "doors": 2, "no_frost": True, "water_dispenser": False},
        "description": "Reliable mid-size fridge. Good fit for a couple or a small family.",
        "best_for": ["small family", "couple", "budget conscious"],
        "available_at": ["st_tlv_01", "st_hfa_01", "st_bsh_01", "st_jlm_01"],
    },

    # ---- Washing machines ----
    {
        "id": "p_wm_01",
        "name": "Bosch Serie 6 9kg 1400rpm",
        "category": "washing_machine",
        "brand": "Bosch",
        "price": 3490,
        "rating": 4.8,
        "rating_count": 201,
        "energy_rating": "A",
        "specs": {"capacity_kg": 9, "rpm": 1400, "steam": True, "quiet_db": 50},
        "description": "Quiet, durable and efficient. A long-term investment for a busy household.",
        "best_for": ["family", "quiet operation", "energy saving"],
        "available_at": ["st_tlv_01", "st_tlv_02", "st_hrz_01"],
    },
    {
        "id": "p_wm_02",
        "name": "Candy 7kg 1000rpm",
        "category": "washing_machine",
        "brand": "Candy",
        "price": 1490,
        "rating": 3.8,
        "rating_count": 377,
        "energy_rating": "C",
        "specs": {"capacity_kg": 7, "rpm": 1000, "steam": False, "quiet_db": 62},
        "description": "Basic and cheap. Does the job for one or two people.",
        "best_for": ["single", "couple", "budget conscious"],
        "available_at": ["st_bsh_01", "st_jlm_01", "st_hfa_01"],
    },

    # ---- Microwaves ----
    {
        "id": "p_mw_01",
        "name": "Sharp 25L Digital",
        "category": "microwave",
        "brand": "Sharp",
        "price": 549,
        "rating": 4.3,
        "rating_count": 188,
        "energy_rating": "B",
        "specs": {"capacity_liters": 25, "watts": 900, "grill": True},
        "description": "Roomy microwave with a grill function. Good everyday choice.",
        "best_for": ["family", "general use"],
        "available_at": ["st_tlv_01", "st_hfa_01", "st_hrz_01", "st_bsh_01"],
    },
]

CATEGORY_LABELS = {
    "tv": "TV",
    "air_conditioner": "Air Conditioner",
    "refrigerator": "Refrigerator",
    "washing_machine": "Washing Machine",
    "microwave": "Microwave",
}


# ── Accessors (the stable interface used by the rest of the app) ──────────────
def get_all_stores() -> list:
    """Return every store in the catalog."""
    return STORES


def get_store_by_id(store_id: str) -> dict | None:
    """Return a single store by its id, or None if it does not exist."""
    return next((s for s in STORES if s["id"] == store_id), None)


def get_stores_by_city(city: str) -> list:
    """Return stores whose city matches (case-insensitive, partial match)."""
    if not city:
        return STORES
    needle = city.strip().lower()
    return [s for s in STORES if needle in s["city"].lower()]


def get_all_products() -> list:
    """Return every product in the catalog."""
    return PRODUCTS


def get_product_by_id(product_id: str) -> dict | None:
    """Return a single product by its id, or None if it does not exist."""
    return next((p for p in PRODUCTS if p["id"] == product_id), None)


def get_products_by_store(store_id: str) -> list:
    """Return the products carried by a given store."""
    return [p for p in PRODUCTS if store_id in p.get("available_at", [])]
