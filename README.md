# Family Financial Compass

Initial scaffold for the Family Financial Compass decision engine, built around the v2 specification.

## Included in this first slice

- Rent-vs-buy engine with:
  - full amortization schedule using `numpy_financial`
  - cents-based money handling
  - opportunity cost via portfolio comparisons
  - liquidity premium as a named cost line item
  - Monte Carlo simulation with correlated inputs
  - break-even month as a distribution
  - immutable scenario and output snapshots
- SQL schema for the core reference, scenario, and configuration tables
- FastAPI service layer with file-backed scenario persistence
- Tests for amortization closure, stochastic outputs, and snapshot stability

## Layout

- `src/family_financial_compass/`: calculation engine and snapshot helpers
- `frontend/`: React + Vite user interface for the decision engine
- `config/system_assumptions.json`: runtime-configurable assumptions and audit trail
- `sql/schema.sql`: Postgres/Supabase schema starter
- `tests/`: model tests

## Install

```powershell
python -m pip install -e .[dev]
```

## Run tests

```powershell
python -m pytest
```

## Run sample scenario

```powershell
$env:PYTHONPATH='src'
python -m family_financial_compass.demo
```

## Run the API

```powershell
python -m uvicorn family_financial_compass.app:create_app --factory --host 0.0.0.0 --port 8000 --app-dir src
```

Endpoints:

- `GET /readyz`
- `GET /livez`
- `GET /v1/rent-vs-buy/assumptions/current`
- `POST /v1/rent-vs-buy/analyze`
- `POST /v1/retirement-survival/analyze`
- `POST /v1/job-offer/analyze`
- `POST /v1/rent-vs-buy/report`
- `POST /v1/rent-vs-buy/scenarios`
- `GET /v1/scenarios/{scenario_id}`
 - `GET /v1/users/{user_id}/scenarios`

## Runtime configuration

Environment variables:

- `FFC_ENV`: set to `production` for production safety checks
- `FFC_HOST`: bind host, default `0.0.0.0`
- `FFC_PORT`: bind port, default `8000`
- `FFC_SCENARIO_STORE_BACKEND`: `file` or `postgres`
- `FFC_DATA_DIR`: scenario storage directory, default `data/`
- `FFC_DATABASE_URL`: Postgres connection string when using the `postgres` backend
- `FFC_DB_MIN_POOL_SIZE`: Postgres client pool minimum size
- `FFC_DB_MAX_POOL_SIZE`: Postgres client pool maximum size
- `FFC_ASSUMPTIONS_PATH`: path to assumptions JSON, default `config/system_assumptions.json`
- `FFC_ASSUMPTIONS_CACHE_TTL_DAYS`: refresh cadence for live online assumptions, default `1`
- `FFC_DEFAULT_USER_ID`: fallback scenario owner, default `anonymous`
- `FFC_ALLOWED_ORIGINS`: comma-separated browser origins allowed by CORS
- `FFC_API_KEY`: shared API key that protects private scenario save/load routes; required when `FFC_ENV=production`
- `GROQ_API_KEY`: optional Groq API key for report narrative generation
- `GROQ_MODEL`: optional Groq model name, default `openai/gpt-oss-20b`
- `GROQ_API_BASE_URL`: optional Groq OpenAI-compatible endpoint override

The app loads values from a root-level `.env` file automatically. Start from [`.env.example`](C:/Users/gordo/Economics%20Decisions%20Engine/.env.example), copy it to [`.env`](C:/Users/gordo/Economics%20Decisions%20Engine/.env), and set:

- `FFC_ENV=production`
- `FFC_SCENARIO_STORE_BACKEND=postgres`
- `FFC_DATABASE_URL=<your Neon direct connection string>`
- `FFC_API_KEY=<your generated shared secret>`

Assumptions are now runtime-dynamic when the API runs on Postgres. The service caches a resolved rent-vs-buy assumption set in Postgres for one day, refreshes mortgage and BLS rent/insurance defaults from public sources when the cache is stale, and falls back to [config/system_assumptions.json](C:/Users/gordo/Economics%20Decisions%20Engine/config/system_assumptions.json) if the live fetch fails. Protected saved scenarios still persist their resolved assumption snapshot, so historical results do not drift.

## Docker

```powershell
docker build -t family-financial-compass .
docker run -p 8000:8000 family-financial-compass
```

## Frontend

Install and run the UI:

```powershell
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` to the deployed Cloud Run backend by default. To point the UI at a different API base, copy [`frontend/.env.example`](C:/Users/gordo/Economics%20Decisions%20Engine/frontend/.env.example) to [`frontend/.env`](C:/Users/gordo/Economics%20Decisions%20Engine/frontend/.env) and set `VITE_API_BASE_URL`.

Frontend environment variables:

- `VITE_API_BASE_URL`: API origin or same-origin path the browser should call
- `VITE_APP_BASE_PATH`: frontend base path
- `VITE_EMBED_MODE`: compact embedded layout toggle
- `VITE_DEFAULT_MODULE`: default calculator to open
- `VITE_ENABLE_SAVED_ANALYSES`: enables the private/internal saved-analysis UI; default `false`

Only set `VITE_API_KEY` for private/internal builds where you explicitly enable saved analyses. Do not ship `VITE_API_KEY` in a public browser build.

To mount the calculator under an existing site such as `leadafrik.com`, you can also set:

- `VITE_APP_BASE_PATH=/calculator/` to serve the built frontend from a subpath like `https://www.leadafrik.com/calculator/`
- `VITE_EMBED_MODE=true` to remove the standalone sidebar and use a compact embedded layout
- `VITE_DEFAULT_MODULE=rent-vs-buy` to choose which calculator opens first

The frontend also reads URL parameters, so `?module=job-offer` switches the default tool and `?embed=1` forces the compact embed layout without rebuilding.

If the API stays on a different origin, set `FFC_ALLOWED_ORIGINS=https://www.leadafrik.com,https://leadafrik.com` on the FastAPI service. If you reverse-proxy the API through the same domain instead, point `VITE_API_BASE_URL` at that same-origin path, for example `/calculator-api`.

Example LeadAfrik deployment flow:

```powershell
cd frontend
copy .env.example .env
# then edit .env and set:
# VITE_APP_BASE_PATH=/calculator/
# VITE_EMBED_MODE=true
# VITE_API_BASE_URL=/calculator-api
# VITE_ENABLE_SAVED_ANALYSES=false
npm run build
```

That build can then be served by the website at `https://www.leadafrik.com/calculator/`, or embedded inside an existing page with an iframe that points at that route.

Key generation example:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Use the generated value for `FFC_API_KEY` on the backend. Only mirror it into `VITE_API_KEY` for a private/internal frontend build with `VITE_ENABLE_SAVED_ANALYSES=true`.

The rent-vs-buy UI now supports on-demand PDF generation and a compact live-assumptions drawer. The browser requests the current default assumption bundle from `GET /v1/rent-vs-buy/assumptions/current`, lets the user override the most material housing assumptions with sliders, sends those overrides into `POST /v1/rent-vs-buy/analyze` and `POST /v1/rent-vs-buy/report`, and renders the PDF locally with React-PDF. If `GROQ_API_KEY` is configured on the backend, the short narrative sections are generated through Groq; otherwise the app falls back to deterministic template text.

Current product shape:

- `Rent vs Buy`: live end-to-end through the API
- `Retirement Survival`: live analysis engine
- `Job Offer & Relocation`: live analysis engine
- `College vs Retirement`: live analysis engine
- `Debt Payoff vs Invest`: queued (hidden from nav until implemented)
