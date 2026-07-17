# Architecture

How ShopBot is put together, and why. For setup see the
[README](../README.md); for data shapes see [DATA_MODEL.md](DATA_MODEL.md).

## The layers

The system is five modules with one rule: **each layer only talks to the one
below it.**

```
main.py          Telegram — polling, onboarding, keyboards, location
   │
agent.py         Claude — system prompt, tool-use loop, error handling
   │
mcp_server.py    Tools — TOOLS_SCHEMA + execute_tool dispatcher
   │
   ├── data/mock_data.py    Catalog (stores, products)
   └── db.py                State (profiles, orders, reviews, history)
```

What this buys:

- **The bot knows nothing about appliances.** `main.py` never mentions a product
  or a price — it formats messages and forwards text. Replacing Telegram with
  Slack, WhatsApp or a web UI touches one file.
- **The tools know nothing about Telegram.** `mcp_server.py` takes dicts and
  returns dicts. It's testable without a bot token, which is how the whole tool
  layer was verified before a bot ever existed.
- **The catalog is one file.** Every other layer calls the accessor functions in
  `mock_data.py`, never raw lists. Real data means reimplementing that file with
  the same signatures.

## The tool-use loop

The heart of the agent, in `agent.py`:

```
user message
    │
    ▼
┌─────────────────────────────────┐
│ messages.create(               │
│   system, tools, messages )    │◄──────┐
└─────────────────────────────────┘       │
    │                                     │
    ├── stop_reason == "tool_use" ────────┤
    │      │                              │
    │      ├─ execute each tool           │
    │      ├─ append assistant content    │
    │      └─ append ALL tool_results ────┘
    │            (one user message)
    │
    └── otherwise ──► return the text
```

Three details that are easy to get wrong:

**Append the whole `response.content`, not just the text.** It carries the
`tool_use` blocks and any thinking blocks. Dropping or editing them breaks the
next turn.

**All tool results go back in a single user message.** Splitting them across
messages teaches the model to stop calling tools in parallel.

**The loop is bounded** (`MAX_TOOL_ITERATIONS = 6`). A model that keeps calling
tools forever would otherwise run up a bill in silence.

## The system prompt is split in two

Prompt caching is a **prefix match**: any byte that changes invalidates
everything after it. So the prompt is two blocks:

```python
system = [
    {"type": "text", "text": STABLE_SYSTEM,
     "cache_control": {"type": "ephemeral"}},   # ← cache breakpoint
    {"type": "text", "text": f"user_id: {user_id}\nprofile: {profile}"},
]
```

The stable block (persona, rules, tool guidance — ~3,000 chars) is identical for
every user on every request, so it caches. The volatile block (the user's
profile) sits **after** the breakpoint, where it invalidates nothing.

Reversing them — interpolating the profile or `datetime.now()` into the top of
the prompt — would mean a cache miss on every single request. This is the most
common way prompt caching is silently lost.

## Design decisions

| Decision | Why |
|---|---|
| **Telegram, not WhatsApp** | Free, no business verification, no 24h window, inline keyboards and native location sharing. The channel is one file. |
| **Mock data, not scraping** | Runnable by anyone who clones it. No legal grey area, nothing to break when a site changes. |
| **In-memory by default** | Two env vars to run. Supabase activates automatically when configured. |
| **`claude-sonnet-5`** | Good cost/performance for a chat bot with tool use. |
| **Manual tool loop** | The SDK's tool runner is in beta. A manual loop is ~30 lines and keeps the dependency surface small. |
| **`asyncio.to_thread` for the agent** | `ask_agent` is blocking and can take seconds. Called directly in an async handler it would freeze the event loop for every user. |
| **Two-tier localization** | Free-text chat is language-agnostic by construction — the system prompt tells Claude to detect and mirror the user's language, so it needs no code. The onboarding UI (buttons, `/start`, `/help`) never touches the agent, so it can't inherit that behavior; it's localized separately in `main.py` from Telegram's `language_code` (`he`/`he-IL` → Hebrew, else English). |

## Two bugs worth knowing about

Both were designed out on purpose.

### `run_polling()` must own the main thread

```python
asyncio.run(app.run_polling(...))   # ❌ inside a worker thread
app.run_polling(...)                # ✅ main thread
```

`run_polling()` is blocking and builds its own event loop. Wrapping it in
`asyncio.run()` inside a non-main thread fails with *"There is no current event
loop in thread 'Thread-1'"* and *"coroutine 'Updater.start_polling' was never
awaited"*. There is no threading here and no Flask — the call sits in `main()`
on the main thread.

### `user_id` is injected, never trusted

`place_order` and `save_review` act on behalf of a specific user. The model is
told the user id, but the id it sends is **overwritten** with the real one from
the Telegram context before the tool runs:

```python
if block.name in _USER_SCOPED_TOOLS:
    tool_input["user_id"] = user_id
```

Without this, a confused turn could place an order under someone else's id.
Tool inputs are model output — treat them as untrusted.

## Validation lives in the tools

`place_order` verifies that the store actually carries the product before
writing anything, and returns the stores that do when it doesn't:

```json
{
  "success": false,
  "error": "SmartHome Jerusalem does not carry Samsung 55\" Crystal UHD 4K",
  "available_at": ["ElectroMax Tel Aviv", "ElectroMax Haifa", "ElectroMax Beer Sheva"]
}
```

The agent then has something useful to say instead of an apology. **No tool ever
raises** — failures come back as `{"error": ...}` with `is_error: true` on the
result block, so a bad call costs one turn instead of the conversation.

## Keeping tool results small

Tools that return lists use a `_summarize()` view — id, name, category, brand,
price, rating, energy rating. Full specs and descriptions only come from
`get_product_details`, for one product at a time. Returning full records for ten
products on every recommendation would waste context and cost on data the model
mostly doesn't need.
