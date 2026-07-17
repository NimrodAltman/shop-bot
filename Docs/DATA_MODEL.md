# Data Model

Data shapes, the tool reference, and the Supabase schema.

## Catalog (demo data)

Lives in [`data/mock_data.py`](../data/mock_data.py) — **6 stores, 11 products**.
This is the only module that touches raw data. Everything else calls its
accessor functions, so connecting a real catalog means reimplementing this one
file with the same signatures.

### Store

```python
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
}
```

Id convention: `st_<city>_<n>`. Coordinates are real, so distance math produces
believable results.

### Product

```python
{
    "id": "p_tv_01",
    "name": 'Samsung 55" Crystal UHD 4K',
    "category": "tv",
    "brand": "Samsung",
    "price": 1890,                       # ILS
    "rating": 4.5,
    "rating_count": 312,
    "energy_rating": "B",                # A–C
    "specs": {"screen_size_inch": 55, "resolution": "4K",
              "smart_tv": True, "refresh_hz": 60},
    "description": "Solid all-round 4K TV for a living room...",
    "best_for": ["living room", "general use", "budget conscious"],
    "available_at": ["st_tlv_01", "st_hfa_01", "st_bsh_01"],
}
```

Id convention: `p_<category-abbrev>_<n>`.

Two fields do the recommendation work:
- **`specs`** is category-specific — TVs have `screen_size_inch`, air
  conditioners have `btu` and `room_size_sqm`, fridges have `capacity_liters`.
- **`best_for`** is what `recommend_products(need=...)` matches free text
  against, so "bedroom" or "gaming" finds the right product without the user
  naming a spec.

`available_at` holds store ids — the many-to-many between products and stores.

### Categories

| Key | Label |
|---|---|
| `tv` | TV |
| `air_conditioner` | Air Conditioner |
| `refrigerator` | Refrigerator |
| `washing_machine` | Washing Machine |
| `microwave` | Microwave |

### Accessors

| Function | Returns |
|---|---|
| `get_all_stores()` | Every store |
| `get_store_by_id(store_id)` | One store or `None` |
| `get_stores_by_city(city)` | Stores in a city (case-insensitive, partial) |
| `get_all_products()` | Every product |
| `get_product_by_id(product_id)` | One product or `None` |
| `get_products_by_store(store_id)` | Products a store carries |

---

## Tools

The 10 tools in [`mcp_server.py`](../mcp_server.py). Every one returns a dict
and never raises — failures come back as `{"error": "..."}`.

| Tool | Required | Optional | Returns |
|---|---|---|---|
| `recommend_products` | — | `category`, `max_price`, `min_rating`, `brand`, `need`, `limit` | `{products, count}` |
| `get_product_details` | `product_id` | — | `{product, available_at, user_reviews, ...}` |
| `find_product_stores` | `product_query` | `city`, `lat`, `lng`, `radius_km` | `{results, count}` |
| `find_nearby_stores` | `lat`, `lng` | `radius_km` (25) | `{stores, count}` — with `distance_km` |
| `get_stores_by_city` | `city` | — | `{stores, count}` |
| `get_store_inventory` | `store_id` | — | `{store, products, count}` |
| `place_order` | `user_id`, `product_id`, `store_id` | `quantity` (1) | `{success, order_id, total_price, ...}` |
| `get_order_status` | `order_id` | — | `{order_id, status, product_name, ...}` |
| `save_review` | `user_id`, `product_id`, `rating` | `comment` | `{success, review_id, ...}` |
| `get_reviews` | `product_id` | — | `{catalog_rating, user_reviews, user_average, count}` |

Notes:

- **Ranking** in `recommend_products` is by rating, then review count — a 4.8
  backed by 200 reviews outranks a 4.9 backed by 3.
- **`need` is a soft filter.** If nothing matches it, the other filters' results
  are returned rather than an empty list.
- **`user_id` is injected**, not taken from the model — see
  [ARCHITECTURE.md](ARCHITECTURE.md#user_id-is-injected-never-trusted).
- **List tools return a summary view** (id, name, category, brand, price,
  rating, energy rating). Full specs come from `get_product_details`.

---

## Storage

[`db.py`](../db.py) — in-memory dicts by default, Supabase when both
`SUPABASE_URL` and `SUPABASE_KEY` are set. The interface is identical either
way; no other module knows which is active. `using_supabase()` reports it.

### Records

```python
# user — created by /start, merged by save_user (existing fields preserved)
{"user_id": "12345", "name": "Nimrod", "city": "Tel Aviv",
 "lat": 32.07, "lng": 34.77, "budget": 3000, "category": "tv",
 "onboarding_complete": True, "created_at": "2026-07-17T..."}

# order — always created as "pending"
{"id": "ord_a1b2c3d4", "user_id": "12345", "product_id": "p_tv_01",
 "store_id": "st_tlv_01", "quantity": 1, "status": "pending",
 "created_at": "2026-07-17T..."}

# review — rating clamped to 1–5 on write
{"id": "rev_e5f6g7h8", "user_id": "12345", "product_id": "p_tv_01",
 "rating": 5, "comment": "Great picture", "created_at": "2026-07-17T..."}
```

Conversation history is stored per user and trimmed to the most recent
`MAX_HISTORY_MESSAGES = 40` messages, so a long chat can't grow the API call
without bound.

### API

| Area | Functions |
|---|---|
| Users | `get_user`, `save_user` |
| Orders | `create_order`, `get_order`, `get_user_orders`, `update_order_status` |
| Reviews | `create_review`, `get_product_reviews` |
| History | `get_history`, `save_history`, `clear_history` |

---

## Supabase schema

Only needed if you want persistence. Run this in the Supabase SQL editor, then
set `SUPABASE_URL` and `SUPABASE_KEY`.

```sql
create table if not exists users (
  user_id             text primary key,
  name                text,
  city                text,
  lat                 float8,
  lng                 float8,
  budget              int,
  category            text,
  onboarding_complete boolean default false,
  created_at          timestamptz default now()
);

create table if not exists orders (
  id         text primary key,
  user_id    text not null,
  product_id text not null,
  store_id   text not null,
  quantity   int  not null default 1,
  status     text not null default 'pending',
  created_at timestamptz default now()
);

create table if not exists reviews (
  id         text primary key,
  user_id    text not null,
  product_id text not null,
  rating     int  not null check (rating between 1 and 5),
  comment    text,
  created_at timestamptz default now()
);

create table if not exists conversations (
  user_id    text primary key,
  history    jsonb not null default '[]'::jsonb,
  updated_at timestamptz default now()
);

create index if not exists orders_user_id_idx     on orders  (user_id, created_at desc);
create index if not exists reviews_product_id_idx on reviews (product_id, created_at desc);
```

Stores and products are **not** tables — they come from `mock_data.py`. Only
user-generated state is persisted.

> **Security note:** these tables have no row-level security. This is fine for a
> demo where the bot is the only client, but a production deployment handling
> real user data would need RLS policies before exposing them.
