from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from family_financial_compass import assumptions as assumptions_module
from family_financial_compass.app import create_app
from family_financial_compass.assumptions import (
    BlsSeriesSnapshot,
    FileAssumptionStore,
    InMemoryAssumptionStore,
    LoadedAssumptionBundle,
    MortgageRateSnapshot,
    OnlineMarketDataClient,
    PostgresAssumptionStore,
    apply_assumption_overrides,
)
from family_financial_compass.config import (
    DEFAULT_CORRELATION_MATRIX,
    DEFAULT_ASSUMPTIONS_PATH,
    DEFAULT_SYSTEM_ASSUMPTIONS,
    assumption_bundle_from_payload,
    default_assumption_bundle,
    assumption_bundle_to_payload,
    build_behavioral_audit_trail,
    build_default_audit_trail,
)
from family_financial_compass.college_vs_retirement import CollegeVsRetirementEngine
from family_financial_compass.job_offer import JobOfferEngine
from family_financial_compass.models import (
    AssumptionOverrides,
    CollegeVsRetirementScenarioInput,
    FilingStatus,
    HousingStatus,
    IncomeStability,
    JobOffer,
    JobOfferScenarioInput,
    LossBehavior,
    RetirementScenarioInput,
    RiskProfile,
    UserScenarioInput,
)
from family_financial_compass.money import dollars_to_cents
from family_financial_compass.repository import FileScenarioRepository
from family_financial_compass.retirement_survival import RetirementSurvivalEngine
from family_financial_compass.rent_vs_buy import RentVsBuyEngine
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


def _retirement_inputs() -> RetirementScenarioInput:
    return RetirementScenarioInput(
        current_portfolio_cents=dollars_to_cents(1_250_000),
        annual_spending_cents=dollars_to_cents(62_000),
        annual_guaranteed_income_cents=dollars_to_cents(18_000),
        retirement_years=30,
        expected_annual_return_rate=0.06,
        risk_profile=RiskProfile.MODERATE,
        loss_behavior=LossBehavior.HOLD,
    )


def _job_offer_inputs() -> JobOfferScenarioInput:
    return JobOfferScenarioInput(
        offer_a=JobOffer(
            label="Offer A",
            base_salary_cents=dollars_to_cents(220_000),
            target_bonus_cents=dollars_to_cents(30_000),
            annual_equity_vesting_cents=dollars_to_cents(40_000),
            sign_on_bonus_cents=dollars_to_cents(20_000),
            relocation_cost_cents=0,
            annual_cost_of_living_delta_cents=0,
            annual_commute_cost_cents=dollars_to_cents(3_000),
            annual_comp_growth_rate=0.03,
            annual_equity_growth_rate=0.02,
            bonus_payout_volatility=0.18,
            equity_volatility=0.45,
        ),
        offer_b=JobOffer(
            label="Offer B",
            base_salary_cents=dollars_to_cents(240_000),
            target_bonus_cents=dollars_to_cents(45_000),
            annual_equity_vesting_cents=dollars_to_cents(80_000),
            sign_on_bonus_cents=dollars_to_cents(35_000),
            relocation_cost_cents=dollars_to_cents(12_000),
            annual_cost_of_living_delta_cents=dollars_to_cents(8_000),
            annual_commute_cost_cents=dollars_to_cents(4_500),
            annual_comp_growth_rate=0.04,
            annual_equity_growth_rate=0.03,
            bonus_payout_volatility=0.25,
            equity_volatility=0.70,
        ),
        comparison_years=4,
        marginal_tax_rate=0.24,
        local_market_concentration=False,
    )


def _college_inputs() -> CollegeVsRetirementScenarioInput:
    return CollegeVsRetirementScenarioInput(
        current_retirement_savings_cents=dollars_to_cents(350_000),
        current_college_savings_cents=dollars_to_cents(40_000),
        annual_savings_budget_cents=dollars_to_cents(24_000),
        annual_college_cost_cents=dollars_to_cents(38_000),
        years_until_college=6,
        years_in_college=4,
        retirement_years=18,
        expected_annual_return_rate=0.06,
        risk_profile=RiskProfile.MODERATE,
        loss_behavior=LossBehavior.HOLD,
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
                groq_model="llama-3.3-70b-versatile",
                groq_base_url="https://api.groq.com/openai/v1/chat/completions",
            )
        )
    )

    response = client.get("/v1/rent-vs-buy/assumptions/current")

    assert response.status_code == 200
    body = response.json()
    assert body["assumptions"]["mortgage_rate"] > 0
    assert body["source"] in {"file", "postgres:auto"}


def test_default_audit_trail_is_tuple_and_matches_defaults() -> None:
    audit_trail = build_default_audit_trail()
    values = {item.parameter: item.value for item in audit_trail if item.parameter}

    assert isinstance(audit_trail, tuple)
    assert len(audit_trail) == 16
    assert values["mortgage_rate"] == f"{DEFAULT_SYSTEM_ASSUMPTIONS.mortgage_rate * 100:.2f}%"
    assert values["property_tax_rate"] == f"{DEFAULT_SYSTEM_ASSUMPTIONS.property_tax_rate * 100:.2f}%"
    assert values["annual_home_insurance_cents"] == f"${DEFAULT_SYSTEM_ASSUMPTIONS.annual_home_insurance_cents / 100:,.0f}"
    assert values["annual_rent_growth_rate"] == f"{DEFAULT_SYSTEM_ASSUMPTIONS.annual_rent_growth_rate * 100:.2f}%"
    assert values["buyer_closing_cost_rate"] == f"{DEFAULT_SYSTEM_ASSUMPTIONS.buyer_closing_cost_rate * 100:.2f}%"


def test_assumption_bundle_from_payload_defaults_missing_correlation_matrix() -> None:
    payload = assumption_bundle_to_payload(default_assumption_bundle())
    payload["monte_carlo"].pop("correlation_matrix")

    bundle = assumption_bundle_from_payload(payload)

    assert bundle.assumptions.monte_carlo.correlation_matrix == DEFAULT_CORRELATION_MATRIX


def test_fetch_bls_series_uses_registration_key_and_wider_window(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class DummyResponse:
        def __enter__(self) -> "DummyResponse":
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "Results": {
                        "series": [
                            {
                                "data": [
                                    {"year": "2026", "period": "M02", "value": "130"},
                                    {"year": "2025", "period": "M02", "value": "120"},
                                ]
                            }
                        ]
                    }
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout: int):
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return DummyResponse()

    monkeypatch.setattr(assumptions_module, "urlopen", fake_urlopen)

    client = OnlineMarketDataClient(timeout_seconds=9, bls_api_key="demo-key")
    snapshot = client.fetch_bls_series("CUUR0000SEHA")
    payload = captured["payload"]
    current_year = datetime.now(timezone.utc).year

    assert snapshot.yoy_change == pytest.approx((130 / 120) - 1.0)
    assert captured["timeout"] == 9
    assert payload["registrationkey"] == "demo-key"
    assert payload["startyear"] == str(current_year - 3)


def test_dynamic_bundle_applies_partial_success_and_caps_insurance() -> None:
    class PartialMarketClient:
        def fetch_primary_mortgage_market_survey(self) -> MortgageRateSnapshot:
            return MortgageRateSnapshot(
                rate_date=date(2026, 4, 3),
                thirty_year_fixed=0.05,
                fifteen_year_fixed=0.042,
                source_name="Freddie Mac PMMS",
            )

        def fetch_bls_series(self, series_id: str) -> BlsSeriesSnapshot:
            if series_id == assumptions_module._BLS_RENT_SERIES_ID:
                raise ValueError("rent unavailable")
            return BlsSeriesSnapshot(
                series_id=series_id,
                observation_date=date(2026, 3, 1),
                value=1000.0,
                yoy_change=0.08,
                source_name="BLS CPI",
            )

    store = PostgresAssumptionStore(
        pool=None,
        fallback_path=DEFAULT_ASSUMPTIONS_PATH,
        market_data_client=PartialMarketClient(),
    )
    base_bundle = default_assumption_bundle()

    refreshed_bundle, dynamic_inputs = store._build_dynamic_bundle(
        base_bundle,
        {"insurance_series": {"value": 1.0}},
    )

    mortgage_item = next(item for item in refreshed_bundle.audit_trail if item.parameter == "mortgage_rate")
    rent_item = next(item for item in refreshed_bundle.audit_trail if item.parameter == "annual_rent_growth_rate")
    base_rent_item = next(item for item in base_bundle.audit_trail if item.parameter == "annual_rent_growth_rate")

    assert refreshed_bundle.assumptions.mortgage_rate == 0.05
    assert refreshed_bundle.assumptions.annual_rent_growth_rate == base_bundle.assumptions.annual_rent_growth_rate
    assert refreshed_bundle.assumptions.annual_home_insurance_cents == int(DEFAULT_SYSTEM_ASSUMPTIONS.annual_home_insurance_cents * 3.0)
    assert mortgage_item.source == "Freddie Mac PMMS"
    assert rent_item == base_rent_item
    assert "mortgage_rate" in dynamic_inputs
    assert "rent_series" not in dynamic_inputs
    assert "insurance_series" in dynamic_inputs
    assert store._dynamic_source_label(dynamic_inputs) == "postgres:partial"


def test_postgres_store_cache_fresh_path_does_not_load_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyConnectionContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *_args: object) -> bool:
            return False

    class DummyPool:
        def connection(self) -> DummyConnectionContext:
            return DummyConnectionContext()

    loaded = LoadedAssumptionBundle(
        bundle=default_assumption_bundle(),
        source="postgres:auto",
        cache_date=datetime.now(timezone.utc).date(),
    )

    class CacheFreshStore(PostgresAssumptionStore):
        def __init__(self) -> None:
            super().__init__(pool=DummyPool(), fallback_path=DEFAULT_ASSUMPTIONS_PATH, market_data_client=OnlineMarketDataClient())

        def _ensure_schema(self, conn: object) -> None:
            return None

        def _fetch_active_row(self, conn: object) -> dict[str, object]:
            return {
                "refresh_mode": "auto",
                "source_label": "postgres:auto",
                "dynamic_inputs_json": {},
            }

        def _row_to_loaded_bundle(self, row: dict[str, object]) -> LoadedAssumptionBundle:
            return loaded

    def fail_load(_path: Path) -> AssumptionBundle:
        raise AssertionError("fallback bundle should not be loaded on cache-fresh path")

    from family_financial_compass.config import AssumptionBundle

    monkeypatch.setattr(assumptions_module, "load_assumption_bundle", fail_load)

    store = CacheFreshStore()

    assert store.get_current_bundle() == loaded


def test_default_audit_trail_covers_all_system_assumption_fields() -> None:
    trail = build_default_audit_trail()
    parameters = {item.parameter for item in trail}
    required = {
        "mortgage_rate",
        "property_tax_rate",
        "annual_home_insurance_cents",
        "annual_rent_growth_rate",
        "buyer_closing_cost_rate",
        "maintenance_rate",
        "selling_cost_rate",
        "annual_pmi_rate",
        "loss_aversion_lambda",
        "panic_sale_expected_return_penalty",
        "liquidity_premium_rate",
        "monte_carlo_scenario_count",
        "monte_carlo_calibration",
        "college_tuition_inflation_rate",
        "college_student_loan_rate",
        "college_student_loan_term_years",
    }
    missing = required - parameters
    assert not missing, f"Missing audit trail coverage for: {missing}"


def test_behavioral_audit_trail_covers_calibration_assumptions() -> None:
    trail = build_behavioral_audit_trail()
    parameters = {item.parameter for item in trail}
    required = {
        "loss_aversion_lambda",
        "panic_sale_expected_return_penalty",
        "liquidity_premium_rate_stable",
        "liquidity_premium_rate_variable",
        "scenario_count",
        "appreciation_stddev",
        "investment_volatility_conservative",
        "investment_volatility_moderate",
        "investment_volatility_aggressive",
    }
    missing = required - parameters
    assert not missing, f"Missing behavioral audit items for: {missing}"


def test_no_audit_item_has_hardcoded_value_string_that_diverges_from_defaults() -> None:
    default_values = {item.parameter: item.value for item in build_default_audit_trail() if item.parameter}
    behavioral_values = {item.parameter: item.value for item in build_behavioral_audit_trail() if item.parameter}

    expected_default_values = {
        "mortgage_rate": f"{DEFAULT_SYSTEM_ASSUMPTIONS.mortgage_rate * 100:.2f}%",
        "property_tax_rate": f"{DEFAULT_SYSTEM_ASSUMPTIONS.property_tax_rate * 100:.2f}%",
        "annual_home_insurance_cents": f"${DEFAULT_SYSTEM_ASSUMPTIONS.annual_home_insurance_cents / 100:,.0f}",
        "annual_rent_growth_rate": f"{DEFAULT_SYSTEM_ASSUMPTIONS.annual_rent_growth_rate * 100:.2f}%",
        "buyer_closing_cost_rate": f"{DEFAULT_SYSTEM_ASSUMPTIONS.buyer_closing_cost_rate * 100:.2f}%",
        "maintenance_rate": f"{DEFAULT_SYSTEM_ASSUMPTIONS.maintenance_rate * 100:.2f}%",
        "selling_cost_rate": f"{DEFAULT_SYSTEM_ASSUMPTIONS.selling_cost_rate * 100:.2f}%",
        "annual_pmi_rate": f"{DEFAULT_SYSTEM_ASSUMPTIONS.annual_pmi_rate * 100:.2f}%",
        "loss_aversion_lambda": round(DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.loss_aversion_lambda, 2),
        "panic_sale_expected_return_penalty": f"{DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.panic_sale_expected_return_penalty * 100:.2f}%",
        "liquidity_premium_rate": (
            f"{DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.stable_income_liquidity_premium * 100:.2f}% "
            f"(stable) / "
            f"{DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.variable_income_liquidity_premium * 100:.2f}% "
            f"(variable income)"
        ),
        "monte_carlo_scenario_count": DEFAULT_SYSTEM_ASSUMPTIONS.monte_carlo.scenario_count,
        "college_tuition_inflation_rate": f"{DEFAULT_SYSTEM_ASSUMPTIONS.college_tuition_inflation_rate * 100:.2f}%",
        "college_student_loan_rate": f"{DEFAULT_SYSTEM_ASSUMPTIONS.college_student_loan_rate * 100:.2f}%",
        "college_student_loan_term_years": f"{DEFAULT_SYSTEM_ASSUMPTIONS.college_student_loan_term_years} years",
    }
    expected_behavioral_values = {
        "loss_aversion_lambda": round(DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.loss_aversion_lambda, 2),
        "panic_sale_expected_return_penalty": f"{DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.panic_sale_expected_return_penalty * 100:.2f}%",
        "liquidity_premium_rate_stable": f"{DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.stable_income_liquidity_premium * 100:.2f}%",
        "liquidity_premium_rate_variable": f"{DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.variable_income_liquidity_premium * 100:.2f}%",
        "scenario_count": DEFAULT_SYSTEM_ASSUMPTIONS.monte_carlo.scenario_count,
        "investment_volatility_conservative": f"{DEFAULT_SYSTEM_ASSUMPTIONS.monte_carlo.investment_volatility_by_risk[RiskProfile.CONSERVATIVE].stated * 100:.2f}%",
        "investment_volatility_moderate": f"{DEFAULT_SYSTEM_ASSUMPTIONS.monte_carlo.investment_volatility_by_risk[RiskProfile.MODERATE].stated * 100:.2f}%",
        "investment_volatility_aggressive": f"{DEFAULT_SYSTEM_ASSUMPTIONS.monte_carlo.investment_volatility_by_risk[RiskProfile.AGGRESSIVE].stated * 100:.2f}%",
        "appreciation_stddev": f"{DEFAULT_SYSTEM_ASSUMPTIONS.monte_carlo.appreciation_stddev * 100:.2f}%",
    }

    for parameter, expected in expected_default_values.items():
        assert default_values[parameter] == expected
    for parameter, expected in expected_behavioral_values.items():
        assert behavioral_values[parameter] == expected


def test_all_audit_items_have_source_and_value() -> None:
    trail = build_default_audit_trail() + build_behavioral_audit_trail()
    for item in trail:
        assert item.source, f"Audit item '{item.name}' has no source"
        assert item.value is not None, f"Audit item '{item.name}' has no value"


def test_rent_vs_buy_audit_trail_is_complete() -> None:
    analysis = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS).analyze(_base_inputs(), seed=7)
    parameters = {item.parameter for item in analysis.audit_trail if item.parameter}

    assert {
        "maintenance_rate",
        "selling_cost_rate",
        "annual_pmi_rate",
        "loss_aversion_lambda",
        "expected_home_appreciation_rate",
        "liquidity_premium_rate",
        "investment_return_volatility",
    } <= parameters


def test_retirement_audit_trail_is_complete() -> None:
    analysis = RetirementSurvivalEngine(DEFAULT_SYSTEM_ASSUMPTIONS).analyze(_retirement_inputs(), seed=7)
    parameters = {item.parameter for item in analysis.audit_trail if item.parameter}

    assert {
        "loss_aversion_lambda",
        "retirement_return_autocorrelation",
        "expected_annual_return_rate",
        "retirement_return_volatility",
        "scenario_count",
    } <= parameters


def test_job_offer_audit_trail_is_complete() -> None:
    analysis = JobOfferEngine(DEFAULT_SYSTEM_ASSUMPTIONS).analyze(_job_offer_inputs(), seed=7)
    parameters = {item.parameter for item in analysis.audit_trail if item.parameter}

    assert {
        "job_offer_bonus_market_beta",
        "job_offer_equity_market_beta",
        "loss_aversion_lambda",
        "scenario_count",
    } <= parameters


def test_college_audit_trail_is_complete() -> None:
    analysis = CollegeVsRetirementEngine(DEFAULT_SYSTEM_ASSUMPTIONS).analyze(_college_inputs(), seed=7)
    parameters = {item.parameter for item in analysis.audit_trail if item.parameter}

    assert {
        "college_tuition_inflation_rate",
        "college_student_loan_rate",
        "college_student_loan_term_years",
        "college_vs_retirement_return_volatility",
        "loss_aversion_lambda",
        "scenario_count",
    } <= parameters
