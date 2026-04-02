from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

import numpy as np


class RiskProfile(StrEnum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class LossBehavior(StrEnum):
    SELL_TO_CASH = "sell_to_cash"
    HOLD = "hold"
    BUY_MORE = "buy_more"


class IncomeStability(StrEnum):
    STABLE = "stable"
    VARIABLE = "variable"


class HousingStatus(StrEnum):
    RENTING = "renting"
    OWNING = "owning"


class FilingStatus(StrEnum):
    SINGLE = "single"
    MARRIED_FILING_JOINTLY = "married_filing_jointly"


@dataclass(frozen=True)
class RiskVolatilityBand:
    low: float
    stated: float
    high: float


@dataclass(frozen=True)
class MonteCarloCalibration:
    scenario_count: int
    appreciation_stddev: float
    rent_growth_stddev: float
    mortgage_rate_stddev: float
    investment_volatility_by_risk: dict[RiskProfile, RiskVolatilityBand]
    correlation_matrix: tuple[tuple[float, ...], ...]
    annual_appreciation_mean: float = 0.035
    annual_rent_growth_mean: float = 0.032

    def __post_init__(self) -> None:
        if self.scenario_count <= 0:
            raise ValueError("Monte Carlo scenario count must be positive.")
        if self.appreciation_stddev < 0 or self.rent_growth_stddev < 0 or self.mortgage_rate_stddev < 0:
            raise ValueError("Monte Carlo standard deviations must be non-negative.")
        if set(self.investment_volatility_by_risk) != set(RiskProfile):
            raise ValueError("Investment volatility bands must be defined for every risk profile.")

        correlation = np.array(self.correlation_matrix, dtype=np.float64)
        if correlation.shape != (4, 4):
            raise ValueError("Correlation matrix must be 4x4.")
        if not np.allclose(correlation, correlation.T, atol=1e-9):
            raise ValueError("Correlation matrix must be symmetric.")
        if not np.allclose(np.diag(correlation), 1.0, atol=1e-9):
            raise ValueError("Correlation matrix diagonal entries must equal 1.")
        np.linalg.cholesky(correlation)

    @property
    def annual_appreciation_std(self) -> float:
        return self.appreciation_stddev

    @property
    def annual_rent_growth_std(self) -> float:
        return self.rent_growth_stddev

    @property
    def annual_mortgage_rate_std(self) -> float:
        return self.mortgage_rate_stddev

    @property
    def num_simulations(self) -> int:
        return self.scenario_count

    @property
    def investment_volatility_bands(self) -> dict[RiskProfile, RiskVolatilityBand]:
        return self.investment_volatility_by_risk


@dataclass(frozen=True)
class BehavioralAdjustments:
    loss_aversion_lambda: float
    panic_sale_expected_return_penalty: float
    stable_income_liquidity_premium: float
    variable_income_liquidity_premium: float

    def __post_init__(self) -> None:
        if self.loss_aversion_lambda <= 0:
            raise ValueError("Loss aversion lambda must be positive.")
        if self.panic_sale_expected_return_penalty < 0:
            raise ValueError("Panic-sale penalty must be non-negative.")
        if self.stable_income_liquidity_premium < 0 or self.variable_income_liquidity_premium < 0:
            raise ValueError("Liquidity premiums must be non-negative.")

    @property
    def liquidity_premium_rate_stable(self) -> float:
        return self.stable_income_liquidity_premium

    @property
    def liquidity_premium_rate_variable(self) -> float:
        return self.variable_income_liquidity_premium


@dataclass(frozen=True)
class SystemAssumptions:
    model_version: str
    mortgage_rate: float
    property_tax_rate: float
    annual_home_insurance_cents: int
    annual_rent_growth_rate: float
    maintenance_rate: float
    selling_cost_rate: float
    annual_pmi_rate: float
    monte_carlo: MonteCarloCalibration
    behavioral: BehavioralAdjustments
    buyer_closing_cost_rate: float = 0.03

    def __post_init__(self) -> None:
        bounded_rates = {
            "mortgage_rate": self.mortgage_rate,
            "property_tax_rate": self.property_tax_rate,
            "annual_rent_growth_rate": self.annual_rent_growth_rate,
            "maintenance_rate": self.maintenance_rate,
            "selling_cost_rate": self.selling_cost_rate,
            "annual_pmi_rate": self.annual_pmi_rate,
            "buyer_closing_cost_rate": self.buyer_closing_cost_rate,
        }
        for name, value in bounded_rates.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1.")
        if self.annual_home_insurance_cents < 0:
            raise ValueError("Annual home insurance must be non-negative.")


@dataclass(frozen=True)
class AssumptionAuditItem:
    name: str | None = None
    value: str | float | int | None = None
    source: str = ""
    sourced_at: str | None = None
    parameter: str | None = None
    last_updated: date | None = None
    notes: str | None = None


@dataclass(frozen=True)
class UserScenarioInput:
    target_home_price_cents: int
    down_payment_cents: int
    loan_term_years: int
    expected_years_in_home: float
    current_monthly_rent_cents: int
    annual_household_income_cents: int
    current_savings_cents: int
    monthly_savings_cents: int
    expected_home_appreciation_rate: float
    expected_investment_return_rate: float
    risk_profile: RiskProfile
    loss_behavior: LossBehavior
    income_stability: IncomeStability
    employment_tied_to_local_economy: bool
    current_housing_status: HousingStatus = HousingStatus.RENTING
    market_region: str = "national"
    marginal_tax_rate: float = 0.24
    itemizes_deductions: bool = False
    filing_status: FilingStatus = FilingStatus.MARRIED_FILING_JOINTLY

    def __post_init__(self) -> None:
        if not isinstance(self.filing_status, FilingStatus):
            object.__setattr__(self, "filing_status", FilingStatus(self.filing_status))

        positive_values = {
            "target_home_price_cents": self.target_home_price_cents,
            "expected_years_in_home": self.expected_years_in_home,
            "current_monthly_rent_cents": self.current_monthly_rent_cents,
            "annual_household_income_cents": self.annual_household_income_cents,
        }
        for name, value in positive_values.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive.")

        non_negative_values = {
            "down_payment_cents": self.down_payment_cents,
            "current_savings_cents": self.current_savings_cents,
            "monthly_savings_cents": self.monthly_savings_cents,
        }
        for name, value in non_negative_values.items():
            if value < 0:
                raise ValueError(f"{name} must be non-negative.")

        bounded_rates = {
            "expected_home_appreciation_rate": self.expected_home_appreciation_rate,
            "expected_investment_return_rate": self.expected_investment_return_rate,
        }
        for name, value in bounded_rates.items():
            if value <= -1.0 or value > 1.0:
                raise ValueError(f"{name} must be greater than -1 and no more than 1.")
        if not 0.0 <= self.marginal_tax_rate <= 0.60:
            raise ValueError("marginal_tax_rate must be between 0.0 and 0.60.")
        if self.down_payment_cents > self.target_home_price_cents:
            raise ValueError("Down payment cannot exceed the target home price.")

    @property
    def home_price_cents(self) -> int:
        return self.target_home_price_cents

    @property
    def horizon_months(self) -> int:
        return max(int(round(self.expected_years_in_home * 12)), 1)

    @property
    def monthly_rent_cents(self) -> int:
        return self.current_monthly_rent_cents

    @property
    def annual_income_cents(self) -> int:
        return self.annual_household_income_cents

    @property
    def savings_cents(self) -> int:
        return self.current_savings_cents

    @property
    def marginal_federal_tax_rate(self) -> float:
        return self.marginal_tax_rate


@dataclass(frozen=True)
class AmortizationRow:
    month: int
    payment_cents: int
    interest_cents: int
    principal_cents: int
    balance_cents: int


@dataclass(frozen=True)
class CostBreakdown:
    principal_and_interest_cents: int
    property_tax_cents: int
    insurance_cents: int
    maintenance_cents: int
    pmi_cents: int
    liquidity_premium_cents: int
    closing_costs_cents: int = 0
    total_mortgage_interest_deduction_cents: int = 0
    capital_gains_tax_on_sale_cents: int = 0
    total_interest_paid_cents: int = 0
    total_cost_of_buying_cents: int = 0

    @property
    def buyer_closing_costs_cents(self) -> int:
        return self.closing_costs_cents


@dataclass(frozen=True)
class YearlyComparisonRow:
    year: int
    rent_net_worth_cents: int
    buy_net_worth_cents: int
    buy_minus_rent_cents: int
    home_equity_cents: int
    rent_portfolio_cents: int
    buy_liquid_portfolio_cents: int
    home_value_cents: int = 0
    remaining_principal_cents: int = 0
    pmi_cents: int = 0
    total_buy_cost_cents: int = 0


@dataclass(frozen=True)
class DeterministicSummary:
    break_even_month: int | None
    end_of_horizon_advantage_cents: int
    horizon_months: int
    first_year_cost_breakdown: CostBreakdown
    yearly_rows: list[YearlyComparisonRow]
    amortization_rows: list[AmortizationRow]

    @property
    def cost_breakdown(self) -> CostBreakdown:
        return self.first_year_cost_breakdown

    @property
    def yearly_comparison(self) -> list[YearlyComparisonRow]:
        return self.yearly_rows


@dataclass(frozen=True)
class MonteCarloSummary:
    scenario_count: int
    probability_buy_beats_rent: float
    probability_break_even_within_horizon: float
    median_break_even_month: int | None
    break_even_ci_80: tuple[int | None, int | None]
    median_terminal_advantage_cents: int
    p10_terminal_advantage_cents: int
    p90_terminal_advantage_cents: int
    utility_adjusted_p50_advantage_cents: int = 0
    probability_utility_positive: float = 0.0

    @property
    def p50_terminal_advantage_cents(self) -> int:
        return self.median_terminal_advantage_cents

    @property
    def probability_buy_wins(self) -> float:
        return self.probability_buy_beats_rent


@dataclass(frozen=True)
class RentVsBuyAnalysis:
    deterministic: DeterministicSummary
    monte_carlo: MonteCarloSummary
    audit_trail: list[AssumptionAuditItem]
    warnings: list[str] = field(default_factory=list)
    calibration_used: MonteCarloCalibration | None = None

    @property
    def resolved_calibration(self) -> MonteCarloCalibration | None:
        return self.calibration_used


@dataclass(frozen=True)
class ScenarioRecord:
    id: str
    user_id: str
    created_at: str
    inputs_snapshot: dict
    assumptions_snapshot: dict
    model_version: str
    idempotency_key: str | None = None

    @property
    def scenario_id(self) -> str:
        return self.id


@dataclass(frozen=True)
class ScenarioOutputRecord:
    scenario_id: str
    computed_at: str
    output_blob: dict
