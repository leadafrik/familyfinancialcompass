from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api_models import (
    AnalysisEnvelope,
    AnalyzeRequest,
    CreateScenarioRequest,
    HealthEnvelope,
    ScenarioEnvelope,
    ScenarioListEnvelope,
)
from .config import load_assumption_bundle
from .repository import FileScenarioRepository, PostgresScenarioRepository
from .rent_vs_buy import RentVsBuyEngine
from .service import FamilyFinancialCompassService
from .settings import AppSettings


def create_app(settings: AppSettings | None = None) -> FastAPI:
    app_settings = settings or AppSettings.from_env()
    assumption_bundle = load_assumption_bundle(app_settings.assumptions_path)
    engine = RentVsBuyEngine(assumption_bundle.assumptions)
    if app_settings.scenario_store_backend == "postgres":
        if app_settings.database_url is None:
            raise ValueError("FFC_DATABASE_URL must be set when FFC_SCENARIO_STORE_BACKEND=postgres.")
        repository = PostgresScenarioRepository(
            database_url=app_settings.database_url,
            min_pool_size=app_settings.database_min_pool_size,
            max_pool_size=app_settings.database_max_pool_size,
            connect_timeout_seconds=app_settings.database_connect_timeout_seconds,
        )
    else:
        repository = FileScenarioRepository(app_settings.data_dir)
    service = FamilyFinancialCompassService(
        engine=engine,
        repository=repository,
        audit_trail=assumption_bundle.audit_trail,
        default_user_id=app_settings.default_user_id,
    )

    app = FastAPI(
        title="Family Financial Compass API",
        version=service.model_version,
    )
    if app_settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(app_settings.allowed_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.state.service = service
    app.state.settings = app_settings

    @app.exception_handler(ValueError)
    async def handle_value_error(_, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/healthz", response_model=HealthEnvelope)
    async def healthz() -> HealthEnvelope:
        return HealthEnvelope(
            status="ok",
            model_version=service.model_version,
            scenario_store=repository.storage_target,
            assumptions_path=str(app_settings.assumptions_path),
        )

    @app.get("/readyz", response_model=HealthEnvelope)
    async def readyz() -> HealthEnvelope:
        return HealthEnvelope(
            status="ok",
            model_version=service.model_version,
            scenario_store=repository.storage_target,
            assumptions_path=str(app_settings.assumptions_path),
        )

    @app.get("/livez", response_model=HealthEnvelope)
    async def livez() -> HealthEnvelope:
        return HealthEnvelope(
            status="ok",
            model_version=service.model_version,
            scenario_store=repository.storage_target,
            assumptions_path=str(app_settings.assumptions_path),
        )

    @app.post("/v1/rent-vs-buy/analyze", response_model=AnalysisEnvelope)
    async def analyze_rent_vs_buy(request: AnalyzeRequest) -> AnalysisEnvelope:
        payload = service.analyze_rent_vs_buy_payload(
            request.input.to_domain(),
            seed=request.simulation_seed,
        )
        return AnalysisEnvelope(**payload)

    @app.post("/v1/rent-vs-buy/scenarios", response_model=ScenarioEnvelope)
    async def create_rent_vs_buy_scenario(request: CreateScenarioRequest) -> ScenarioEnvelope:
        bundle = service.create_rent_vs_buy_scenario(
            user_inputs=request.input.to_domain(),
            user_id=request.user_id,
            seed=request.simulation_seed,
            idempotency_key=request.idempotency_key,
        )
        return ScenarioEnvelope(**service.serialize_scenario_bundle(bundle))

    @app.get("/v1/scenarios/{scenario_id}", response_model=ScenarioEnvelope)
    async def get_scenario(scenario_id: str) -> ScenarioEnvelope:
        bundle = service.get_scenario(scenario_id)
        if bundle is None:
            raise HTTPException(status_code=404, detail="Scenario not found.")
        return ScenarioEnvelope(**service.serialize_scenario_bundle(bundle))

    @app.get("/v1/users/{user_id}/scenarios", response_model=ScenarioListEnvelope)
    async def list_scenarios(
        user_id: str,
        limit: int = app_settings.scenario_list_default_limit,
        cursor: str | None = None,
    ) -> ScenarioListEnvelope:
        if limit <= 0 or limit > app_settings.scenario_list_max_limit:
            raise HTTPException(
                status_code=400,
                detail=(
                    "limit must be between 1 and "
                    f"{app_settings.scenario_list_max_limit}"
                ),
            )
        page = service.list_scenarios(user_id=user_id, limit=limit, cursor=cursor)
        return ScenarioListEnvelope(
            items=[ScenarioEnvelope(**service.serialize_scenario_bundle(bundle)) for bundle in page.items],
            next_cursor=page.next_cursor,
        )

    @app.on_event("shutdown")
    async def shutdown() -> None:
        close = getattr(repository, "close", None)
        if callable(close):
            close()

    return app
