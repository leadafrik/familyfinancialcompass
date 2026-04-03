from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .assumptions import FileAssumptionStore, PostgresAssumptionStore
from .api_models import (
    AnalysisEnvelope,
    AnalyzeRequest,
    CollegeVsRetirementAnalyzeRequest,
    CreateScenarioRequest,
    CurrentAssumptionsEnvelope,
    HealthEnvelope,
    JobOfferAnalyzeRequest,
    RetirementAnalyzeRequest,
    ReportEnvelope,
    ScenarioEnvelope,
    ScenarioListEnvelope,
)
from .repository import FileScenarioRepository, PostgresScenarioRepository
from .service import FamilyFinancialCompassService
from .settings import AppSettings


def create_app(settings: AppSettings | None = None) -> FastAPI:
    app_settings = settings or AppSettings.from_env()
    if app_settings.scenario_store_backend == "postgres":
        if app_settings.database_url is None:
            raise ValueError("FFC_DATABASE_URL must be set when FFC_SCENARIO_STORE_BACKEND=postgres.")
        repository = PostgresScenarioRepository(
            database_url=app_settings.database_url,
            min_pool_size=app_settings.database_min_pool_size,
            max_pool_size=app_settings.database_max_pool_size,
            connect_timeout_seconds=app_settings.database_connect_timeout_seconds,
        )
        assumption_store = PostgresAssumptionStore(
            pool=repository.pool,
            fallback_path=app_settings.assumptions_path,
            cache_ttl_days=app_settings.assumptions_cache_ttl_days,
        )
    else:
        repository = FileScenarioRepository(app_settings.data_dir)
        assumption_store = FileAssumptionStore(app_settings.assumptions_path)
    service = FamilyFinancialCompassService(
        repository=repository,
        assumption_store=assumption_store,
        default_user_id=app_settings.default_user_id,
        groq_api_key=app_settings.groq_api_key,
        groq_model=app_settings.groq_model,
        groq_base_url=app_settings.groq_base_url,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        close = getattr(repository, "close", None)
        if callable(close):
            close()

    app = FastAPI(
        title="Family Financial Compass API",
        version=service.model_version,
        lifespan=lifespan,
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

    def _process_health_payload() -> HealthEnvelope:
        return HealthEnvelope(
            status="ok",
            model_version=service.model_version,
            scenario_store=repository.storage_target,
            assumptions_path=str(app_settings.assumptions_path),
        )

    @app.exception_handler(ValueError)
    async def handle_value_error(_, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/healthz", response_model=HealthEnvelope)
    async def healthz() -> HealthEnvelope:
        return _process_health_payload()

    @app.get("/readyz", response_model=HealthEnvelope)
    async def readyz() -> HealthEnvelope:
        try:
            service.is_ready()
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"status": "unavailable", "detail": str(exc)},
            )
        current = service.current_assumptions_payload()
        return HealthEnvelope(
            status="ok",
            model_version=service.model_version,
            scenario_store=repository.storage_target,
            assumptions_path=str(app_settings.assumptions_path),
            assumptions_source=current["source"],
            assumptions_cache_date=current["cache_date"],
        )

    @app.get("/livez", response_model=HealthEnvelope)
    async def livez() -> HealthEnvelope:
        return _process_health_payload()

    @app.get("/v1/rent-vs-buy/assumptions/current", response_model=CurrentAssumptionsEnvelope)
    async def current_rent_vs_buy_assumptions() -> CurrentAssumptionsEnvelope:
        return CurrentAssumptionsEnvelope(**service.current_assumptions_payload())

    @app.post("/v1/rent-vs-buy/analyze", response_model=AnalysisEnvelope)
    async def analyze_rent_vs_buy(request: AnalyzeRequest) -> AnalysisEnvelope:
        payload = service.analyze_rent_vs_buy_payload(
            request.input.to_domain(),
            seed=request.simulation_seed,
            assumption_overrides=None if request.assumption_overrides is None else request.assumption_overrides.to_domain(),
            assumptions_snapshot=request.assumptions_snapshot,
            audit_trail_snapshot=request.audit_trail_snapshot,
        )
        return AnalysisEnvelope(**payload)

    @app.post("/v1/retirement-survival/analyze", response_model=AnalysisEnvelope)
    async def analyze_retirement_survival(request: RetirementAnalyzeRequest) -> AnalysisEnvelope:
        payload = service.analyze_retirement_survival_payload(
            request.input.to_domain(),
            seed=request.simulation_seed,
            assumptions_snapshot=request.assumptions_snapshot,
            audit_trail_snapshot=request.audit_trail_snapshot,
        )
        return AnalysisEnvelope(**payload)

    @app.post("/v1/job-offer/analyze", response_model=AnalysisEnvelope)
    async def analyze_job_offer(request: JobOfferAnalyzeRequest) -> AnalysisEnvelope:
        payload = service.analyze_job_offer_payload(
            request.input.to_domain(),
            seed=request.simulation_seed,
            assumptions_snapshot=request.assumptions_snapshot,
            audit_trail_snapshot=request.audit_trail_snapshot,
        )
        return AnalysisEnvelope(**payload)

    @app.post("/v1/college-vs-retirement/analyze", response_model=AnalysisEnvelope)
    async def analyze_college_vs_retirement(request: CollegeVsRetirementAnalyzeRequest) -> AnalysisEnvelope:
        payload = service.analyze_college_vs_retirement_payload(
            request.input.to_domain(),
            seed=request.simulation_seed,
            assumptions_snapshot=request.assumptions_snapshot,
            audit_trail_snapshot=request.audit_trail_snapshot,
        )
        return AnalysisEnvelope(**payload)

    @app.post("/v1/rent-vs-buy/report", response_model=ReportEnvelope)
    async def report_rent_vs_buy(request: AnalyzeRequest) -> ReportEnvelope:
        payload = service.build_rent_vs_buy_report_payload(
            request.input.to_domain(),
            seed=request.simulation_seed,
            assumption_overrides=None if request.assumption_overrides is None else request.assumption_overrides.to_domain(),
            assumptions_snapshot=request.assumptions_snapshot,
            audit_trail_snapshot=request.audit_trail_snapshot,
        )
        return ReportEnvelope(**payload)

    @app.post("/v1/rent-vs-buy/scenarios", response_model=ScenarioEnvelope)
    async def create_rent_vs_buy_scenario(request: CreateScenarioRequest) -> ScenarioEnvelope:
        bundle = service.create_rent_vs_buy_scenario(
            user_inputs=request.input.to_domain(),
            user_id=request.user_id,
            seed=request.simulation_seed,
            idempotency_key=request.idempotency_key,
            assumption_overrides=None if request.assumption_overrides is None else request.assumption_overrides.to_domain(),
            assumptions_snapshot=request.assumptions_snapshot,
            audit_trail_snapshot=request.audit_trail_snapshot,
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

    return app
