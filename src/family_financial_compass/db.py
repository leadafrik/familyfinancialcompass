from __future__ import annotations

from typing import Protocol

from .models import ScenarioOutputRecord, ScenarioRecord


class ScenarioRepository(Protocol):
    def save_scenario(self, record: ScenarioRecord) -> str: ...

    def save_output(self, record: ScenarioOutputRecord) -> str: ...

    def get_scenario(self, scenario_id: str) -> ScenarioRecord | None: ...

    def get_output(self, scenario_id: str) -> ScenarioOutputRecord | None: ...


class InMemoryScenarioRepository:
    def __init__(self) -> None:
        self._scenarios: dict[str, ScenarioRecord] = {}
        self._outputs: dict[str, ScenarioOutputRecord] = {}

    def save_scenario(self, record: ScenarioRecord) -> str:
        self._scenarios[record.scenario_id] = record
        return record.scenario_id

    def save_output(self, record: ScenarioOutputRecord) -> str:
        self._outputs[record.scenario_id] = record
        return record.scenario_id

    def get_scenario(self, scenario_id: str) -> ScenarioRecord | None:
        return self._scenarios.get(scenario_id)

    def get_output(self, scenario_id: str) -> ScenarioOutputRecord | None:
        return self._outputs.get(scenario_id)
