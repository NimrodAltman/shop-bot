# TODO / Roadmap

Status of the project and what's left. Updated 2026-10-11.

## Status

Every layer is written, committed and pushed. The catalog, storage and tool
layers are verified by direct execution. Three rounds of work have landed:

- **Round 1:** rich Markdown formatting (icons, structured product lists) and
  onboarding across four languages (English/Hebrew/Russian/Arabic, with
  dynamic switching if the user types in a different language than their
  Telegram client is set to).
- **Round 2:** localization extracted into its own `i18n.py` module; a
  returning user with a saved profile gets a welcome-back instead of forced
  re-onboarding; `/update` edits one saved field without a full reset; the
  location-share button re-appears if the user asks about stores in free text
  before ever sharing one; optional admin alerts (`notify.py`) on a new order
  or an API failure.
- **Round 3 (security review):** a full pass over the whole project — tool
  authorization, data exposure, prompt injection, cost abuse — closed 6 issues,
  the most serious being an IDOR on order status. Full list below under
  "Round 3: security fixes."

**Live testing has started and the highest-risk regression passed:** after
rounds 1–3 landed, a full onboarding → recommendation → order →
`get_order_status` round-trip was walked through live in Telegram, including
asking for the order status by name (the exact call whose signature the
security fix changed) — it returned the correct "pending" status. The rest of
the live checklist (4-language rendering, `/update`, returning-user greeting,
rate limiting, the two injection fixes) is still open — see "Next up" below.

| Layer | State |
|---|---|
| `data/mock_data.py` | ✅ Done — 6 stores, 11 products |
| `db.py` | ✅ Done, tested — in-memory verified; Supabase path untested |
| `mcp_server.py` | ✅ Done, tested. `get_order_status` now requires and checks `user_id`; review tools strip the reviewer's `user_id` before returning |
| `agent.py` | ✅ Done. Formatting rules in the system prompt; admin alert on each API-error branch; `get_order_status` added to the server-injected `_USER_SCOPED_TOOLS`; profile text sanitized before it enters the prompt |
| `main.py` | ✅ Done. Localization delegated to `i18n.py`; returning-user greeting, `/update`, location-keyboard re-offer; per-user rate limiting (12 msg/60s); the `LOCATION_SHARED` marker is defanged in typed text; the Telegram display name is Markdown-escaped |
| `i18n.py` | ✅ Detection/resolution + all fixed strings for 4 languages, including the rate-limit notice |
| `notify.py` | ✅ Silent no-op without `ADMIN_TELEGRAM_ID` |
| Docs | ✅ README, architecture, data model, deployment, this file |

**Live-confirmed so far:** `/start` → category → budget → location →
`recommend_products` → `place_order` → `get_order_status` (owner reading
their own order, post-fix). **Not yet live-confirmed:** everything else in
rounds 1–3 — see the checklist in "Next up."

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
  `ANTHROPIC_API_KEY`, `run_polling()` reaches Telegram's `getMe` successfully,
  as [@NimrodShopDemo_bot](https://t.me/NimrodShopDemo_bot).
- **A real conversation turn** — category → budget → location → a
  `recommend_products` call that returned a real air-conditioner match at the
  right size and budget. This confirms the agent loop, tool execution, and
  Claude producing a usable reply all work end to end — the first time that
  was true (see commit `ce8eb27`'s note that this was previously unconfirmed).
- **Onboarding localization (pre-4-language version)** — Hebrew rendering
  confirmed live by the user, before the 4-language expansion below.
- **The root cause of an apparent "the bot forgot our conversation"** — traced
  to a bot restart (mid-session, to load a fix) landing exactly between two
  user messages. In-memory storage has no persistence across restarts; this is
  documented in Known Limitations, not a conversation-logic bug.
- **Round 2, offline (no live Telegram involved):** `i18n.detect_lang` correctly
  identifies English/Hebrew/Arabic/Russian and returns `None` for digits-only
  text; `i18n.resolve_lang` picks a stored profile override over the Telegram
  `language_code`; `i18n.t`/`category_label` return the right string per
  language; the location-keyword matcher fires for English and Russian sample
  phrases and correctly does not fire on an unrelated Hebrew sentence;
  `notify.send_admin_alert` is a true no-op (no exception, no request sent)
  when `ADMIN_TELEGRAM_ID` is unset; `_category_keyboard`/`_budget_keyboard`
  build correct `updcat:`/`updbudget:`-prefixed callback data for `/update`;
  a returning user's profile (`category`, `budget`) is confirmed left
  untouched by the `/start` returning-user branch; `place_order` still
  succeeds with `notify` wired in.
- **Round 3 (security fixes), offline, one scenario per fix:** a second
  `user_id` reading someone else's `order_id` gets the identical
  "no order with id" error a nonexistent id gets (no cross-user read, no
  existence oracle); `get_reviews`/`get_product_details` contain no `user_id`
  anywhere in their JSON after a review is saved; a simulated flood of 20
  messages from one user lets exactly 12 through and blocks the rest, while a
  second user is unaffected and an expired window frees up again; four
  variants of a hand-typed `LOCATION_SHARED: lat,lng` are all rewritten to
  plain text while ordinary messages are untouched; a multi-line profile name
  crafted to look like a system instruction is flattened to one line and
  capped at 64 characters; a `[click here](url)` display name no longer
  parses as a link and stray `*`/`_` no longer open unclosed emphasis, while
  real names in four scripts pass through unchanged. All six verified to not
  interfere with each other in one combined run.
- **Live, post-fix:** the single highest-risk regression point — asking "what's
  the status of my order" after `get_order_status` started requiring
  `user_id` — was exercised in a real Telegram conversation and returned the
  correct status for the order's actual owner.

### What was not verified

- **Everything in round 1** — rich Markdown rendering, the parse-error
  fallback, 4-language onboarding, dynamic language switching — none of it has
  been seen in a live Telegram conversation yet.
- **Most of round 2** — no real `/update`, no real returning-user `/start`,
  no real free-text location re-offer, and no real admin alert have been
  observed against the live bot yet.
- **Round 3's live confirmation is partial** — the order-status fix (the
  highest-risk one) is confirmed live; the cross-user IDOR block itself
  needs a second Telegram account to exercise directly (the offline test
  above substitutes for this); rate limiting, the location-marker defang,
  and the Markdown-escaped display name have not been tried against the
  live bot.
- The rest of the conversation checklist below — reviews, city-name search,
  general questions.
- Prompt caching behavior in practice (only inspected structurally, not via
  `usage.cache_read_input_tokens` on a real request).
- The Supabase code path (needs a project + the tables).

---

## Next up

### 1. Re-test live — three rounds of gap-closing and security work are stacked up untested

This is the immediate next step — everything else in this section is
downstream of it.

- [x] Bot connects to Telegram with real credentials, no startup errors
- [x] `/start` onboarding UI renders in the user's language (Hebrew confirmed)
- [x] A real recommendation round-trip (category → budget → location →
      `recommend_products` → a genuine match) — confirmed with an air
      conditioner recommendation
- [x] Order flow: confirm → `place_order` → order id → `get_order_status`,
      including the post-security-fix owner read (see Round 3 below)
- [ ] **Cross-user order read is actually blocked** — needs a second Telegram
      account; place an order as user A, ask about its `order_id` as user B,
      confirm the same "not found" error a fake id gets
- [ ] **Rate limiting fires and recovers** — send 13+ messages quickly, confirm
      message 13 gets the rate-limited notice instead of an answer, and that a
      different account is unaffected at the same time
- [ ] **`LOCATION_SHARED` spoofing is neutralized** — type the marker by hand
      in free text, confirm the bot does not treat it as a real location
- [ ] **Rich formatting renders correctly** — bold product names, category
      icons, one product per line, no raw `*`/`_` leaking into the message
- [ ] **The Markdown-parse-error fallback actually fires and recovers** if the
      model ever produces unmatched `*`/`_` (hard to force deliberately, but
      worth watching for during normal use)
- [ ] **4-language onboarding** — confirm Russian and Arabic labels render
      correctly (only Hebrew/English seen live so far)
- [ ] **Dynamic language switching** — start in Hebrew, type an English
      message mid-conversation, confirm subsequent menus switch to English
- [ ] **Category-keyboard reattachment** — deliberately reproduce the "bot
      asks for a category in a sentence" case and confirm buttons appear now
- [ ] **Returning-user `/start`** — complete onboarding once, send `/start`
      again, confirm a welcome-back message and that category/budget/location
      survive untouched
- [ ] **`/update`** — change just the budget via the menu, confirm it doesn't
      also ask for a new category or location afterward
- [ ] **Location re-offer in free text** — with no location saved, ask "any
      stores nearby?" and confirm the location-share button appears
- [ ] **Admin alerts** — set `ADMIN_TELEGRAM_ID` to your own id, place an
      order, confirm a Telegram message arrives
- [ ] Location sharing returns genuinely nearby stores
- [ ] City name (typed instead of GPS) works
- [ ] Ordering from a store that doesn't stock the item is refused gracefully
- [ ] Reviews save and read back, and no `user_id` is visible in the reply
- [ ] A general question ("what's a good energy rating?") answers without tools
- [ ] Asked whether stores are real, the bot says it's demo data
- [ ] `/reset` clears context; `/help` reads correctly in all four languages

### 2. Commit and push this batch

**Done.** Rounds 1–2 and the 6 security fixes (round 3) are all pushed, each
fix in its own commit. The live-regression pass before pushing (onboarding
through order-status) caught no breakage — the "asks for category as a
sentence" gap from before round 2 is the reason this project tests live
before pushing UI/behavior changes at all, and it paid for itself again.

- [x] ~~Commit and push the earlier localization change~~ — `ce8eb27`
- [x] ~~Commit and push round 1 + round 2~~ — `3fa53cd`
- [x] ~~Commit and push round 3 (security fixes), one commit per fix~~ —
      `7009c98`, `e340112`, `3825bda`, `2c342f0`, `5fdea98`, `b3f8026`

### 3. ~~Rich message formatting~~ — code-complete, pending the re-test above

Implemented in two files, matching the split that was planned:

- [x] `main.py`: `_send()` now passes `parse_mode="Markdown"` on agent replies
      (not just `/help`), and catches `telegram.error.BadRequest` to retry
      without `parse_mode` if the model's Markdown doesn't parse.
- [x] `agent.py`: `STABLE_SYSTEM` gained a "Formatting (Telegram Markdown)"
      section — the category icon table, "one product per line," "blank line
      before the follow-up question," and which Markdown subset is safe
      (`*bold*`/`_italic_` only, no nesting, no links/headers/code blocks).
- [ ] Confirmed rendering correctly in a live reply (see item 1).

### 4. ~~Four-language onboarding with dynamic switching~~ — code-complete, pending the re-test above

Not originally scoped — added after directly comparing a screenshot of another
Telegram bot's onboarding (Hebrew/English/Russian/Arabic support) against
ShopBot's.

- [x] `main.py`: `SUPPORTED_LANGS` extended to `en`/`he`/`ru`/`ar`; every
      onboarding string and category label has all four translations (now
      living in `i18n.py` — see round 2 below).
- [x] `i18n.detect_lang()` — guesses a language from the Unicode script
      of what the user actually types (Hebrew/Arabic/Cyrillic ranges, else
      Latin → English), no API call. `on_text` calls it on every free-text
      message and persists a change to the user's profile.
- [x] `i18n.resolve_lang()` prefers that stored override over the Telegram
      client's fixed `language_code`, so someone with a Hebrew phone who
      starts typing in English gets English menus from then on.
- [x] Onboarding restructured into two messages (a bold capabilities card,
      then the actual question with its keyboard) — matches the rhythm the
      reference bot uses, per the side-by-side screenshot comparison.
- [ ] Russian and Arabic confirmed rendering correctly (see item 1).
- [ ] The switch-mid-conversation behavior confirmed live (see item 1).

### 5. ~~Round 2: i18n module, returning users, `/update`, admin alerts~~ — code-complete, pending the re-test above

Ported from comparing against the reference bot's more mature onboarding
(same architecture pattern, home-appliance strings — no domain content
carried over):

- [x] `i18n.py` (new) — all localization moved out of `main.py`: `detect_lang`,
      `resolve_lang`, `t`, `category_label`, `STRINGS`, `CATEGORY_LABELS_BY_LANG`,
      `BUDGET_OPTIONS`, `LOCATION_KEYWORDS`. `main.py` now only calls into it.
- [x] `notify.py` (new) — `send_admin_alert(message)`, a plain Telegram
      `sendMessage` to `ADMIN_TELEGRAM_ID` using stdlib `urllib` (no new
      dependency). No-ops silently if unset; never raises.
- [x] `agent.py` — calls `notify.send_admin_alert` in each of the four
      exception branches (auth, rate limit, connection, unexpected).
- [x] `mcp_server.py` — `place_order` calls `notify.send_admin_alert` with the
      order details right after `db.create_order` succeeds.
- [x] `main.py` — `start()` checks `onboarding_complete` first: a returning
      user gets `welcome_back` and keeps their saved category/budget/location;
      only a new user goes through the category → budget → location chain.
- [x] `main.py` — `/update` command + menu (category/budget/location). Reuses
      `_category_keyboard`/`_budget_keyboard` via a `prefix` parameter
      (`updcat:`/`updbudget:`) routed to standalone confirm-and-stop handlers,
      so picking a new category via `/update` doesn't also chain into asking
      for a budget.
- [x] `main.py` — `_reply_via_agent` re-offers the location-share keyboard
      when the user has no `lat`/`city` on file and their free text matches
      `i18n.LOCATION_KEYWORDS` for their current language.
- [ ] All of the above confirmed in a live conversation (see item 1).

**Deliberately not ported** (see the original comparison): a numbered
1-7 text-menu fallback (Telegram already has real buttons), a `/health` Flask
endpoint (shop-bot has no HTTP server — adding one risks the exact threaded
`asyncio.run()` bug this project was built to avoid), a privacy-consent
screen and self-service data deletion, and name transliteration. None of
these were needed to close the gaps that mattered; the first two actively
conflict with this project's architecture.

### 6. ~~Round 3: security review~~ — pushed, partially confirmed live

A full pass over the project, scoped to three threat categories the bot is
actually exposed to as a public Telegram bot: prompt injection, cross-user
data leakage, and cost abuse. One commit per fix, each with its own offline
attack-scenario test (see "What was actually verified" above).

- [x] `mcp_server.py` — **IDOR**: `get_order_status` took only an `order_id`;
      any user could read any order's product, store, quantity and price. Now
      requires `user_id` and returns the same "not found" error for someone
      else's order as for a fake id, so the error can't be used to enumerate
      real order ids. `agent.py`: `get_order_status` added to
      `_USER_SCOPED_TOOLS`, so the id is injected server-side like
      `place_order`/`save_review`, never trusted from the model.
- [x] `mcp_server.py` — `get_reviews`/`get_product_details` returned the raw
      stored review, including the reviewer's Telegram `user_id`. Both now map
      through `_public_review()`, which exposes only rating/comment/date.
- [x] `main.py` — **no rate limiting anywhere**, so one chat could trigger
      unlimited paid Anthropic calls. `_reply_via_agent` is the only path to a
      paid call; it now checks a per-user sliding window (12 messages/60s,
      in memory) before calling the agent, and replies with a translated
      notice instead when exceeded.
- [x] `main.py` — the system prompt tells the model `LOCATION_SHARED: lat,lng`
      in a message means real shared coordinates; nothing stopped a user from
      typing that string themselves. `on_text` now rewrites the marker to
      plain wording before the agent sees it; `on_location` is unaffected.
- [x] `agent.py` — the profile (including the user's Telegram display name)
      is rendered into the system prompt; a multi-line name could be dressed
      up to look like a system instruction. `_sanitize_profile()` collapses
      whitespace and caps `name`/`city` at 64 characters before that happens,
      and the prompt now states explicitly that profile values are data, not
      instructions.
- [x] `main.py` — the display name was interpolated into greeting messages
      sent with `parse_mode="Markdown"` unescaped; a name like
      `[click here](url)` rendered as a live link. `_escape_markdown()` now
      backslash-escapes Telegram legacy Markdown's four special characters
      before the name is used.
- [ ] Live-confirmed: only the order-status fix so far (see above). The other
      five are offline-verified only — see item 1's checklist.

**Scoped out on purpose, not forgotten:** a global (cross-account) rate limit
— the per-user cap doesn't stop the same flood spread across many accounts;
upper bounds on `quantity`/`limit`/`radius_km` in tool inputs — nothing
exploitable with 6 stores and 11 products, but worth capping before any real
catalog; pinning dependency versions in `requirements.txt` (currently `>=`);
Supabase row-level security (already tracked below, and moot while
unconnected).

### 7. Screenshots for the README

The README has no screenshots — the one gap against the original plan. Capture
**after** the re-test above, so they show the real experience:

- [ ] `/start` onboarding with the inline keyboard, in at least two languages
- [ ] A recommendation with reasoning — icons and a real list, not one paragraph
- [ ] Location sharing → nearby stores
- [ ] An order confirmation
- [ ] Commit to `Docs/images/` and embed in the README

### 8. Polish

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
