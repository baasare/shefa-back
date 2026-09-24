# ShefaFx V3 paper trading

V3 adds a LangChain-backed bot drafting and analysis API. Bots can only use a verified `alpaca_paper` connection attached to a paper portfolio. Live portfolios and live Alpaca connections are rejected in both the bot runner and the shared order execution engine.

## Local setup

Set `GEMINI_API_KEY`, `BOT_LLM_MODEL`, and `REDIS_URL` in the local backend environment. The default LLM is Gemini 3.8 Flash through LangChain. Create and migrate the database, then run Django, a Celery worker, and Celery Beat:

Gemini analysis receives the bot's instructions, supplied market data, paper-account snapshot (portfolio value, daily P&L, open position count/symbols), and bot risk limits. Google's Gemini Developer API free tier may use submitted content to improve Google products; switch to the paid tier before sending data that should not be used this way.

```sh
python manage.py migrate
python manage.py runserver
celery -A celery_app worker -l info
celery -A celery_app beat -l info
```

The authenticated API lives under `/v1/bots/`. It supports draft creation, an optional LangChain rewrite, paper-only start/pause/stop, manual queueing, run history, activity events, and Server-Sent Events. The web client attaches the normal bearer token to the SSE fetch; it never puts the token in a URL.

## Production prerequisites

The existing Render blueprint provisions only a Free web service. It does not provision a persistent Celery worker, Celery Beat, or Redis. Therefore it cannot run scheduled bots and manual runs will return a clear queue-unavailable response until those services are deployed. Do not represent an active status as evidence that a run was executed.

Before enabling execution in production, deploy a persistent worker and Beat process using the same backend commit, provision a durable Redis-compatible queue, set `REDIS_URL`, and set `GEMINI_API_KEY` on the backend only. Confirm the broker is an Alpaca paper account. The V3 scheduler is the only periodic autonomous trading task; the legacy agent scan and live strategy execution schedules were removed. Do not enable live trading.

Use Render's current service pricing before adding persistent infrastructure; worker and queue pricing may change. No paid service should be created without explicit cost approval.

## Safety limits

- U.S. stock and ETF symbols only, long-only, whole-share market orders.
- AI can only return `buy`, `sell`, or `hold`; it cannot set quantity or issue a broker tool call.
- Server checks account mode, trading eligibility, market hours, quote freshness, daily loss, order value, buying power, held positions, and maximum open positions.
- Each order has a stable Alpaca client order ID. An ambiguous provider response is looked up instead of blindly retried.
- Live trading, options, short sales, crypto, and user-supplied live API connections are out of scope.
