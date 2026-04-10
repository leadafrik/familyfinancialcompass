from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
from uuid import uuid4

from typing import Any

from .models import ScenarioOutputRecord, ScenarioRecord, SystemAssumptions


def serialize_model(value):
    if is_dataclass(value):
        return {key: serialize_model(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): serialize_model(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_model(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def create_saved_scenario(
    user_id: str,
    user_inputs: Any,
    system_assumptions: SystemAssumptions,
    analysis: Any,
    module: str = "rent_vs_buy",
    idempotency_key: str | None = None,
) -> tuple[ScenarioRecord, ScenarioOutputRecord]:
    scenario_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    scenario = ScenarioRecord(
        id=scenario_id,
        user_id=user_id,
        created_at=now,
        inputs_snapshot=serialize_model(user_inputs),
        assumptions_snapshot=serialize_model(system_assumptions),
        model_version=system_assumptions.model_version,
        module=module,
        idempotency_key=idempotency_key,
    )
    scenario_output = ScenarioOutputRecord(
        scenario_id=scenario_id,
        computed_at=now,
        output_blob=serialize_model(analysis),
    )
    return scenario, scenario_output
