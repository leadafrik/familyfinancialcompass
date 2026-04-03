from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from family_financial_compass.app import create_app
from family_financial_compass.college_vs_retirement import CollegeVsRetirementEngine
from family_financial_compass.config import DEFAULT_ASSUMPTIONS_PATH, DEFAULT_SYSTEM_ASSUMPTIONS
from family_financial_compass.models import CollegeVsRetirementScenarioInput, LossBehavior, RiskProfile
from family_financial_compass.money import dollars_to_cents
from family_financial_compass.settings import AppSettings


def _base_input() -> CollegeVsRetirementScenarioInput:
    return CollegeVsRetirementScenarioInput(
        current_retirement_savings_cents=dollars_to_cents(400_000),
        current_college_savings_cents=dollars_to_cents(20_000),
        annual_savings_budget_cents=dollars_to_cents(18_000),
        annual_college_cost_cents=dollars_to_cents(35_000),
        years_until_college=8,
        years_in_college=4,
        retirement_years=18,
        expected_annual_return_rate=0.06,
        risk_profile=RiskProfile.MODERATE,
        loss_behavior=LossBehavior.HOLD,
    )


def _test_settings() -> AppSettings:
    return AppSettings(
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
        default_user_id="college-vs-retirement-endpoint-test",
        scenario_list_default_limit=25,
        scenario_list_max_limit=100,
        allowed_origins=(),
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        groq_base_url="https://api.groq.com/openai/v1/chat/completions",
    )


def test_college_first_reduces_student_loan_pressure() -> None:
    engine = CollegeVsRetirementEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    analysis = engine.analyze(_base_input(), seed=7)

    assert (
        analysis.deterministic.college_first_total_loan_cents
        < analysis.deterministic.retirement_first_total_loan_cents
    )


def test_retirement_first_can_win_long_horizon_tradeoff() -> None:
    engine = CollegeVsRetirementEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    analysis = engine.analyze(_base_input(), seed=7)

    assert analysis.deterministic.end_of_horizon_advantage_cents > 0
    assert analysis.monte_carlo.probability_retirement_first_wins > 0.50


def test_sell_to_cash_reduces_retirement_first_advantage() -> None:
    engine = CollegeVsRetirementEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    hold = engine.analyze(_base_input(), seed=7)
    sell = engine.analyze(
        CollegeVsRetirementScenarioInput(
            current_retirement_savings_cents=dollars_to_cents(400_000),
            current_college_savings_cents=dollars_to_cents(20_000),
            annual_savings_budget_cents=dollars_to_cents(18_000),
            annual_college_cost_cents=dollars_to_cents(35_000),
            years_until_college=8,
            years_in_college=4,
            retirement_years=18,
            expected_annual_return_rate=0.06,
            risk_profile=RiskProfile.MODERATE,
            loss_behavior=LossBehavior.SELL_TO_CASH,
        ),
        seed=7,
    )

    assert (
        sell.monte_carlo.median_retirement_first_terminal_retirement_cents
        < hold.monte_carlo.median_retirement_first_terminal_retirement_cents
    )


def test_college_vs_retirement_seeded_numeric_regression() -> None:
    engine = CollegeVsRetirementEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    analysis = engine.analyze(_base_input(), seed=7)
    monte_carlo = analysis.monte_carlo

    assert analysis.deterministic.break_even_year == 1
    assert analysis.deterministic.end_of_horizon_advantage_cents == pytest.approx(7_179_121, abs=150_000)
    assert analysis.deterministic.retirement_first_total_loan_cents == pytest.approx(18_909_104, abs=150_000)
    assert monte_carlo.probability_retirement_first_wins == pytest.approx(0.7576, abs=0.01)
    assert monte_carlo.conditional_median_break_even_year == 1
    assert monte_carlo.median_terminal_advantage_cents == pytest.approx(5_581_078, abs=250_000)
    assert monte_carlo.p10_terminal_advantage_cents == pytest.approx(-3_652_660, abs=350_000)
    assert monte_carlo.p90_terminal_advantage_cents == pytest.approx(21_541_197, abs=400_000)


def test_college_vs_retirement_api_endpoint_is_available() -> None:
    client = TestClient(create_app(_test_settings()))

    response = client.post(
        "/v1/college-vs-retirement/analyze",
        json={
            "input": {
                "current_retirement_savings_cents": 40000000,
                "current_college_savings_cents": 2000000,
                "annual_savings_budget_cents": 1800000,
                "annual_college_cost_cents": 3500000,
                "years_until_college": 8,
                "years_in_college": 4,
                "retirement_years": 18,
                "expected_annual_return_rate": 0.06,
                "risk_profile": "moderate",
                "loss_behavior": "hold",
            },
            "simulation_seed": 7,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["monte_carlo"]["probability_retirement_first_wins"] >= 0.0
