from __future__ import annotations

from pathlib import Path

import pytest
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
        default_user_id="retirement-endpoint-test",
        scenario_list_default_limit=25,
        scenario_list_max_limit=100,
        allowed_origins=(),
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        groq_base_url="https://api.groq.com/openai/v1/chat/completions",
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


def test_retirement_seeded_numeric_regression() -> None:
    engine = RetirementSurvivalEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    analysis = engine.analyze(_base_input(), seed=7)
    monte_carlo = analysis.monte_carlo

    assert monte_carlo.probability_portfolio_survives == pytest.approx(0.788, abs=0.005)
    assert monte_carlo.safe_withdrawal_rate_95 == pytest.approx(0.02417, abs=0.0005)
    assert monte_carlo.median_terminal_wealth_cents == pytest.approx(197_447_256, abs=2_000_000)
    assert monte_carlo.p90_terminal_wealth_cents == pytest.approx(1_259_880_725, abs=10_000_000)
    assert monte_carlo.conditional_median_depletion_year == 22
    assert monte_carlo.yearly_rows[9].median_portfolio_cents == pytest.approx(163_188_302, abs=2_000_000)
    assert monte_carlo.yearly_rows[9].cumulative_depletion_probability == pytest.approx(0.002, abs=0.001)


def test_retirement_api_endpoint_is_available() -> None:
    client = TestClient(create_app(_test_settings()))

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


def test_health_and_liveness_do_not_depend_on_repository_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(create_app(_test_settings()))
    service = client.app.state.service

    def raise_ping() -> None:
        raise RuntimeError("repository unavailable")

    def raise_assumptions() -> dict[str, object]:
        raise RuntimeError("assumption store unavailable")

    monkeypatch.setattr(service.repository, "ping", raise_ping)
    monkeypatch.setattr(service, "current_assumptions_payload", raise_assumptions)

    health_response = client.get("/healthz")
    live_response = client.get("/livez")
    ready_response = client.get("/readyz")

    assert health_response.status_code == 200
    assert health_response.json()["status"] == "ok"
    assert health_response.json()["assumptions_source"] is None
    assert live_response.status_code == 200
    assert live_response.json()["status"] == "ok"
    assert ready_response.status_code == 503
    assert ready_response.json()["status"] == "unavailable"
