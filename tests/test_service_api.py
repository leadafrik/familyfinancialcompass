from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from family_financial_compass.api_models import CreateScenarioRequest, RentVsBuyInputModel
from family_financial_compass.config import DEFAULT_SYSTEM_ASSUMPTIONS, build_default_audit_trail
from family_financial_compass.models import (
    FilingStatus,
    HousingStatus,
    IncomeStability,
    LossBehavior,
    RiskProfile,
    UserScenarioInput,
)
from family_financial_compass.money import dollars_to_cents
from family_financial_compass.repository import FileScenarioRepository
from family_financial_compass.rent_vs_buy import RentVsBuyEngine
from family_financial_compass.service import FamilyFinancialCompassService


def test_api_models_are_strict_and_include_tax_fields() -> None:
    with pytest.raises(ValidationError):
        RentVsBuyInputModel(
            target_home_price_cents="55000000",
            down_payment_cents=11_000_000,
            loan_term_years=30,
            expected_years_in_home=7.0,
            current_monthly_rent_cents=285_000,
            annual_household_income_cents=21_000_000,
            current_savings_cents=15_000_000,
            monthly_savings_cents=200_000,
            expected_home_appreciation_rate=0.035,
            expected_investment_return_rate=0.07,
            risk_profile=RiskProfile.MODERATE,
            loss_behavior=LossBehavior.HOLD,
            income_stability=IncomeStability.STABLE,
            employment_tied_to_local_economy=False,
        )

    request = CreateScenarioRequest(
        input=RentVsBuyInputModel(
            target_home_price_cents=55_000_000,
            down_payment_cents=11_000_000,
            loan_term_years=30,
            expected_years_in_home=7.0,
            current_monthly_rent_cents=285_000,
            annual_household_income_cents=21_000_000,
            current_savings_cents=15_000_000,
            monthly_savings_cents=200_000,
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
        ),
        simulation_seed=7,
        user_id="user-1",
        idempotency_key="request-1",
    )

    assert request.input.marginal_tax_rate == pytest.approx(0.24)
    assert request.input.filing_status == FilingStatus.MARRIED_FILING_JOINTLY
    assert request.idempotency_key == "request-1"


def test_file_repository_and_service_are_idempotent() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    repository = FileScenarioRepository(Path.cwd() / "data")
    service = FamilyFinancialCompassService(
        engine=engine,
        repository=repository,
        audit_trail=build_default_audit_trail(),
        default_user_id="user-idempotent-test",
    )
    inputs = UserScenarioInput(
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

    first = service.create_rent_vs_buy_scenario(
        inputs,
        user_id="user-idempotent-test",
        seed=5,
        idempotency_key="same-key-idempotent-test",
    )
    second = service.create_rent_vs_buy_scenario(
        inputs,
        user_id="user-idempotent-test",
        seed=9,
        idempotency_key="same-key-idempotent-test",
    )

    assert first.scenario.id == second.scenario.id
    assert first.output.scenario_id == second.output.scenario_id
    assert repository.get(first.scenario.id) == first


def test_file_repository_list_for_user_is_cursor_paginated() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    repository = FileScenarioRepository(Path.cwd() / "data")
    service = FamilyFinancialCompassService(
        engine=engine,
        repository=repository,
        audit_trail=build_default_audit_trail(),
        default_user_id="user-pagination-test",
    )
    base_inputs = UserScenarioInput(
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

    service.create_rent_vs_buy_scenario(
        base_inputs,
        user_id="user-pagination-test",
        seed=1,
        idempotency_key="pagination-one",
    )
    service.create_rent_vs_buy_scenario(
        base_inputs,
        user_id="user-pagination-test",
        seed=2,
        idempotency_key="pagination-two",
    )
    service.create_rent_vs_buy_scenario(
        base_inputs,
        user_id="user-pagination-test",
        seed=3,
        idempotency_key="pagination-three",
    )

    first_page = repository.list_for_user(user_id="user-pagination-test", limit=2)

    assert len(first_page.items) == 2
    assert first_page.next_cursor is not None

    second_page = repository.list_for_user(
        user_id="user-pagination-test",
        limit=2,
        cursor=first_page.next_cursor,
    )

    assert len(second_page.items) >= 1
    assert len(second_page.items) <= 2


def test_report_payload_contains_model_backed_sections() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    repository = FileScenarioRepository(Path.cwd() / "data")
    service = FamilyFinancialCompassService(
        engine=engine,
        repository=repository,
        audit_trail=build_default_audit_trail(),
        default_user_id="user-report-test",
    )
    inputs = UserScenarioInput(
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

    payload = service.build_rent_vs_buy_report_payload(inputs, seed=7)

    assert payload["model_version"] == DEFAULT_SYSTEM_ASSUMPTIONS.model_version
    assert "informational and educational purposes only" in payload["disclaimer"]
    report = payload["report"]
    assert report["winner"] in {"buying", "renting"}
    assert len(report["yearly_net_worth"]) >= 1
    assert len(report["sensitivity"]["rows"]) == 9
    assert report["narrative_source"] == "template"
    assert report["year_one_costs"]["gross_annual_cents"] >= report["year_one_costs"]["true_annual_cents"]
    assert any(item["label"] == "Buyer closing costs" for item in report["audit_trail"])
    assert "does not reach break-even" in report["narratives"]["verdict_driver"]


def test_report_endpoint_is_available() -> None:
    from fastapi.testclient import TestClient

    from family_financial_compass.app import create_app
    from family_financial_compass.config import DEFAULT_ASSUMPTIONS_PATH
    from family_financial_compass.settings import AppSettings

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
                default_user_id="report-endpoint-test",
                scenario_list_default_limit=25,
                scenario_list_max_limit=100,
                allowed_origins=(),
                groq_api_key=None,
                groq_model="openai/gpt-oss-20b",
                groq_base_url="https://api.groq.com/openai/v1/chat/completions",
            )
        )
    )
    payload = {
        "input": {
            "target_home_price_cents": 55_000_000,
            "down_payment_cents": 11_000_000,
            "loan_term_years": 30,
            "expected_years_in_home": 7.0,
            "current_monthly_rent_cents": 285_000,
            "annual_household_income_cents": 21_000_000,
            "current_savings_cents": 15_000_000,
            "monthly_savings_cents": 200_000,
            "expected_home_appreciation_rate": 0.035,
            "expected_investment_return_rate": 0.07,
            "risk_profile": "moderate",
            "loss_behavior": "hold",
            "income_stability": "stable",
            "employment_tied_to_local_economy": False,
            "current_housing_status": "renting",
            "market_region": "national",
            "marginal_tax_rate": 0.24,
            "itemizes_deductions": False,
            "filing_status": "married_filing_jointly",
        },
        "simulation_seed": 7,
    }

    response = client.post("/v1/rent-vs-buy/report", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert "report" in body
    assert body["report"]["sensitivity"]["most_sensitive_label"]
