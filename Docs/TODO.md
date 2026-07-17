# TODO / Roadmap

Status of the project and what's left. Updated 2026-07-17.

## Status

The five layers are written and the repo is live. The catalog, storage and tool
layers are verified by direct execution. **The agent loop has not been exercised
end-to-end yet** — that needs credentials (see below).

| Layer | State |
|---|---|
| `data/mock_data.py` | ✅ Done — 6 stores, 11 products |
| `db.py` | ✅ Done, tested — in-memory verified; Supabase path untested |
| `mcp_server.py` | ✅ Done, tested — all 10 tools + error paths |
| `agent.py` | ⚠️ Written, imports clean — **loop never run** (no API key) |
| `main.py` | ⚠️ Written, starts cleanly — **handlers never driven by a real bot** |
| Docs | ✅ Done — README, architecture, data model, deployment |

### What was actually verified

- **Storage** — profile merge preserves existing fields; review ratings clamp to
  1–5; history saves, reads and clears; backend falls back to in-memory when
  Supabase is not configured.
- **Tools** — budget filtering; haversine distances (0.0 km at a store's own
  coordinates, 11.4 km to Herzliya); case-insensitive city matching; free-text
  `need` matching; order validation rejects a store that doesn't carry the
  product and returns the ones that do; every error path returns a dict rather
  than raising; the tool schema is unique and JSON-serializable.
- **Bot startup** — `run_polling()` reaches Telegram's `getMe` and fails only on
  the (deliberately fake) token, with no event-loop error. Guard clauses exit
  cleanly when credentials are missing. Keyboards build correctly; the message
  splitter chunks past Telegram's 4,096-character cap.

### What was not verified

- Any call to the Anthropic API. The tool-use loop, the system prompt's
  behavior, and prompt caching are all unexercised.
- Any Telegram handler running against a real bot.
- The Supabase code path (needs a project + the tables).

---

## Next up

### 1. Run it end-to-end — **blocks everything below**

Needs two credentials in `.env`:

- `TELEGRAM_TOKEN` — [@BotFather](https://t.me/BotFather) → `/newbot`
- `ANTHROPIC_API_KEY` — [console.anthropic.com](https://console.anthropic.com)

Then `python main.py` and walk the flow:

- [ ] `/start` → category → budget → location, profile saved at each step
- [ ] Recommendations respect the budget and explain the fit
- [ ] Location sharing returns genuinely nearby stores
- [ ] City name (typed instead of GPS) works
- [ ] Order flow: confirm → `place_order` → order id → `get_order_status`
- [ ] Ordering from a store that doesn't stock the item is refused gracefully
- [ ] Reviews save and read back
- [ ] A general question ("what's a good energy rating?") answers without tools
- [ ] Replies come back in the language the user wrote in
- [ ] Asked whether stores are real, the bot says it's demo data
- [ ] `/reset` clears context; `/help` reads correctly

### 2. Screenshots for the README

The README has no screenshots — the one gap against the original plan. Capture
once the bot runs:

- [ ] `/start` onboarding with the inline keyboard
- [ ] A recommendation with reasoning
- [ ] Location sharing → nearby stores
- [ ] An order confirmation
- [ ] Commit to `Docs/images/` and embed in the README

### 3. Polish

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
