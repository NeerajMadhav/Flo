# Flo

Telegram personal finance assistant for Indian users (`@PennyTrackerBot`).

Logs expenses from plain English / Hinglish / Tenglish, handles bill splits (both debt directions), settlements, goals, and weekly/monthly reports.

## Stack

- FastAPI + python-telegram-bot v21 (async)
- SQLAlchemy 2.0 async (SQLite dev / Postgres prod)
- OpenRouter NLP (PARSE / EDIT / CLARIFY / INSIGHT prompts)
- APScheduler (single Railway instance)

## Quick start

```bash
cp .env.example .env
# Set TELEGRAM_BOT_TOKEN, OPENROUTER_API_KEY, API_SECRET_KEY, TELEGRAM_WEBHOOK_SECRET

pip install -r requirements-dev.txt
python -m app.core.seed
BOT_MODE=polling uvicorn app.main:app --reload --port 8000
```

Then message your bot on Telegram: `/start`

- Health: `GET /health`
- API docs: `http://localhost:8000/docs`
- Webhook (prod): `BOT_MODE=webhook` + public `BACKEND_URL`

## Layout

```
app/
  core/          models, DB, exceptions, seed
  repositories/  user-scoped data access
  services/      finance + NLP business logic
  channels/
    telegram/    bot handlers, router, keyboards
    api/v1/      REST endpoints
  nlp/           prompts + ParsedMessage schema
  scheduler/     weekly/monthly/recurring jobs
  utils/         currency, dates, sanitizer, logger
```

## Specs (source of truth)

- `FLO_FEATURES_COMPLETE.md` — product behaviour
- `PAISA_BOT_FINAL_BLUEPRINT.md` — engineering design
- `backend-plan.md` — build order
- `prompt.md` — NLP prompt system

## Tests

```bash
pytest -q
```

## Deploy notes

- Pin Railway max instances to **1** (APScheduler has no distributed lock)
- Production `DATABASE_URL` should be `postgresql+asyncpg://...`
- Never commit `.env`
