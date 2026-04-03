from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from family_financial_compass.app import create_app
from family_financial_compass.config import DEFAULT_ASSUMPTIONS_PATH, DEFAULT_SYSTEM_ASSUMPTIONS
from family_financial_compass.job_offer import JobOfferEngine
from family_financial_compass.models import JobOffer, JobOfferScenarioInput
from family_financial_compass.money import dollars_to_cents
from family_financial_compass.settings import AppSettings


def _base_input() -> JobOfferScenarioInput:
    return JobOfferScenarioInput(
        offer_a=JobOffer(
            label="Current role",
            base_salary_cents=dollars_to_cents(160_000),
            target_bonus_cents=dollars_to_cents(20_000),
            annual_equity_vesting_cents=0,
            annual_commute_cost_cents=dollars_to_cents(3_000),
            annual_comp_growth_rate=0.03,
            bonus_payout_volatility=0.10,
            equity_volatility=0.0,
        ),
        offer_b=JobOffer(
            label="New role",
            base_salary_cents=dollars_to_cents(190_000),
            target_bonus_cents=dollars_to_cents(30_000),
            annual_equity_vesting_cents=dollars_to_cents(25_000),
            sign_on_bonus_cents=dollars_to_cents(20_000),
            relocation_cost_cents=dollars_to_cents(15_000),
            annual_cost_of_living_delta_cents=dollars_to_cents(18_000),
            annual_commute_cost_cents=dollars_to_cents(5_000),
            annual_comp_growth_rate=0.035,
            annual_equity_growth_rate=0.0,
            bonus_payout_volatility=0.25,
            equity_volatility=0.60,
        ),
        comparison_years=4,
        marginal_tax_rate=0.30,
        local_market_concentration=True,
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
        default_user_id="job-offer-endpoint-test",
        scenario_list_default_limit=25,
        scenario_list_max_limit=100,
        allowed_origins=(),
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        groq_base_url="https://api.groq.com/openai/v1/chat/completions",
    )


def test_job_offer_new_role_outperforms_baseline() -> None:
    engine = JobOfferEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    analysis = engine.analyze(_base_input(), seed=7)

    assert analysis.deterministic.end_of_horizon_advantage_cents > 0
    assert analysis.monte_carlo.probability_offer_b_wins > 0.60
    assert analysis.deterministic.break_even_month is not None


def test_job_offer_relocation_cost_delays_break_even() -> None:
    engine = JobOfferEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    base_input = _base_input()
    base_analysis = engine.analyze(base_input, seed=7)
    stressed_analysis = engine.analyze(
        JobOfferScenarioInput(
            offer_a=base_input.offer_a,
            offer_b=replace(base_input.offer_b, relocation_cost_cents=dollars_to_cents(60_000)),
            comparison_years=4,
            marginal_tax_rate=0.30,
            local_market_concentration=True,
        ),
        seed=7,
    )

    assert stressed_analysis.deterministic.break_even_month is not None
    assert base_analysis.deterministic.break_even_month is not None
    assert stressed_analysis.deterministic.break_even_month > base_analysis.deterministic.break_even_month


def test_job_offer_equity_volatility_widens_terminal_distribution() -> None:
    engine = JobOfferEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    base_input = _base_input()
    low_vol_analysis = engine.analyze(
        JobOfferScenarioInput(
            offer_a=base_input.offer_a,
            offer_b=replace(base_input.offer_b, equity_volatility=0.20),
            comparison_years=4,
            marginal_tax_rate=0.30,
            local_market_concentration=False,
        ),
        seed=7,
    )
    high_vol_analysis = engine.analyze(base_input, seed=7)

    low_spread = (
        low_vol_analysis.monte_carlo.p90_terminal_advantage_cents
        - low_vol_analysis.monte_carlo.p10_terminal_advantage_cents
    )
    high_spread = (
        high_vol_analysis.monte_carlo.p90_terminal_advantage_cents
        - high_vol_analysis.monte_carlo.p10_terminal_advantage_cents
    )

    assert high_spread > low_spread


def test_job_offer_cheaper_city_improves_advantage() -> None:
    engine = JobOfferEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    base_input = _base_input()
    baseline = engine.analyze(base_input, seed=7)
    cheaper_city = engine.analyze(
        JobOfferScenarioInput(
            offer_a=base_input.offer_a,
            offer_b=replace(
                base_input.offer_b,
                annual_cost_of_living_delta_cents=-dollars_to_cents(12_000),
            ),
            comparison_years=base_input.comparison_years,
            marginal_tax_rate=base_input.marginal_tax_rate,
            local_market_concentration=base_input.local_market_concentration,
        ),
        seed=7,
    )

    assert cheaper_city.deterministic.end_of_horizon_advantage_cents > baseline.deterministic.end_of_horizon_advantage_cents


def test_job_offer_seeded_numeric_regression() -> None:
    engine = JobOfferEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    analysis = engine.analyze(_base_input(), seed=7)
    monte_carlo = analysis.monte_carlo

    assert analysis.deterministic.break_even_month == 1
    assert analysis.deterministic.end_of_horizon_advantage_cents == pytest.approx(11_096_421, abs=100_000)
    assert monte_carlo.probability_offer_b_wins == pytest.approx(1.0, abs=0.0)
    assert monte_carlo.median_terminal_advantage_cents == pytest.approx(11_151_330, abs=150_000)
    assert monte_carlo.p10_terminal_advantage_cents == pytest.approx(7_843_106, abs=250_000)
    assert monte_carlo.p90_terminal_advantage_cents == pytest.approx(14_715_329, abs=250_000)


def test_job_offer_api_endpoint_is_available() -> None:
    client = TestClient(create_app(_test_settings()))

    response = client.post(
        "/v1/job-offer/analyze",
        json={
            "input": {
                "offer_a": {
                    "label": "Current role",
                    "base_salary_cents": 16000000,
                    "target_bonus_cents": 2000000,
                    "annual_equity_vesting_cents": 0,
                    "sign_on_bonus_cents": 0,
                    "relocation_cost_cents": 0,
                    "annual_cost_of_living_delta_cents": 0,
                    "annual_commute_cost_cents": 300000,
                    "annual_comp_growth_rate": 0.03,
                    "annual_equity_growth_rate": 0.0,
                    "bonus_payout_volatility": 0.10,
                    "equity_volatility": 0.0,
                },
                "offer_b": {
                    "label": "New role",
                    "base_salary_cents": 19000000,
                    "target_bonus_cents": 3000000,
                    "annual_equity_vesting_cents": 2500000,
                    "sign_on_bonus_cents": 2000000,
                    "relocation_cost_cents": 1500000,
                    "annual_cost_of_living_delta_cents": 1800000,
                    "annual_commute_cost_cents": 500000,
                    "annual_comp_growth_rate": 0.035,
                    "annual_equity_growth_rate": 0.0,
                    "bonus_payout_volatility": 0.25,
                    "equity_volatility": 0.60,
                },
                "comparison_years": 4,
                "marginal_tax_rate": 0.30,
                "local_market_concentration": True,
            },
            "simulation_seed": 7,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["monte_carlo"]["probability_offer_b_wins"] >= 0.0
