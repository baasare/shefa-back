# ShefaFx Trading Platform - Backend

AI-powered autonomous trading agent platform built with Django, Celery, and LangGraph.

## Architecture

- **Framework:** Django 5.0+
- **API:** Django REST Framework with SSE streaming support
- **Background Tasks:** Celery + Redis
- **Database:** PostgreSQL
- **AI/Agents:** LangGraph + Anthropic Claude
- **Authentication:** JWT + OAuth (Google)

## Project Structure

```
backend/
├── apps/
│   ├── users/           # User management & authentication
│   ├── portfolios/      # Portfolio tracking & performance
│   ├── strategies/      # Trading strategy configuration
│   ├── orders/          # Order management & HITL approvals
│   ├── agents/          # AI trading agents (LangGraph + SSE)
│   ├── market_data/     # Market data providers
│   ├── brokers/         # Broker integrations (Alpaca, etc.)
│   └── notifications/   # Email/SMS/Push notifications
├── config/
│   ├── settings/
│   │   ├── base.py      # Base settings
│   │   ├── development.py
│   │   ├── production.py
│   │   └── test.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── celery_app.py        # Celery configuration & beat schedule
├── manage.py
└── requirements.txt

## Setup

### 1. Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up environment variables

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 4. Set up PostgreSQL database

```bash
createdb shefa_db
```

### 5. Run migrations

```bash
python manage.py migrate
```

### 6. Create superuser

```bash
python manage.py createsuperuser
```

### 7. Run development server

```bash
python manage.py runserver
```

## Render deployment with Supabase

Use `render.yaml` to create the free API service. Set the database fields from
Supabase's **Connect → Session pooler** panel (port 5432); enter the database
password only in Render's environment settings. This deployment requires TLS.
Disable Supabase's Data API for this Django-managed database, unless separately
configured with appropriate grants and row-level security.

Set `FRONTEND_URL`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS` to the
Vercel production origin, including `https://`. Set Vercel's
`NEXT_PUBLIC_API_URL` to the Render origin without a path prefix and
`NEXT_PUBLIC_APP_URL` to the Vercel origin. API routes are `/v1/`, `/docs/`, and
`/health/`. Render automatically adds its hostname to Django's allowed hosts.

The start command applies migrations before serving requests. Free Render web
services sleep when idle. This blueprint does not provision Celery workers,
Redis, or scheduled trading; those need separate services. Configure Resend and
the provider credentials in Render before using email verification, AI, or
market-data features. Never put backend secrets in Vercel's `NEXT_PUBLIC_*`
variables.

## Running Celery

### Start Celery worker

```bash
celery -A celery_app worker -l info
```

### Start Celery Beat (scheduler for autonomous agents)

```bash
celery -A celery_app beat -l info
```

## API Documentation

Once the server is running, visit:

- **Swagger UI:** http://localhost:8000/api/docs/
- **ReDoc:** http://localhost:8000/api/redoc/
- **OpenAPI Schema:** http://localhost:8000/api/schema/

## SSE Streaming (Agent Analysis)

The agent analysis endpoint uses Server-Sent Events (SSE) for real-time streaming, compatible with Vercel AI SDK.

**Endpoint:** `POST /api/agents/stream/`

**Payload:**
```json
{
  "strategy_id": "uuid",
  "symbols": ["AAPL", "TSLA", "MSFT"],
  "id": "optional-message-id"
}
```

**Event Types:**
- `analysis-start` - Agent starts analyzing a symbol
- `tool-call` - Agent invokes a tool
- `tool-result` - Tool returns results
- `text-delta` - Agent reasoning (streams char-by-char)
- `trade-signal` - Buy/sell/hold signal generated
- `analysis-complete` - Analysis finished
- `data-error` - Error occurred

## Environment Variables

See `.env.example` for all required environment variables.

### Key Variables:

- `ENVIRONMENT` - development/production/test
- `SECRET_KEY` - Django secret key
- `POSTGRES_*` - Database credentials
- `REDIS_URL` - Redis connection URL
- `ANTHROPIC_API_KEY` - Claude API key
- `ALPACA_API_KEY` - Alpaca broker API key

## Development Tips

1. **Use Django Extensions:**
   ```bash
   python manage.py shell_plus  # Enhanced shell
   python manage.py show_urls   # List all URLs
   ```

2. **Run tests:**
   ```bash
   python manage.py test
   ```

3. **Create migrations:**
   ```bash
   python manage.py makemigrations
   ```

## License

Proprietary - All rights reserved
