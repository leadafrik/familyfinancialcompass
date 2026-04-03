from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from family_financial_compass.app import create_app
from family_financial_compass.config import DEFAULT_ASSUMPTIONS_PATH, DEFAULT_SYSTEM_ASSUMPTIONS
from family_financial_compass.models import LossBehavior, RetirementScenarioInput, RiskProfile
from family_financial_compass.money import dollars_to_cents
from family_financial_compass.retirement_survival import RetirementSurvivalEngine
from family_financial_compass.settings import AppSettings


def _base_input() -> RetirementScenarioInput:
    return RetirementScenarioInput(
        current_portfolio_cents=dollars_to_cents(1_500_000),
        annual_spending_cents=dollars_to_cents(80_000),
        annual_guaranteed_income_cents=dollars_to_cents(20_000),
        retirement_years=30,
        expected_annual_return_rate=0.06,
        risk_profile=RiskProfile.MODERATE,
        loss_behavior=LossBehavior.HOLD,
    )


def test_retirement_survival_probability_declines_with_higher_withdrawal() -> None:
    engine = RetirementSurvivalEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    base = engine.analyze(_base_input(), seed=7)
    stressed = engine.analyze(
        RetirementScenarioInput(
            current_portfolio_cents=dollars_to_cents(1_500_000),
            annual_spending_cents=dollars_to_cents(110_000),
            annual_guaranteed_income_cents=dollars_to_cents(20_000),
            retirement_years=30,
            expected_annual_return_rate=0.06,
            risk_profile=RiskProfile.MODERATE,
            loss_behavior=LossBehavior.HOLD,
        ),
        seed=7,
    )

    assert (
        stressed.monte_carlo.probability_portfolio_survives
        < base.monte_carlo.probability_portfolio_survives
    )


def test_sell_to_cash_reduces_survival_probability() -> None:
    engine = RetirementSurvivalEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    hold = engine.analyze(_base_input(), seed=7)
    sell = engine.analyze(
        RetirementScenarioInput(
            current_portfolio_cents=dollars_to_cents(1_500_000),
            annual_spending_cents=dollars_to_cents(80_000),
            annual_guaranteed_income_cents=dollars_to_cents(20_000),
            retirement_years=30,
            expected_annual_return_rate=0.06,
            risk_profile=RiskProfile.MODERATE,
            loss_behavior=LossBehavior.SELL_TO_CASH,
        ),
        seed=7,
    )

    assert (
        sell.monte_carlo.probability_portfolio_survives
        < hold.monte_carlo.probability_portfolio_survives
    )


def test_retirement_analysis_produces_yearly_projection_rows() -> None:
    engine = RetirementSurvivalEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    analysis = engine.analyze(_base_input(), seed=7)

    assert len(analysis.monte_carlo.yearly_rows) == 30
    assert analysis.monte_carlo.yearly_rows[0].year == 1
    assert analysis.monte_carlo.yearly_rows[-1].year == 30


def test_retirement_api_endpoint_is_available() -> None:
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
                default_user_id="retirement-endpoint-test",
                scenario_list_default_limit=25,
                scenario_list_max_limit=100,
                allowed_origins=(),
                groq_api_key=None,
                groq_model="openai/gpt-oss-20b",
                groq_base_url="https://api.groq.com/openai/v1/chat/completions",
            )
        )
    )

    response = client.post(
        "/v1/retirement-survival/analyze",
        json={
            "input": {
                "current_portfolio_cents": 150000000,
                "annual_spending_cents": 8000000,
                "annual_guaranteed_income_cents": 2000000,
                "retirement_years": 30,
                "expected_annual_return_rate": 0.06,
                "risk_profile": "moderate",
                "loss_behavior": "hold",
            },
            "simulation_seed": 7,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["monte_carlo"]["probability_portfolio_survives"] >= 0.0
