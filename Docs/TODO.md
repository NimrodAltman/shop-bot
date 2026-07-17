# TODO / Roadmap

Status of the project and what's left. Updated 2026-07-17.

## Status

All five layers are written and the repo is live. Storage and tools are
verified by direct execution. **The bot itself is now live and connected** with
real credentials — but the full conversation flow (recommendations, orders,
reviews through the Claude tool loop) hasn't been walked end-to-end yet. That
testing pass is scheduled for early next week.

| Layer | State |
|---|---|
| `data/mock_data.py` | ✅ Done — 6 stores, 11 products |
| `db.py` | ✅ Done, tested — in-memory verified; Supabase path untested |
| `mcp_server.py` | ✅ Done, tested — all 10 tools + error paths |
| `agent.py` | ✅ Done. Bot process connects live — **a full Claude turn (recommendation/order) not yet confirmed** |
| `main.py` | ✅ Done, running live. Onboarding auto-localizes to Hebrew/English — **confirmed working**; rest of the flow pending the checklist below |
| Docs | ✅ Done — README, architecture, data model, deployment, this file |

### What was actually verified

- **Storage** — profile merge preserves existing fields; review ratings clamp to
  1–5; history saves, reads and clears; backend falls back to in-memory when
  Supabase is not configured.
- **Tools** — budget filtering; haversine distances (0.0 km at a store's own
  coordinates, 11.4 km to Herzliya); case-insensitive city matching; free-text
  `need` matching; order validation rejects a store that doesn't carry the
  product and returns the ones that do; every error path returns a dict rather
  than raising; the tool schema is unique and JSON-serializable.
- **Bot connects live** — running with real `TELEGRAM_TOKEN` and
  `ANTHROPIC_API_KEY`, `run_polling()` reaches Telegram's `getMe` successfully
  (`Application started`, no event-loop error), as
  [@NimrodShopDemo_bot](https://t.me/NimrodShopDemo_bot).
- **Onboarding localization** — `/start`, the category and budget buttons, and
  the location prompt auto-detect the user's Telegram client language
  (`language_code`) and render in Hebrew or English with no manual switch.
  Confirmed live in Hebrew by the user. Free-text chat was already
  per-message language-detected by `agent.py`'s system prompt, independent of
  this change.

### What was not verified

- **A full conversation turn through Claude** — a recommendation, an order, a
  review. The bot connects and the onboarding UI renders correctly, but no tool
  call or agent reply has been confirmed yet.
- Prompt caching behavior in practice (only inspected structurally, not via
  `usage.cache_read_input_tokens` on a real request).
- The Supabase code path (needs a project + the tables).

---

## Next up

### 1. Full conversation testing — **in progress, scheduled early next week**

Credentials are already in `.env` and the bot is live. Checklist to walk through
`/start` onward:

- [x] Bot connects to Telegram with real credentials, no startup errors
- [x] `/start` onboarding UI renders in the user's language (Hebrew confirmed)
- [ ] Category → budget → location, profile saved at each step
- [ ] Recommendations respect the budget and explain the fit
- [ ] Location sharing returns genuinely nearby stores
- [ ] City name (typed instead of GPS) works
- [ ] Order flow: confirm → `place_order` → order id → `get_order_status`
- [ ] Ordering from a store that doesn't stock the item is refused gracefully
- [ ] Reviews save and read back
- [ ] A general question ("what's a good energy rating?") answers without tools
- [ ] Free-text replies come back in the language the user wrote in
- [ ] Asked whether stores are real, the bot says it's demo data
- [ ] `/reset` clears context; `/help` reads correctly

### 2. ~~Commit and push the localization change~~ — done

Pushed as `ce8eb27`, ahead of the original plan to wait for the full checklist
— the user wanted this backed up rather than sitting only on disk. The
checklist below is still open; nothing about pushing early changes that.

### 3. Rich message formatting — do this before screenshots

**Problem:** every agent reply currently ships as one flat paragraph — no
line breaks between products, no visual separation for the follow-up question
at the end, no per-category iconography. Telegram supports rich formatting;
right now the bot doesn't use any of it.

**Wanted:**
- Multi-product replies (`recommend_products` results, store inventories) shown
  as a real list — one product per line, not run-on prose.
- A category icon per product/store context, e.g.:

  | Category | Icon |
  |---|---|
  | `tv` | 📺 |
  | `air_conditioner` | ❄️ |
  | `refrigerator` | 🧊 |
  | `washing_machine` | 🧺 |
  | `microwave` | 📦 |

  (Also useful for stores: 📍 for a store line, 🛒 for an order confirmation,
  ⭐ for reviews — reuse the emoji already scattered through `agent.py`'s
  prompt, but apply them consistently instead of ad hoc.)
- The trailing follow-up question visually set apart from the body (its own
  line, not tacked onto the end of the last sentence).

**Why two files change together:** `agent.py` decides *what* to write,
`main.py` decides *how Telegram renders it* — fixing only one does nothing.

- [ ] `main.py`: pass `parse_mode="MarkdownV2"` (or `"Markdown"` — simpler,
      but Telegram's legacy mode is more forgiving of unescaped characters
      than `MarkdownV2`, which requires escaping `. ! - ( )` etc. in normal
      text) on agent replies in `_send()`, not just `/help`.
- [ ] `main.py`: wrap the send in try/except — a malformed markdown reply from
      the model (unmatched `*`/`_`) makes Telegram reject the message outright;
      fall back to plain text on a parse error instead of losing the reply.
- [ ] `agent.py`: add a formatting section to `STABLE_SYSTEM` — the category
      icon table above, "one product per line, bold the name," "put the
      follow-up question on its own line at the end," and which Markdown
      subset is safe for the chosen `parse_mode`.
- [ ] Re-run a few turns of the checklist above once this lands, since it
      changes what every reply looks like.

### 4. Screenshots for the README

The README has no screenshots — the one gap against the original plan. Capture
**after** the formatting work above, so they show the real experience:

- [ ] `/start` onboarding with the inline keyboard (Hebrew and/or English)
- [ ] A recommendation with reasoning — icons and a real list, not one paragraph
- [ ] Location sharing → nearby stores
- [ ] An order confirmation
- [ ] Commit to `Docs/images/` and embed in the README

### 5. Polish

- [ ] Add a `/myorders` command (`db.get_user_orders` exists and is unused)
- [ ] Set the bot's description and avatar via @BotFather
- [ ] Tune `output_config.effort` once real latency is observable — currently
      `medium`, chosen without measurement

---

## Later

### Testing
- [ ] `pytest` suite for `mcp_server.py` — the verification so far was ad-hoc
      scripts, not committed tests
- [ ] Fixtures for `db.py` covering both backends
- [ ] CI on push (`.github/workflows/`)

### Deployment
- [ ] Deploy to Railway as a **worker** (see [DEPLOYMENT.md](DEPLOYMENT.md))
- [ ] Put a live bot link in the README so a reader can try it in one click
- [ ] Only one instance may poll a token — do not scale past 1 replica

### Supabase
- [ ] Create a project, run the schema from [DATA_MODEL.md](DATA_MODEL.md)
- [ ] Verify the persistence path actually works
- [ ] Add row-level security before any real user data

### Product ideas
- [ ] Compare two products side by side
- [ ] Price-drop alerts (needs a scheduler)
- [ ] Store opening hours in recommendations ("open now")
- [ ] More categories: dishwasher, oven, dryer

---

## Known limitations

These are deliberate, not bugs.

| Limitation | Why |
|---|---|
| Catalog is demo data | Portfolio project — keeps it runnable by anyone, no scraping |
| Orders aren't real | Nothing is purchased; `place_order` records intent |
| In-memory storage loses data on restart | Two-env-var setup; Supabase is the opt-in fix |
| Polling, not webhooks | Simpler to run locally; a webhook rewrite is a different program |
| Single instance only | Telegram allows one poller per token |
