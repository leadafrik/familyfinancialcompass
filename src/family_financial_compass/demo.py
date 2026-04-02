from __future__ import annotations

from pprint import pprint

from .config import DEFAULT_SYSTEM_ASSUMPTIONS
from .models import FilingStatus, HousingStatus, IncomeStability, LossBehavior, RiskProfile, UserScenarioInput
from .money import cents_to_dollars, dollars_to_cents
from .rent_vs_buy import RentVsBuyEngine


def main() -> None:
    scenario = UserScenarioInput(
        target_home_price_cents=dollars_to_cents(550_000),
        down_payment_cents=dollars_to_cents(110_000),
        loan_term_years=30,
        expected_years_in_home=7.0,
        current_monthly_rent_cents=dollars_to_cents(2_850),
        annual_household_income_cents=dollars_to_cents(210_000),
        current_savings_cents=dollars_to_cents(180_000),
        monthly_savings_cents=dollars_to_cents(2_000),
        expected_home_appreciation_rate=0.035,
        expected_investment_return_rate=0.07,
        risk_profile=RiskProfile.MODERATE,
        loss_behavior=LossBehavior.HOLD,
        income_stability=IncomeStability.STABLE,
        employment_tied_to_local_economy=True,
        current_housing_status=HousingStatus.RENTING,
        market_region="national",
        marginal_tax_rate=0.24,
        itemizes_deductions=False,
        filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
    )
    engine = RentVsBuyEngine(DEFAULT_SYSTEM_ASSUMPTIONS)
    analysis = engine.analyze(scenario)

    print("Family Financial Compass demo")
    print(f"Deterministic break-even month: {analysis.deterministic.break_even_month}")
    print(
        "Probability buying wins by the horizon:",
        f"{analysis.monte_carlo.probability_buy_beats_rent:.1%}",
    )
    print(
        "Monte Carlo break-even 80% interval:",
        analysis.monte_carlo.break_even_ci_80,
    )
    print(
        "Median terminal advantage:",
        cents_to_dollars(analysis.monte_carlo.median_terminal_advantage_cents),
    )
    print(
        "Utility-adjusted p50 advantage:",
        cents_to_dollars(analysis.monte_carlo.utility_adjusted_p50_advantage_cents),
    )
    print(
        "Probability utility-positive:",
        f"{analysis.monte_carlo.probability_utility_positive:.1%}",
    )
    print(
        "Tax deduction benefit (total):",
        cents_to_dollars(
            analysis.deterministic.first_year_cost_breakdown.total_mortgage_interest_deduction_cents
        ),
    )
    print("Warnings:")
    pprint(analysis.warnings)


if __name__ == "__main__":
    main()
