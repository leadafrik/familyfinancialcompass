from __future__ import annotations

from .assumptions import InMemoryAssumptionStore, apply_assumption_overrides
from .config import AssumptionBundle, assumption_bundle_from_payload
from .job_offer import JobOfferEngine
from .legal import OUTPUT_DISCLAIMER
from .models import (
    AssumptionOverrides,
    JobOfferAnalysis,
    JobOfferScenarioInput,
    RetirementScenarioInput,
    RetirementSurvivalAnalysis,
    RentVsBuyAnalysis,
    UserScenarioInput,
)
from .reporting import build_rent_vs_buy_report
from .retirement_survival import RetirementSurvivalEngine
from .rent_vs_buy import RentVsBuyEngine
from .repository import ScenarioBundle, ScenarioPage, ScenarioRepository
from .scenario import create_saved_scenario, serialize_model


class FamilyFinancialCompassService:
    def __init__(
        self,
        repository: ScenarioRepository,
        assumption_store=None,
        engine: RentVsBuyEngine | None = None,
        audit_trail: list | tuple = (),
        default_user_id: str = "anonymous",
        groq_api_key: str | None = None,
        groq_model: str = "llama-3.3-70b-versatile",
        groq_base_url: str = "https://api.groq.com/openai/v1/chat/completions",
    ):
        self.repository = repository
        if assumption_store is None:
            if engine is None:
                raise ValueError("Either assumption_store or engine must be provided.")
            assumption_store = InMemoryAssumptionStore(
                AssumptionBundle(
                    assumptions=engine.assumptions,
                    audit_trail=tuple(audit_trail),
                )
            )
        self.assumption_store = assumption_store
        self.default_user_id = default_user_id
        self.groq_api_key = groq_api_key
        self.groq_model = groq_model
        self.groq_base_url = groq_base_url

    @property
    def model_version(self) -> str:
        return self.assumption_store.get_current_bundle().bundle.assumptions.model_version

    def _resolve_bundle(
        self,
        assumption_overrides: AssumptionOverrides | None = None,
        assumptions_snapshot: dict | None = None,
        audit_trail_snapshot: list[dict] | None = None,
    ):
        if assumptions_snapshot is not None:
            payload = dict(assumptions_snapshot)
            payload["audit_trail"] = list(audit_trail_snapshot or [])
            bundle = assumption_bundle_from_payload(payload)
            return None, apply_assumption_overrides(bundle, assumption_overrides)

        loaded = self.assumption_store.get_current_bundle()
        bundle = apply_assumption_overrides(loaded.bundle, assumption_overrides)
        return loaded, bundle

    def _resolve_engine(
        self,
        assumption_overrides: AssumptionOverrides | None = None,
        assumptions_snapshot: dict | None = None,
        audit_trail_snapshot: list[dict] | None = None,
    ) -> tuple[RentVsBuyEngine, list, AssumptionBundle]:
        _, bundle = self._resolve_bundle(
            assumption_overrides,
            assumptions_snapshot=assumptions_snapshot,
            audit_trail_snapshot=audit_trail_snapshot,
        )
        return RentVsBuyEngine(bundle.assumptions), list(bundle.audit_trail), bundle

    def analyze_rent_vs_buy(
        self,
        user_inputs: UserScenarioInput,
        seed: int = 7,
        assumption_overrides: AssumptionOverrides | None = None,
        assumptions_snapshot: dict | None = None,
        audit_trail_snapshot: list[dict] | None = None,
    ) -> RentVsBuyAnalysis:
        engine, audit_trail, _ = self._resolve_engine(
            assumption_overrides,
            assumptions_snapshot=assumptions_snapshot,
            audit_trail_snapshot=audit_trail_snapshot,
        )
        return engine.analyze(user_inputs, audit_trail=audit_trail, seed=seed)

    def analyze_rent_vs_buy_payload(
        self,
        user_inputs: UserScenarioInput,
        seed: int = 7,
        assumption_overrides: AssumptionOverrides | None = None,
        assumptions_snapshot: dict | None = None,
        audit_trail_snapshot: list[dict] | None = None,
    ) -> dict:
        _, bundle = self._resolve_bundle(
            assumption_overrides,
            assumptions_snapshot=assumptions_snapshot,
            audit_trail_snapshot=audit_trail_snapshot,
        )
        analysis = RentVsBuyEngine(bundle.assumptions).analyze(
            user_inputs,
            audit_trail=list(bundle.audit_trail),
            seed=seed,
        )
        return {
            "model_version": bundle.assumptions.model_version,
            "disclaimer": OUTPUT_DISCLAIMER,
            "analysis": serialize_model(analysis),
        }

    def analyze_retirement_survival(
        self,
        user_inputs: RetirementScenarioInput,
        seed: int = 7,
        assumptions_snapshot: dict | None = None,
        audit_trail_snapshot: list[dict] | None = None,
    ) -> RetirementSurvivalAnalysis:
        _, bundle = self._resolve_bundle(
            assumptions_snapshot=assumptions_snapshot,
            audit_trail_snapshot=audit_trail_snapshot,
        )
        engine = RetirementSurvivalEngine(bundle.assumptions)
        return engine.analyze(user_inputs, audit_trail=list(bundle.audit_trail), seed=seed)

    def analyze_retirement_survival_payload(
        self,
        user_inputs: RetirementScenarioInput,
        seed: int = 7,
        assumptions_snapshot: dict | None = None,
        audit_trail_snapshot: list[dict] | None = None,
    ) -> dict:
        _, bundle = self._resolve_bundle(
            assumptions_snapshot=assumptions_snapshot,
            audit_trail_snapshot=audit_trail_snapshot,
        )
        analysis = RetirementSurvivalEngine(bundle.assumptions).analyze(
            user_inputs,
            audit_trail=list(bundle.audit_trail),
            seed=seed,
        )
        return {
            "model_version": bundle.assumptions.model_version,
            "disclaimer": OUTPUT_DISCLAIMER,
            "analysis": serialize_model(analysis),
        }

    def analyze_job_offer(
        self,
        user_inputs: JobOfferScenarioInput,
        seed: int = 7,
        assumptions_snapshot: dict | None = None,
        audit_trail_snapshot: list[dict] | None = None,
    ) -> JobOfferAnalysis:
        _, bundle = self._resolve_bundle(
            assumptions_snapshot=assumptions_snapshot,
            audit_trail_snapshot=audit_trail_snapshot,
        )
        engine = JobOfferEngine(bundle.assumptions)
        return engine.analyze(user_inputs, audit_trail=list(bundle.audit_trail), seed=seed)

    def analyze_job_offer_payload(
        self,
        user_inputs: JobOfferScenarioInput,
        seed: int = 7,
        assumptions_snapshot: dict | None = None,
        audit_trail_snapshot: list[dict] | None = None,
    ) -> dict:
        _, bundle = self._resolve_bundle(
            assumptions_snapshot=assumptions_snapshot,
            audit_trail_snapshot=audit_trail_snapshot,
        )
        analysis = JobOfferEngine(bundle.assumptions).analyze(
            user_inputs,
            audit_trail=list(bundle.audit_trail),
            seed=seed,
        )
        return {
            "model_version": bundle.assumptions.model_version,
            "disclaimer": OUTPUT_DISCLAIMER,
            "analysis": serialize_model(analysis),
        }

    def build_rent_vs_buy_report_payload(
        self,
        user_inputs: UserScenarioInput,
        seed: int = 7,
        assumption_overrides: AssumptionOverrides | None = None,
        assumptions_snapshot: dict | None = None,
        audit_trail_snapshot: list[dict] | None = None,
    ) -> dict:
        engine, audit_trail, bundle = self._resolve_engine(
            assumption_overrides,
            assumptions_snapshot=assumptions_snapshot,
            audit_trail_snapshot=audit_trail_snapshot,
        )
        report = build_rent_vs_buy_report(
            engine=engine,
            user_inputs=user_inputs,
            audit_trail=audit_trail,
            seed=seed,
            groq_api_key=self.groq_api_key,
            groq_model=self.groq_model,
            groq_base_url=self.groq_base_url,
        )
        return {
            "model_version": bundle.assumptions.model_version,
            "disclaimer": OUTPUT_DISCLAIMER,
            "report": serialize_model(report),
        }

    def create_rent_vs_buy_scenario(
        self,
        user_inputs: UserScenarioInput,
        user_id: str | None = None,
        seed: int = 7,
        idempotency_key: str | None = None,
        assumption_overrides: AssumptionOverrides | None = None,
        assumptions_snapshot: dict | None = None,
        audit_trail_snapshot: list[dict] | None = None,
    ) -> ScenarioBundle:
        resolved_user_id = user_id or self.default_user_id
        engine, audit_trail, bundle = self._resolve_engine(
            assumption_overrides,
            assumptions_snapshot=assumptions_snapshot,
            audit_trail_snapshot=audit_trail_snapshot,
        )
        analysis = engine.analyze(
            user_inputs,
            audit_trail=audit_trail,
            seed=seed,
        )
        scenario, output = create_saved_scenario(
            user_id=resolved_user_id,
            user_inputs=user_inputs,
            system_assumptions=bundle.assumptions,
            analysis=analysis,
            idempotency_key=idempotency_key,
        )
        return self.repository.save(scenario, output)

    def current_assumptions_payload(self) -> dict:
        loaded = self.assumption_store.get_current_bundle()
        return {
            "model_version": loaded.bundle.assumptions.model_version,
            "disclaimer": OUTPUT_DISCLAIMER,
            "source": loaded.source,
            "cache_date": loaded.cache_date.isoformat(),
            "assumptions": serialize_model(loaded.bundle.assumptions),
            "audit_trail": serialize_model(list(loaded.bundle.audit_trail)),
        }

    def is_ready(self) -> None:
        """Raises if the backing store is unreachable. Used by /readyz."""
        self.repository.ping()

    def get_scenario(self, scenario_id: str) -> ScenarioBundle | None:
        return self.repository.get(scenario_id)

    def list_scenarios(self, user_id: str, limit: int, cursor: str | None = None) -> ScenarioPage:
        return self.repository.list_for_user(user_id=user_id, limit=limit, cursor=cursor)

    def serialize_scenario_bundle(self, bundle: ScenarioBundle) -> dict:
        return {
            "scenario_id": bundle.scenario.id,
            "user_id": bundle.scenario.user_id,
            "created_at": bundle.scenario.created_at,
            "computed_at": bundle.output.computed_at,
            "model_version": bundle.scenario.model_version,
            "disclaimer": OUTPUT_DISCLAIMER,
            "inputs_snapshot": bundle.scenario.inputs_snapshot,
            "assumptions_snapshot": bundle.scenario.assumptions_snapshot,
            "analysis": bundle.output.output_blob,
        }
