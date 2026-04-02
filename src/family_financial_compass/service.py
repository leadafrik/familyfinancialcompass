from __future__ import annotations

from .legal import OUTPUT_DISCLAIMER
from .models import RentVsBuyAnalysis, UserScenarioInput
from .rent_vs_buy import RentVsBuyEngine
from .repository import ScenarioBundle, ScenarioPage, ScenarioRepository
from .scenario import create_saved_scenario, serialize_model


class FamilyFinancialCompassService:
    def __init__(
        self,
        engine: RentVsBuyEngine,
        repository: ScenarioRepository,
        audit_trail: list | tuple,
        default_user_id: str = "anonymous",
    ):
        self.engine = engine
        self.repository = repository
        self.audit_trail = list(audit_trail)
        self.default_user_id = default_user_id

    @property
    def model_version(self) -> str:
        return self.engine.assumptions.model_version

    def analyze_rent_vs_buy(self, user_inputs: UserScenarioInput, seed: int = 7) -> RentVsBuyAnalysis:
        return self.engine.analyze(user_inputs, audit_trail=list(self.audit_trail), seed=seed)

    def analyze_rent_vs_buy_payload(self, user_inputs: UserScenarioInput, seed: int = 7) -> dict:
        analysis = self.analyze_rent_vs_buy(user_inputs, seed=seed)
        return {
            "model_version": self.model_version,
            "disclaimer": OUTPUT_DISCLAIMER,
            "analysis": serialize_model(analysis),
        }

    def create_rent_vs_buy_scenario(
        self,
        user_inputs: UserScenarioInput,
        user_id: str | None = None,
        seed: int = 7,
        idempotency_key: str | None = None,
    ) -> ScenarioBundle:
        resolved_user_id = user_id or self.default_user_id
        analysis = self.analyze_rent_vs_buy(user_inputs, seed=seed)
        scenario, output = create_saved_scenario(
            user_id=resolved_user_id,
            user_inputs=user_inputs,
            system_assumptions=self.engine.assumptions,
            analysis=analysis,
            idempotency_key=idempotency_key,
        )
        return self.repository.save(scenario, output)

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
