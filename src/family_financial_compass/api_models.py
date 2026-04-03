from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic import StrictInt

from .models import (
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


class RentVsBuyInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_home_price_cents: StrictInt = Field(gt=0)
    down_payment_cents: StrictInt = Field(ge=0)
    loan_term_years: Literal[15, 20, 30]
    expected_years_in_home: float = Field(gt=0)
    current_monthly_rent_cents: StrictInt = Field(gt=0)
    annual_household_income_cents: StrictInt = Field(gt=0)
    current_savings_cents: StrictInt = Field(ge=0)
    monthly_savings_cents: StrictInt = Field(ge=0)
    expected_home_appreciation_rate: float = Field(gt=-1.0, le=1.0)
    expected_investment_return_rate: float = Field(gt=-1.0, le=1.0)
    risk_profile: RiskProfile
    loss_behavior: LossBehavior
    income_stability: IncomeStability
    employment_tied_to_local_economy: bool
    current_housing_status: HousingStatus = HousingStatus.RENTING
    market_region: str = "national"
    marginal_tax_rate: float = Field(default=0.24, ge=0.0, le=0.60)
    itemizes_deductions: bool = False
    filing_status: FilingStatus = FilingStatus.MARRIED_FILING_JOINTLY

    def to_domain(self) -> UserScenarioInput:
        return UserScenarioInput(**self.model_dump())


class AssumptionOverrideModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mortgage_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    property_tax_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    annual_home_insurance_cents: StrictInt | None = Field(default=None, ge=0)
    annual_rent_growth_rate: float | None = Field(default=None, gt=-1.0, le=1.0)
    maintenance_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    selling_cost_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    annual_pmi_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    buyer_closing_cost_rate: float | None = Field(default=None, ge=0.0, le=1.0)

    def to_domain(self) -> AssumptionOverrides:
        return AssumptionOverrides(**self.model_dump())


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: RentVsBuyInputModel
    simulation_seed: StrictInt = Field(default=7, ge=0)
    assumption_overrides: AssumptionOverrideModel | None = None
    assumptions_snapshot: dict[str, Any] | None = None
    audit_trail_snapshot: list[dict[str, Any]] | None = None


class CreateScenarioRequest(AnalyzeRequest):
    model_config = ConfigDict(extra="forbid")

    user_id: str | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class RetirementInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_portfolio_cents: StrictInt = Field(gt=0)
    annual_spending_cents: StrictInt = Field(ge=0)
    annual_guaranteed_income_cents: StrictInt = Field(default=0, ge=0)
    retirement_years: StrictInt = Field(default=30, gt=0, le=60)
    expected_annual_return_rate: float = Field(default=0.06, gt=-1.0, le=1.0)
    risk_profile: RiskProfile = RiskProfile.MODERATE
    loss_behavior: LossBehavior = LossBehavior.HOLD

    def to_domain(self) -> RetirementScenarioInput:
        return RetirementScenarioInput(**self.model_dump())


class RetirementAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: RetirementInputModel
    simulation_seed: StrictInt = Field(default=7, ge=0)
    assumptions_snapshot: dict[str, Any] | None = None
    audit_trail_snapshot: list[dict[str, Any]] | None = None


class RetirementReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: RetirementInputModel
    simulation_seed: StrictInt = Field(default=7, ge=0)
    assumptions_snapshot: dict[str, Any] | None = None
    audit_trail_snapshot: list[dict[str, Any]] | None = None


class JobOfferModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=80)
    base_salary_cents: StrictInt = Field(ge=0)
    target_bonus_cents: StrictInt = Field(default=0, ge=0)
    annual_equity_vesting_cents: StrictInt = Field(default=0, ge=0)
    sign_on_bonus_cents: StrictInt = Field(default=0, ge=0)
    relocation_cost_cents: StrictInt = Field(default=0, ge=0)
    annual_cost_of_living_delta_cents: StrictInt = Field(default=0)
    annual_commute_cost_cents: StrictInt = Field(default=0, ge=0)
    annual_comp_growth_rate: float = Field(default=0.03, gt=-1.0, le=1.0)
    annual_equity_growth_rate: float = Field(default=0.0, gt=-1.0, le=1.0)
    bonus_payout_volatility: float = Field(default=0.20, ge=0.0, le=3.0)
    equity_volatility: float = Field(default=0.60, ge=0.0, le=3.0)

    def to_domain(self) -> JobOffer:
        return JobOffer(**self.model_dump())


class JobOfferAnalyzeInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_a: JobOfferModel
    offer_b: JobOfferModel
    comparison_years: StrictInt = Field(default=4, gt=0)
    marginal_tax_rate: float = Field(default=0.24, ge=0.0, le=0.60)
    local_market_concentration: bool = False

    def to_domain(self) -> JobOfferScenarioInput:
        payload = self.model_dump()
        return JobOfferScenarioInput(
            offer_a=self.offer_a.to_domain(),
            offer_b=self.offer_b.to_domain(),
            comparison_years=payload["comparison_years"],
            marginal_tax_rate=payload["marginal_tax_rate"],
            local_market_concentration=payload["local_market_concentration"],
        )


class JobOfferAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: JobOfferAnalyzeInputModel
    simulation_seed: StrictInt = Field(default=7, ge=0)
    assumptions_snapshot: dict[str, Any] | None = None
    audit_trail_snapshot: list[dict[str, Any]] | None = None


class JobOfferReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: JobOfferAnalyzeInputModel
    simulation_seed: StrictInt = Field(default=7, ge=0)
    assumptions_snapshot: dict[str, Any] | None = None
    audit_trail_snapshot: list[dict[str, Any]] | None = None


class CollegeVsRetirementInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_retirement_savings_cents: StrictInt = Field(ge=0)
    current_college_savings_cents: StrictInt = Field(default=0, ge=0)
    annual_savings_budget_cents: StrictInt = Field(default=0, ge=0)
    annual_college_cost_cents: StrictInt = Field(gt=0)
    years_until_college: StrictInt = Field(ge=0)
    years_in_college: StrictInt = Field(default=4, gt=0)
    retirement_years: StrictInt = Field(default=18, gt=0)
    expected_annual_return_rate: float = Field(default=0.06, gt=-1.0, le=1.0)
    risk_profile: RiskProfile = RiskProfile.MODERATE
    loss_behavior: LossBehavior = LossBehavior.HOLD

    def to_domain(self) -> CollegeVsRetirementScenarioInput:
        return CollegeVsRetirementScenarioInput(**self.model_dump())


class CollegeVsRetirementAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: CollegeVsRetirementInputModel
    simulation_seed: StrictInt = Field(default=7, ge=0)
    assumptions_snapshot: dict[str, Any] | None = None
    audit_trail_snapshot: list[dict[str, Any]] | None = None


class CollegeVsRetirementReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: CollegeVsRetirementInputModel
    simulation_seed: StrictInt = Field(default=7, ge=0)
    assumptions_snapshot: dict[str, Any] | None = None
    audit_trail_snapshot: list[dict[str, Any]] | None = None


class AnalysisEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_version: str
    disclaimer: str
    analysis: dict[str, Any]


class ReportEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_version: str
    disclaimer: str
    report: dict[str, Any]


class ScenarioEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    user_id: str
    created_at: str
    computed_at: str
    model_version: str
    disclaimer: str
    inputs_snapshot: dict[str, Any]
    assumptions_snapshot: dict[str, Any]
    analysis: dict[str, Any]


class HealthEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    model_version: str
    scenario_store: str
    assumptions_path: str
    assumptions_source: str | None = None
    assumptions_cache_date: str | None = None


class CurrentAssumptionsEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_version: str
    disclaimer: str
    source: str
    cache_date: str
    assumptions: dict[str, Any]
    audit_trail: list[dict[str, Any]]


class ScenarioListEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ScenarioEnvelope]
    next_cursor: str | None = None
