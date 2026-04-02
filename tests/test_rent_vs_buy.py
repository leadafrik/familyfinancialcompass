from __future__ import annotations

from dataclasses import replace

import pytest

from family_financial_compass.config import DEFAULT_SYSTEM_ASSUMPTIONS
from family_financial_compass.db import InMemoryScenarioRepository
from family_financial_compass.models import (
    FilingStatus,
    HousingStatus,
    IncomeStability,
    LossBehavior,
    RiskProfile,
    UserScenarioInput,
)
from family_financial_compass.money import dollars_to_cents
from family_financial_compass.rent_vs_buy import RentVsBuyEngine
from family_financial_compass.scenario import create_saved_scenario
from family_financial_compass.tax import after_tax_investment_return

BASE_INPUTS = UserScenarioInput(
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


def scenario(**overrides: object) -> UserScenarioInput:
    return replace(BASE_INPUTS, **overrides)


def test_amortization_closes_to_zero() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    payment, interest, principal, balances = engine._build_amortization_arrays(
        loan_amount_cents=BASE_INPUTS.target_home_price_cents - BASE_INPUTS.down_payment_cents,
        annual_rate=DEFAULT_SYSTEM_ASSUMPTIONS.mortgage_rate,
        term_months=BASE_INPUTS.loan_term_years * 12,
    )

    assert payment.shape[0] == BASE_INPUTS.loan_term_years * 12
    assert interest.shape == principal.shape
    assert balances[-1] == 0
    assert principal.sum() == BASE_INPUTS.target_home_price_cents - BASE_INPUTS.down_payment_cents


def test_analysis_returns_break_even_distribution_and_cost_breakdown() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    analysis = engine.analyze(BASE_INPUTS, seed=11)

    assert analysis.deterministic.cost_breakdown.liquidity_premium_cents > 0
    assert analysis.deterministic.cost_breakdown.closing_costs_cents > 0
    assert analysis.monte_carlo.scenario_count == 10_000
    assert 0.0 <= analysis.monte_carlo.probability_buy_beats_rent <= 1.0
    assert analysis.monte_carlo.break_even_ci_80[0] is None or analysis.monte_carlo.break_even_ci_80[0] <= analysis.monte_carlo.break_even_ci_80[1]
    assert analysis.monte_carlo.utility_adjusted_p50_advantage_cents <= analysis.monte_carlo.p90_terminal_advantage_cents
    assert analysis.monte_carlo.probability_utility_positive == pytest.approx(analysis.monte_carlo.probability_buy_beats_rent)
    assert len(analysis.audit_trail) >= 8
    assert analysis.calibration_used is not None
    assert analysis.calibration_used.annual_appreciation_mean == pytest.approx(0.035)


def test_saved_scenario_snapshots_are_immutable() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    analysis = engine.analyze(BASE_INPUTS, seed=5)
    scenario_record, output_record = create_saved_scenario(
        user_id="00000000-0000-0000-0000-000000000001",
        user_inputs=BASE_INPUTS,
        system_assumptions=DEFAULT_SYSTEM_ASSUMPTIONS,
        analysis=analysis,
    )

    changed_assumptions = replace(DEFAULT_SYSTEM_ASSUMPTIONS, mortgage_rate=0.075)

    assert scenario_record.assumptions_snapshot["mortgage_rate"] == DEFAULT_SYSTEM_ASSUMPTIONS.mortgage_rate
    assert scenario_record.assumptions_snapshot["mortgage_rate"] != changed_assumptions.mortgage_rate
    assert output_record.output_blob["monte_carlo"]["scenario_count"] == 10_000


def test_pmi_triggers_and_clears_correctly() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    inputs = scenario(
        down_payment_cents=dollars_to_cents(55_000),
        current_savings_cents=dollars_to_cents(80_000),
    )
    analysis = engine.analyze(inputs, seed=13)
    yearly_rows = analysis.deterministic.yearly_comparison
    paths = engine._monthly_paths(inputs, annual_investment_return=engine._effective_investment_return(inputs))

    assert yearly_rows[0].pmi_cents > 0

    clear_index = None
    for index, (home_value_cents, remaining_principal_cents, pmi_cents) in enumerate(
        zip(paths["home_value"], paths["balances"], paths["pmi"], strict=True)
    ):
        raw_equity = int(home_value_cents) - int(remaining_principal_cents)
        if raw_equity >= round(int(home_value_cents) * 0.20):
            clear_index = index
            assert int(pmi_cents) == 0
            break

    assert clear_index is not None
    assert all(int(pmi_cents) == 0 for pmi_cents in paths["pmi"][clear_index:])


def test_fifteen_year_loan_builds_equity_faster() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    analysis_30 = engine.analyze(scenario(loan_term_years=30), seed=17)
    analysis_15 = engine.analyze(scenario(loan_term_years=15), seed=17)
    cost_30 = analysis_30.deterministic.cost_breakdown
    cost_15 = analysis_15.deterministic.cost_breakdown
    year_5_30 = analysis_30.deterministic.yearly_comparison[4]
    year_5_15 = analysis_15.deterministic.yearly_comparison[4]

    assert cost_30.total_interest_paid_cents > cost_15.total_interest_paid_cents
    assert year_5_15.remaining_principal_cents < year_5_30.remaining_principal_cents
    assert cost_15.principal_and_interest_cents / 12 > cost_30.principal_and_interest_cents / 12


def test_short_horizon_no_break_even_and_loss_aversion_bites() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    inputs = scenario(
        target_home_price_cents=dollars_to_cents(1_200_000),
        down_payment_cents=dollars_to_cents(240_000),
        expected_years_in_home=2.0,
        current_monthly_rent_cents=dollars_to_cents(2_500),
        current_savings_cents=dollars_to_cents(300_000),
    )
    analysis = engine.analyze(inputs, seed=19)

    assert analysis.deterministic.break_even_month is None
    assert analysis.monte_carlo.utility_adjusted_p50_advantage_cents < analysis.monte_carlo.p50_terminal_advantage_cents


def test_sell_to_cash_reduces_effective_investment_return() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    hold_inputs = scenario(loss_behavior=LossBehavior.HOLD)
    sell_inputs = scenario(loss_behavior=LossBehavior.SELL_TO_CASH)
    hold_paths = engine._monthly_paths(hold_inputs, annual_investment_return=engine._effective_investment_return(hold_inputs))
    sell_paths = engine._monthly_paths(sell_inputs, annual_investment_return=engine._effective_investment_return(sell_inputs))

    gross = 0.08
    net = after_tax_investment_return(gross)

    assert int(sell_paths["buy_portfolio"][-1]) < int(hold_paths["buy_portfolio"][-1])
    assert net < gross
    assert net > 0.0
    assert abs(gross - net) < 0.01


def test_variable_income_increases_liquidity_premium() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    stable_inputs = scenario(income_stability=IncomeStability.STABLE)
    variable_inputs = scenario(income_stability=IncomeStability.VARIABLE)
    stable_analysis = engine.analyze(stable_inputs, seed=23)
    variable_analysis = engine.analyze(variable_inputs, seed=23)

    stable_total_buy_cost = sum(row.total_buy_cost_cents for row in stable_analysis.deterministic.yearly_comparison)
    variable_total_buy_cost = sum(row.total_buy_cost_cents for row in variable_analysis.deterministic.yearly_comparison)

    assert variable_total_buy_cost > stable_total_buy_cost


def test_validation_rejects_savings_below_down_plus_closing() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    inputs = scenario(current_savings_cents=BASE_INPUTS.down_payment_cents)

    with pytest.raises(ValueError, match="closing costs"):
        engine.analyze(inputs, seed=29)


def test_buyer_closing_costs_reduce_initial_buy_portfolio() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    paths = engine._monthly_paths(BASE_INPUTS, annual_investment_return=engine._effective_investment_return(BASE_INPUTS))
    analysis = engine.analyze(BASE_INPUTS, seed=31)
    closing_costs_cents = round(BASE_INPUTS.target_home_price_cents * DEFAULT_SYSTEM_ASSUMPTIONS.buyer_closing_cost_rate)
    expected_buy_initial_portfolio = (
        BASE_INPUTS.current_savings_cents - BASE_INPUTS.down_payment_cents - closing_costs_cents
    )

    assert int(paths["closing_costs_cents"]) == closing_costs_cents
    assert int(paths["buy_initial_portfolio_cents"]) == expected_buy_initial_portfolio
    assert analysis.deterministic.cost_breakdown.buyer_closing_costs_cents == closing_costs_cents


def test_tax_deduction_reduces_buy_path_net_cost() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    analysis = engine.analyze(
        scenario(marginal_tax_rate=0.32, itemizes_deductions=True),
        seed=37,
    )
    breakdown = analysis.deterministic.cost_breakdown

    assert breakdown.total_mortgage_interest_deduction_cents > 0
    assert breakdown.total_mortgage_interest_deduction_cents <= round(breakdown.total_interest_paid_cents * 0.32)


def test_regional_calibration_routes_correctly() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    coastal = engine.analyze(scenario(market_region="coastal_high_cost"), seed=41)
    national = engine.analyze(scenario(market_region="national"), seed=41)

    assert coastal.calibration_used is not None
    assert national.calibration_used is not None
    assert coastal.calibration_used.annual_appreciation_mean == pytest.approx(0.055)
    assert national.calibration_used.annual_appreciation_mean != pytest.approx(0.055)
    assert coastal.monte_carlo.p90_terminal_advantage_cents > national.monte_carlo.p90_terminal_advantage_cents


def test_in_memory_scenario_repository_round_trips() -> None:
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    analysis = engine.analyze(BASE_INPUTS, seed=43)
    scenario_record, output_record = create_saved_scenario(
        user_id="00000000-0000-0000-0000-000000000001",
        user_inputs=BASE_INPUTS,
        system_assumptions=DEFAULT_SYSTEM_ASSUMPTIONS,
        analysis=analysis,
    )
    repository = InMemoryScenarioRepository()

    scenario_id = repository.save_scenario(scenario_record)
    output_id = repository.save_output(output_record)

    assert scenario_id == scenario_record.scenario_id
    assert output_id == output_record.scenario_id
    assert repository.get_scenario(scenario_record.scenario_id) == scenario_record
    assert repository.get_output(output_record.scenario_id) == output_record
    assert repository.get_scenario("nonexistent-id") is None
