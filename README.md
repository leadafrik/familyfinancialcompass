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
- `POST /v1/rent-vs-buy/analyze`
- `POST /v1/rent-vs-buy/report`
- `POST /v1/rent-vs-buy/scenarios`
- `GET /v1/scenarios/{scenario_id}`
 - `GET /v1/users/{user_id}/scenarios`

## Runtime configuration

Environment variables:

- `FFC_HOST`: bind host, default `0.0.0.0`
- `FFC_PORT`: bind port, default `8000`
- `FFC_SCENARIO_STORE_BACKEND`: `file` or `postgres`
- `FFC_DATA_DIR`: scenario storage directory, default `data/`
- `FFC_DATABASE_URL`: Postgres connection string when using the `postgres` backend
- `FFC_DB_MIN_POOL_SIZE`: Postgres client pool minimum size
- `FFC_DB_MAX_POOL_SIZE`: Postgres client pool maximum size
- `FFC_ASSUMPTIONS_PATH`: path to assumptions JSON, default `config/system_assumptions.json`
- `FFC_DEFAULT_USER_ID`: fallback scenario owner, default `anonymous`
- `FFC_ALLOWED_ORIGINS`: comma-separated browser origins allowed by CORS
- `GROQ_API_KEY`: optional Groq API key for report narrative generation
- `GROQ_MODEL`: optional Groq model name, default `openai/gpt-oss-20b`
- `GROQ_API_BASE_URL`: optional Groq OpenAI-compatible endpoint override

The app loads values from a root-level `.env` file automatically. Edit [`.env`](C:/Users/gordo/Economics%20Decisions%20Engine/.env) and set:

- `FFC_SCENARIO_STORE_BACKEND=postgres`
- `FFC_DATABASE_URL=<your Neon direct connection string>`

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

The Vite dev server proxies `/api` to the deployed Cloud Run backend by default. To point the UI at a different API base, copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_BASE_URL`.

The rent-vs-buy UI now supports on-demand PDF generation. The browser requests a report payload from `POST /v1/rent-vs-buy/report` and renders the PDF locally with React-PDF. If `GROQ_API_KEY` is configured on the backend, the short narrative sections are generated through Groq; otherwise the app falls back to deterministic template text.

Current product shape:

- `Rent vs Buy`: live end-to-end through the API
- `Retirement Survival`: next computation module
- `Job Offer & Relocation`: queued
- `College vs Retirement`: queued
- `Debt Payoff vs Invest`: queued
