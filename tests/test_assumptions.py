from __future__ import annotations

import json
from uuid import uuid4
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from family_financial_compass.app import create_app
from family_financial_compass.assumptions import FileAssumptionStore, InMemoryAssumptionStore, apply_assumption_overrides
from family_financial_compass.config import (
    DEFAULT_ASSUMPTIONS_PATH,
    default_assumption_bundle,
    assumption_bundle_to_payload,
)
from family_financial_compass.models import AssumptionOverrides, RiskProfile, LossBehavior, IncomeStability, HousingStatus, FilingStatus, UserScenarioInput
from family_financial_compass.money import dollars_to_cents
from family_financial_compass.repository import FileScenarioRepository
from family_financial_compass.service import FamilyFinancialCompassService
from family_financial_compass.settings import AppSettings


def _base_inputs() -> UserScenarioInput:
    return UserScenarioInput(
        target_home_price_cents=dollars_to_cents(550_000),
        down_payment_cents=dollars_to_cents(110_000),
        loan_term_years=30,
        expected_years_in_home=7.0,
        current_monthly_rent_cents=dollars_to_cents(2_850),
        annual_household_income_cents=dollars_to_cents(210_000),
        current_savings_cents=dollars_to_cents(150_000),
        monthly_savings_cents=dollars_to_cents(2_000),
        expected_home_appreciation_rate=0.035,
        expected_investment_return_rate=0.07,
        risk_profile=RiskProfile.MODERATE,
        loss_behavior=LossBehavior.HOLD,
        income_stability=IncomeStability.STABLE,
        employment_tied_to_local_economy=False,
        current_housing_status=HousingStatus.RENTING,
        market_region="national",
        marginal_tax_rate=0.24,
        itemizes_deductions=False,
        filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
    )


def test_apply_assumption_overrides_updates_values_and_audit_trail() -> None:
    bundle = default_assumption_bundle()

    updated = apply_assumption_overrides(
        bundle,
        AssumptionOverrides(mortgage_rate=0.055, buyer_closing_cost_rate=0.04),
    )

    assert updated.assumptions.mortgage_rate == 0.055
    assert updated.assumptions.buyer_closing_cost_rate == 0.04
    mortgage_item = next(item for item in updated.audit_trail if item.parameter == "mortgage_rate")
    closing_item = next(item for item in updated.audit_trail if item.parameter == "buyer_closing_cost_rate")
    assert mortgage_item.source == "User override"
    assert mortgage_item.value == "5.50%"
    assert closing_item.value == "4.00%"


def test_file_assumption_store_reloads_updated_file() -> None:
    bundle = default_assumption_bundle()
    payload = assumption_bundle_to_payload(bundle)
    target = Path.cwd() / f".test-assumptions-{uuid4().hex}.json"
    try:
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        store = FileAssumptionStore(target)

        first = store.get_current_bundle()
        assert first.bundle.assumptions.mortgage_rate == bundle.assumptions.mortgage_rate

        payload["mortgage_rate"] = 0.05
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        second = store.get_current_bundle()

        assert second.bundle.assumptions.mortgage_rate == 0.05
    finally:
        if target.exists():
            target.unlink()


def test_service_re_resolves_assumptions_between_calls() -> None:
    repository = FileScenarioRepository(Path.cwd() / "data")
    bundle = default_assumption_bundle()
    store = InMemoryAssumptionStore(bundle)
    service = FamilyFinancialCompassService(
        repository=repository,
        assumption_store=store,
        default_user_id="dynamic-assumptions-test",
    )

    first = service.analyze_rent_vs_buy(_base_inputs(), seed=7)

    store.set_bundle(
        replace(
            bundle,
            assumptions=replace(bundle.assumptions, mortgage_rate=0.05),
        )
    )
    second = service.analyze_rent_vs_buy(_base_inputs(), seed=7)

    assert (
        second.deterministic.cost_breakdown.principal_and_interest_cents
        < first.deterministic.cost_breakdown.principal_and_interest_cents
    )


def test_service_accepts_snapshot_bundle_without_relabeling_sources() -> None:
    repository = FileScenarioRepository(Path.cwd() / "data")
    store = InMemoryAssumptionStore(default_assumption_bundle())
    service = FamilyFinancialCompassService(
        repository=repository,
        assumption_store=store,
        default_user_id="snapshot-assumptions-test",
    )
    snapshot_bundle = replace(
        default_assumption_bundle(),
        assumptions=replace(default_assumption_bundle().assumptions, mortgage_rate=0.05),
    )
    snapshot_payload = assumption_bundle_to_payload(snapshot_bundle)
    baseline = service.analyze_rent_vs_buy(_base_inputs(), seed=7)

    analysis = service.analyze_rent_vs_buy(
        _base_inputs(),
        seed=7,
        assumptions_snapshot={key: value for key, value in snapshot_payload.items() if key != "audit_trail"},
        audit_trail_snapshot=snapshot_payload["audit_trail"],
    )

    mortgage_item = next(item for item in analysis.audit_trail if item.parameter == "mortgage_rate")
    assert mortgage_item.source != "User override"
    assert (
        analysis.deterministic.cost_breakdown.principal_and_interest_cents
        < baseline.deterministic.cost_breakdown.principal_and_interest_cents
    )


def test_current_assumptions_endpoint_returns_runtime_bundle() -> None:
    client = TestClient(
        create_app(
            AppSettings(
                host="127.0.0.1",
                port=8000,
                scenario_store_backend="file",
                data_dir=Path.cwd() / "data",
                database_url=None,
                database_min_pool_size=1,
                database_max_pool_size=1,
                database_connect_timeout_seconds=5.0,
                assumptions_path=DEFAULT_ASSUMPTIONS_PATH,
                assumptions_cache_ttl_days=1,
                default_user_id="assumptions-endpoint-test",
                scenario_list_default_limit=25,
                scenario_list_max_limit=100,
                allowed_origins=(),
                groq_api_key=None,
                groq_model="openai/gpt-oss-20b",
                groq_base_url="https://api.groq.com/openai/v1/chat/completions",
            )
        )
    )

    response = client.get("/v1/rent-vs-buy/assumptions/current")

    assert response.status_code == 200
    body = response.json()
    assert body["assumptions"]["mortgage_rate"] > 0
    assert body["source"] in {"file", "postgres:auto"}
