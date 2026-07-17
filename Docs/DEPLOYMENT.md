# Deployment

Running ShopBot locally, and putting it somewhere it stays up.

## Local

### Requirements

- Python 3.10+ (`db.py` uses `dict | None` syntax)
- A Telegram bot token and an Anthropic API key

### Steps

```bash
pip install -r requirements.txt
cp .env.example .env    # fill in TELEGRAM_TOKEN and ANTHROPIC_API_KEY
python main.py
```

Expected output:

```
2026-07-17 15:07:55 [INFO] __main__: ShopBot is up — polling for updates.
```

Then send `/start` to your bot in Telegram.

### Getting the credentials

**Telegram token** — message [@BotFather](https://t.me/BotFather), send
`/newbot`, pick a name and a username ending in `bot`. He replies with a token
like `123456789:AAF...`. `/setdescription` and `/setuserpic` are worth doing if
you're sharing the bot.

**Anthropic key** — [console.anthropic.com](https://console.anthropic.com) →
API Keys → Create Key. Requires credit on the account.

### Common startup failures

| Symptom | Cause |
|---|---|
| `TELEGRAM_TOKEN is not set` | No `.env`, or the value is blank |
| `ANTHROPIC_API_KEY is not set` | Same |
| `telegram.error.InvalidToken: Unauthorized` | Token is wrong or was revoked |
| `⚠️ The assistant isn't configured correctly` (in chat) | Anthropic key is invalid — the bot is up, Claude isn't |
| Bot never answers, no errors | Another instance is polling the same token. Telegram allows one. |

## Storage

In-memory by default: everything is lost on restart. Fine for a demo, and it
means anyone can clone and run with only two env vars.

For persistence, create the tables from
[DATA_MODEL.md](DATA_MODEL.md#supabase-schema), uncomment `supabase` in
`requirements.txt`, install it, and set `SUPABASE_URL` + `SUPABASE_KEY`. `db.py`
switches over on the next start — no code change. If the client can't be
created, it logs a warning and falls back to in-memory rather than crashing.

## Railway

The bot is a long-running poller, not a web service — it needs a **worker**, not
a web dyno. There is no HTTP port to bind.

1. Push to GitHub.
2. [railway.app](https://railway.app) → New Project → Deploy from GitHub repo.
3. Add the env vars under **Variables**: `TELEGRAM_TOKEN`, `ANTHROPIC_API_KEY`,
   and optionally the Supabase pair.
4. Add a `Procfile`:

```
worker: python main.py
```

Railway's nixpacks builder detects Python and installs `requirements.txt`
automatically.

### Notes

- **Only one instance may poll a token.** Don't scale the worker past 1 replica
  — a second one causes both to drop updates. Scale by moving to webhooks
  instead of polling.
- **Use in-memory storage only for a single instance.** State lives in the
  process; two replicas mean two disjoint sets of users. Configure Supabase
  before scaling.
- **Restarts clear in-memory state.** Railway restarts on deploy, so a
  conversation mid-flow starts over.

## Other hosts

Anything that runs a long-lived Python process works — Fly.io, Render (as a
Background Worker), a VPS with systemd. The requirements are only: Python 3.10+,
outbound HTTPS, one instance, and the env vars.

Serverless (Lambda, Cloud Functions) does **not** fit this design — `run_polling()`
expects to run forever. Serverless would mean rewriting `main.py` to use
webhooks, which is a reasonable change but a different program.

## Cost

- **Telegram** — free.
- **Anthropic** — per token. A short conversation is fractions of a cent; the
  split system prompt caches the ~3,000-character stable block, so repeat turns
  read it at roughly a tenth of the input price instead of paying full price
  each time. See [ARCHITECTURE.md](ARCHITECTURE.md#the-system-prompt-is-split-in-two).
- **Railway** — free tier covers a demo bot.
- **Supabase** — free tier is far beyond what this needs.
