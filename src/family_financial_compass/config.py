from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType

from .models import (
    AssumptionAuditItem,
    BehavioralAdjustments,
    MonteCarloCalibration,
    RiskProfile,
    RiskVolatilityBand,
    SystemAssumptions,
)

MODEL_VERSION = "2.0.0-alpha.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ASSUMPTIONS_PATH = PROJECT_ROOT / "config" / "system_assumptions.json"


@dataclass(frozen=True)
class ReferenceDataTimestamps:
    mortgage_rate_date: date
    inflation_date: date
    property_tax_date: date
    insurance_date: date


DEFAULT_REFERENCE_DATES = ReferenceDataTimestamps(
    mortgage_rate_date=date(2026, 3, 27),
    inflation_date=date(2026, 3, 12),
    property_tax_date=date(2025, 11, 1),
    insurance_date=date(2025, 11, 1),
)

DEFAULT_CORRELATION_MATRIX: tuple[tuple[float, ...], ...] = (
    (1.00, 0.25, 0.30, -0.35),
    (0.25, 1.00, 0.20, -0.15),
    (0.30, 0.20, 1.00, -0.20),
    (-0.35, -0.15, -0.20, 1.00),
)

DEFAULT_INVESTMENT_VOLATILITY_BANDS: dict[RiskProfile, RiskVolatilityBand] = {
    RiskProfile.CONSERVATIVE: RiskVolatilityBand(low=0.08, stated=0.10, high=0.12),
    RiskProfile.MODERATE: RiskVolatilityBand(low=0.12, stated=0.16, high=0.20),
    RiskProfile.AGGRESSIVE: RiskVolatilityBand(low=0.16, stated=0.20, high=0.24),
}


def _copy_volatility_bands() -> dict[RiskProfile, RiskVolatilityBand]:
    return {
        profile: RiskVolatilityBand(low=band.low, stated=band.stated, high=band.high)
        for profile, band in DEFAULT_INVESTMENT_VOLATILITY_BANDS.items()
    }


def _pct(rate: float) -> str:
    return f"{rate * 100:.2f}%"


def _usd(cents: int) -> str:
    return f"${cents / 100:,.0f}"


DEFAULT_MONTE_CARLO = MonteCarloCalibration(
    scenario_count=10_000,
    appreciation_stddev=0.025,
    rent_growth_stddev=0.012,
    mortgage_rate_stddev=0.003,
    investment_volatility_by_risk=_copy_volatility_bands(),
    correlation_matrix=DEFAULT_CORRELATION_MATRIX,
    annual_appreciation_mean=0.035,
    annual_rent_growth_mean=0.032,
)

REGIONAL_CALIBRATIONS: Mapping[str, MonteCarloCalibration] = MappingProxyType({
    "national": DEFAULT_MONTE_CARLO,
    "coastal_high_cost": MonteCarloCalibration(
        scenario_count=10_000,
        appreciation_stddev=0.038,
        rent_growth_stddev=0.015,
        mortgage_rate_stddev=0.003,
        investment_volatility_by_risk=_copy_volatility_bands(),
        correlation_matrix=DEFAULT_CORRELATION_MATRIX,
        annual_appreciation_mean=0.055,
        annual_rent_growth_mean=0.042,
    ),
    "midwest_stable": MonteCarloCalibration(
        scenario_count=10_000,
        appreciation_stddev=0.018,
        rent_growth_stddev=0.010,
        mortgage_rate_stddev=0.003,
        investment_volatility_by_risk=_copy_volatility_bands(),
        correlation_matrix=DEFAULT_CORRELATION_MATRIX,
        annual_appreciation_mean=0.028,
        annual_rent_growth_mean=0.025,
    ),
    "sunbelt_growth": MonteCarloCalibration(
        scenario_count=10_000,
        appreciation_stddev=0.032,
        rent_growth_stddev=0.014,
        mortgage_rate_stddev=0.003,
        investment_volatility_by_risk=_copy_volatility_bands(),
        correlation_matrix=DEFAULT_CORRELATION_MATRIX,
        annual_appreciation_mean=0.048,
        annual_rent_growth_mean=0.038,
    ),
})

DEFAULT_BEHAVIORAL_ADJUSTMENTS = BehavioralAdjustments(
    loss_aversion_lambda=2.25,
    panic_sale_expected_return_penalty=0.015,
    stable_income_liquidity_premium=0.0075,
    variable_income_liquidity_premium=0.02,
)

DEFAULT_SYSTEM_ASSUMPTIONS = SystemAssumptions(
    model_version=MODEL_VERSION,
    mortgage_rate=0.0682,
    property_tax_rate=0.0174,
    annual_home_insurance_cents=240_000,
    annual_rent_growth_rate=0.032,
    maintenance_rate=0.01,
    selling_cost_rate=0.07,
    annual_pmi_rate=0.01,
    monte_carlo=DEFAULT_MONTE_CARLO,
    behavioral=DEFAULT_BEHAVIORAL_ADJUSTMENTS,
    retirement_return_autocorrelation=0.15,
    job_offer_bonus_market_beta=0.20,
    job_offer_equity_market_beta=0.35,
    college_tuition_inflation_rate=0.05,
    college_student_loan_rate=0.065,
    college_student_loan_term_years=10,
    buyer_closing_cost_rate=0.03,
)


@dataclass(frozen=True)
class AssumptionBundle:
    assumptions: SystemAssumptions
    audit_trail: tuple[AssumptionAuditItem, ...]


def build_behavioral_audit_trail() -> tuple[AssumptionAuditItem, ...]:
    return (
        AssumptionAuditItem(
            name="Loss aversion lambda",
            parameter="loss_aversion_lambda",
            value=round(DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.loss_aversion_lambda, 2),
            source="Tversky & Kahneman (1992) - Advances in Prospect Theory. Lambda is typically estimated around 2.0-2.5 across empirical studies.",
            last_updated=date(1992, 1, 1),
            notes="Applied to downside outcomes in utility-adjusted probability calculations.",
        ),
        AssumptionAuditItem(
            name="Panic-sale return penalty",
            parameter="panic_sale_expected_return_penalty",
            value=_pct(DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.panic_sale_expected_return_penalty),
            source="DALBAR Quantitative Analysis of Investor Behavior 2023 - investor behavior gap.",
            last_updated=date(2023, 1, 1),
            notes="Applied to expected return when loss_behavior is SELL_TO_CASH.",
        ),
        AssumptionAuditItem(
            name="Illiquidity cost - stable income",
            parameter="liquidity_premium_rate_stable",
            value=_pct(DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.stable_income_liquidity_premium),
            source="Internal calibration. See Flavin & Yamashita (2002) on housing as a constrained asset.",
            last_updated=date(2025, 1, 1),
            notes="Annual cost of capital tied up in home equity for stable-income households.",
        ),
        AssumptionAuditItem(
            name="Illiquidity cost - variable income",
            parameter="liquidity_premium_rate_variable",
            value=_pct(DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.variable_income_liquidity_premium),
            source="Internal calibration. Elevated vs stable-income to reflect precautionary liquidity demand.",
            last_updated=date(2025, 1, 1),
            notes="Applied when income_stability is VARIABLE.",
        ),
        AssumptionAuditItem(
            name="Monte Carlo simulation paths",
            parameter="scenario_count",
            value=DEFAULT_MONTE_CARLO.scenario_count,
            source="Internal model parameter. 10,000 paths yields < 0.5 percentage-point standard error on probability estimates.",
            last_updated=date(2025, 1, 1),
        ),
        AssumptionAuditItem(
            name="Portfolio volatility - conservative",
            parameter="investment_volatility_conservative",
            value=_pct(DEFAULT_MONTE_CARLO.investment_volatility_by_risk[RiskProfile.CONSERVATIVE].stated),
            source="Vanguard Portfolio Studies; historical annual volatility of bond-heavy (20/80 equity/bond) portfolios, 1990-2024.",
            last_updated=date(2024, 1, 1),
        ),
        AssumptionAuditItem(
            name="Portfolio volatility - moderate",
            parameter="investment_volatility_moderate",
            value=_pct(DEFAULT_MONTE_CARLO.investment_volatility_by_risk[RiskProfile.MODERATE].stated),
            source="Vanguard Portfolio Studies; historical annual volatility of balanced (60/40 equity/bond) portfolios, 1990-2024.",
            last_updated=date(2024, 1, 1),
        ),
        AssumptionAuditItem(
            name="Portfolio volatility - aggressive",
            parameter="investment_volatility_aggressive",
            value=_pct(DEFAULT_MONTE_CARLO.investment_volatility_by_risk[RiskProfile.AGGRESSIVE].stated),
            source="S&P 500 realized annual return volatility 1990-2024 (FRED). Represents equity-heavy portfolio.",
            last_updated=date(2024, 1, 1),
        ),
        AssumptionAuditItem(
            name="Home price appreciation volatility",
            parameter="appreciation_stddev",
            value=_pct(DEFAULT_MONTE_CARLO.appreciation_stddev),
            source="FHFA House Price Index - national annual appreciation standard deviation, 1991-2024.",
            last_updated=date(2024, 1, 1),
        ),
    )


def build_default_audit_trail() -> tuple[AssumptionAuditItem, ...]:
    return (
        AssumptionAuditItem(
            name="30-year mortgage rate",
            parameter="mortgage_rate",
            value=_pct(DEFAULT_SYSTEM_ASSUMPTIONS.mortgage_rate),
            source="Freddie Mac PMMS",
            sourced_at=DEFAULT_REFERENCE_DATES.mortgage_rate_date.isoformat(),
            last_updated=DEFAULT_REFERENCE_DATES.mortgage_rate_date,
        ),
        AssumptionAuditItem(
            name="State property tax",
            parameter="property_tax_rate",
            value=_pct(DEFAULT_SYSTEM_ASSUMPTIONS.property_tax_rate),
            source="Tax Foundation 2025",
            sourced_at=DEFAULT_REFERENCE_DATES.property_tax_date.isoformat(),
            last_updated=DEFAULT_REFERENCE_DATES.property_tax_date,
        ),
        AssumptionAuditItem(
            name="Annual home insurance",
            parameter="annual_home_insurance_cents",
            value=_usd(DEFAULT_SYSTEM_ASSUMPTIONS.annual_home_insurance_cents),
            source="Insurance Information Institute 2025",
            sourced_at=DEFAULT_REFERENCE_DATES.insurance_date.isoformat(),
            last_updated=DEFAULT_REFERENCE_DATES.insurance_date,
        ),
        AssumptionAuditItem(
            name="CPI / rent growth",
            parameter="annual_rent_growth_rate",
            value=_pct(DEFAULT_SYSTEM_ASSUMPTIONS.annual_rent_growth_rate),
            source="BLS CPI, Feb 2026",
            sourced_at=DEFAULT_REFERENCE_DATES.inflation_date.isoformat(),
            last_updated=DEFAULT_REFERENCE_DATES.inflation_date,
        ),
        AssumptionAuditItem(
            name="Buyer closing costs",
            parameter="buyer_closing_cost_rate",
            value=_pct(DEFAULT_SYSTEM_ASSUMPTIONS.buyer_closing_cost_rate),
            source="CFPB: What are mortgage closing costs? (2024)",
            last_updated=date(2024, 1, 1),
            notes="Covers origination, title insurance, escrow. Excludes prepaids and reserves.",
        ),
        AssumptionAuditItem(
            name="Annual home maintenance rate",
            parameter="maintenance_rate",
            value=_pct(DEFAULT_SYSTEM_ASSUMPTIONS.maintenance_rate),
            source="National Association of Realtors; Harvard Joint Center for Housing Studies",
            last_updated=date(2025, 1, 1),
            notes=(
                "Estimated as a percentage of home value per year covering routine repairs, "
                "capital replacements, and upkeep. Actual costs vary by home age, type, and region."
            ),
        ),
        AssumptionAuditItem(
            name="Seller closing cost rate",
            parameter="selling_cost_rate",
            value=_pct(DEFAULT_SYSTEM_ASSUMPTIONS.selling_cost_rate),
            source="National Association of Realtors 2024; CoreLogic Seller Transaction Cost Study",
            last_updated=date(2024, 8, 1),
            notes=(
                "Covers agent commissions, transfer taxes, title fees, and attorney costs. "
                "Commission structures shifted following the August 2024 NAR settlement; "
                "actual seller costs in some markets may be lower."
            ),
        ),
        AssumptionAuditItem(
            name="Private mortgage insurance (PMI) annual rate",
            parameter="annual_pmi_rate",
            value=_pct(DEFAULT_SYSTEM_ASSUMPTIONS.annual_pmi_rate),
            source="Urban Institute Housing Finance Policy Center; CFPB mortgage disclosure data 2024",
            last_updated=date(2024, 1, 1),
            notes=(
                "Applied only when the down payment is below 20% of the purchase price. "
                "Actual PMI rate varies by lender, loan-to-value ratio, and borrower credit profile; "
                "1% is a mid-range estimate across conforming loan products."
            ),
        ),
        AssumptionAuditItem(
            name="Loss aversion coefficient (lambda)",
            parameter="loss_aversion_lambda",
            value=round(DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.loss_aversion_lambda, 2),
            source="Kahneman & Tversky (1979) Prospect Theory; Tversky & Kahneman (1992) Advances in Prospect Theory",
            last_updated=date(2024, 1, 1),
            notes=(
                "Controls the utility-adjusted output. Losses are weighted approximately 2.25x more "
                "heavily than equivalent gains, consistent with the behavioral economics consensus estimate. "
                "Individual loss aversion varies; this parameter is applied uniformly."
            ),
        ),
        AssumptionAuditItem(
            name="Panic-sale expected return penalty",
            parameter="panic_sale_expected_return_penalty",
            value=_pct(DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.panic_sale_expected_return_penalty),
            source="DALBAR Quantitative Analysis of Investor Behavior (QAIB) 2024",
            last_updated=date(2024, 1, 1),
            notes=(
                "Reduction in expected investment return applied when loss behavior is set to "
                "'sell to cash'. Reflects the empirical gap between index returns and actual "
                "investor returns caused by behavioral mistiming of exits and re-entries."
            ),
        ),
        AssumptionAuditItem(
            name="Home equity illiquidity premium",
            parameter="liquidity_premium_rate",
            value=(
                f"{DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.stable_income_liquidity_premium * 100:.2f}% "
                f"(stable) / "
                f"{DEFAULT_SYSTEM_ASSUMPTIONS.behavioral.variable_income_liquidity_premium * 100:.2f}% "
                f"(variable income)"
            ),
            source="Internal behavioral calibration; informed by Lustig & Van Nieuwerburgh (2005) housing liquidity research",
            last_updated=date(2025, 1, 1),
            notes=(
                "Annual implicit cost applied to home equity to reflect that housing wealth cannot be "
                "accessed quickly without selling. Higher for variable-income households who face greater "
                "probability of needing liquid capital on short notice."
            ),
        ),
        AssumptionAuditItem(
            name="Monte Carlo simulation count",
            parameter="monte_carlo_scenario_count",
            value=DEFAULT_SYSTEM_ASSUMPTIONS.monte_carlo.scenario_count,
            source="Internal calibration - convergence validated at 10,000 paths",
            last_updated=date(2025, 1, 1),
            notes="Number of simulated market futures used to produce probability distributions.",
        ),
        AssumptionAuditItem(
            name="Monte Carlo market calibration",
            parameter="monte_carlo_calibration",
            value="See full assumptions payload",
            source=(
                "Internal expert calibration; volatility and correlation parameters estimated from "
                "FHFA House Price Index, BLS CPI, and Federal Reserve H.15 data (2000-2024)"
            ),
            last_updated=date(2025, 1, 1),
            notes=(
                "Covers appreciation volatility, rent-growth volatility, investment return volatility "
                "by risk profile, and the 4x4 correlation matrix between home appreciation, investment "
                "returns, rent growth, and mortgage rates. Full parameter values are available at the "
                "/v1/rent-vs-buy/assumptions/current endpoint."
            ),
        ),
        AssumptionAuditItem(
            name="College tuition inflation rate",
            parameter="college_tuition_inflation_rate",
            value=_pct(DEFAULT_SYSTEM_ASSUMPTIONS.college_tuition_inflation_rate),
            source="College Board Trends in College Pricing 2024; 20-year historical average",
            last_updated=date(2024, 10, 1),
            notes=(
                "Annual rate at which tuition, fees, and room and board are assumed to increase. "
                "Actual rates vary substantially by institution type and selectivity."
            ),
        ),
        AssumptionAuditItem(
            name="Federal student loan interest rate",
            parameter="college_student_loan_rate",
            value=_pct(DEFAULT_SYSTEM_ASSUMPTIONS.college_student_loan_rate),
            source="U.S. Department of Education Federal Student Aid - 2024-25 loan rate announcement",
            last_updated=date(2024, 7, 1),
            notes=(
                "Rate applied to direct unsubsidized loans. Undergraduate direct subsidized/unsubsidized "
                "rate for 2024-25 is 6.53%. Private loan rates vary by lender and borrower credit profile."
            ),
        ),
        AssumptionAuditItem(
            name="Standard student loan repayment term",
            parameter="college_student_loan_term_years",
            value=f"{DEFAULT_SYSTEM_ASSUMPTIONS.college_student_loan_term_years} years",
            source="U.S. Department of Education - Standard Repayment Plan",
            last_updated=date(2024, 1, 1),
            notes=(
                "The federal standard repayment plan runs 10 years. Income-driven repayment plans "
                "extend this to 20-25 years; this model uses the standard term as the baseline."
            ),
        ),
    )


# Effective property tax rates by market region (Tax Foundation 2025, state-level median).
# coastal_high_cost: CA (~0.75%), NY (~1.72%), WA (~0.98%) — weighted toward CA/WA high-value markets.
# midwest_stable: IL (~2.23%), OH (~1.59%), MI (~1.54%), IN (~0.85%) — weighted average.
# sunbelt_growth: FL (~0.89%), AZ (~0.63%), GA (~0.93%), TX (~1.74%) — lower-tax states dominate volume.
REGIONAL_PROPERTY_TAX_RATES: Mapping[str, float] = MappingProxyType({
    "national": 0.0174,
    "coastal_high_cost": 0.0115,
    "midwest_stable": 0.0155,
    "sunbelt_growth": 0.0105,
})


def get_calibration(market_region: str) -> MonteCarloCalibration:
    return REGIONAL_CALIBRATIONS.get(market_region, DEFAULT_MONTE_CARLO)


def get_property_tax_rate(market_region: str, assumption_rate: float) -> float:
    """Return the effective property tax rate for a given market region.

    If the caller has applied an explicit per-scenario override (i.e., assumption_rate
    differs from the system default), that override takes precedence.  Otherwise the
    regional rate is used, falling back to the system default for unrecognised regions.
    """
    if assumption_rate != DEFAULT_SYSTEM_ASSUMPTIONS.property_tax_rate:
        return assumption_rate
    return REGIONAL_PROPERTY_TAX_RATES.get(market_region, assumption_rate)


def default_assumption_bundle() -> AssumptionBundle:
    return AssumptionBundle(
        assumptions=DEFAULT_SYSTEM_ASSUMPTIONS,
        audit_trail=build_default_audit_trail(),
    )


def _parse_audit_item(payload: dict) -> AssumptionAuditItem:
    last_updated_raw = payload.get("last_updated")
    last_updated = None
    if isinstance(last_updated_raw, str) and last_updated_raw:
        last_updated = date.fromisoformat(last_updated_raw)

    return AssumptionAuditItem(
        name=payload.get("name"),
        parameter=payload.get("parameter"),
        value=payload.get("value"),
        source=payload.get("source", ""),
        sourced_at=payload.get("sourced_at"),
        last_updated=last_updated,
        notes=payload.get("notes"),
    )


def _parse_monte_carlo_payload(monte_carlo_payload: dict) -> MonteCarloCalibration:
    volatility_payload = monte_carlo_payload.get(
        "investment_volatility_by_risk",
        monte_carlo_payload.get("investment_volatility_bands"),
    )
    return MonteCarloCalibration(
        scenario_count=int(monte_carlo_payload.get("scenario_count", monte_carlo_payload.get("num_simulations", DEFAULT_MONTE_CARLO.scenario_count))),
        appreciation_stddev=float(
            monte_carlo_payload.get("appreciation_stddev", monte_carlo_payload.get("annual_appreciation_std", DEFAULT_MONTE_CARLO.appreciation_stddev))
        ),
        rent_growth_stddev=float(
            monte_carlo_payload.get("rent_growth_stddev", monte_carlo_payload.get("annual_rent_growth_std", DEFAULT_MONTE_CARLO.rent_growth_stddev))
        ),
        mortgage_rate_stddev=float(
            monte_carlo_payload.get("mortgage_rate_stddev", monte_carlo_payload.get("annual_mortgage_rate_std", DEFAULT_MONTE_CARLO.mortgage_rate_stddev))
        ),
        investment_volatility_by_risk={
            RiskProfile(profile): RiskVolatilityBand(
                low=float(band["low"]),
                stated=float(band["stated"]),
                high=float(band["high"]),
            )
            for profile, band in volatility_payload.items()
        },
        correlation_matrix=tuple(
            tuple(float(value) for value in row)
            for row in monte_carlo_payload.get("correlation_matrix", DEFAULT_CORRELATION_MATRIX)
        ),
        annual_appreciation_mean=float(
            monte_carlo_payload.get("annual_appreciation_mean", DEFAULT_MONTE_CARLO.annual_appreciation_mean)
        ),
        annual_rent_growth_mean=float(
            monte_carlo_payload.get("annual_rent_growth_mean", DEFAULT_MONTE_CARLO.annual_rent_growth_mean)
        ),
    )


def assumption_bundle_from_payload(payload: dict) -> AssumptionBundle:
    monte_carlo_payload = payload["monte_carlo"]
    behavioral_payload = payload["behavioral"]
    monte_carlo = _parse_monte_carlo_payload(monte_carlo_payload)
    assumptions = SystemAssumptions(
        model_version=str(payload["model_version"]),
        mortgage_rate=float(payload["mortgage_rate"]),
        property_tax_rate=float(payload["property_tax_rate"]),
        annual_home_insurance_cents=int(payload["annual_home_insurance_cents"]),
        annual_rent_growth_rate=float(payload["annual_rent_growth_rate"]),
        maintenance_rate=float(payload["maintenance_rate"]),
        selling_cost_rate=float(payload["selling_cost_rate"]),
        annual_pmi_rate=float(payload["annual_pmi_rate"]),
        monte_carlo=monte_carlo,
        behavioral=BehavioralAdjustments(
            loss_aversion_lambda=float(behavioral_payload["loss_aversion_lambda"]),
            panic_sale_expected_return_penalty=float(behavioral_payload["panic_sale_expected_return_penalty"]),
            stable_income_liquidity_premium=float(behavioral_payload["stable_income_liquidity_premium"]),
            variable_income_liquidity_premium=float(behavioral_payload["variable_income_liquidity_premium"]),
        ),
        retirement_return_autocorrelation=float(
            payload.get(
                "retirement_return_autocorrelation",
                DEFAULT_SYSTEM_ASSUMPTIONS.retirement_return_autocorrelation,
            )
        ),
        job_offer_bonus_market_beta=float(
            payload.get(
                "job_offer_bonus_market_beta",
                DEFAULT_SYSTEM_ASSUMPTIONS.job_offer_bonus_market_beta,
            )
        ),
        job_offer_equity_market_beta=float(
            payload.get(
                "job_offer_equity_market_beta",
                DEFAULT_SYSTEM_ASSUMPTIONS.job_offer_equity_market_beta,
            )
        ),
        college_tuition_inflation_rate=float(
            payload.get(
                "college_tuition_inflation_rate",
                DEFAULT_SYSTEM_ASSUMPTIONS.college_tuition_inflation_rate,
            )
        ),
        college_student_loan_rate=float(
            payload.get(
                "college_student_loan_rate",
                DEFAULT_SYSTEM_ASSUMPTIONS.college_student_loan_rate,
            )
        ),
        college_student_loan_term_years=int(
            payload.get(
                "college_student_loan_term_years",
                DEFAULT_SYSTEM_ASSUMPTIONS.college_student_loan_term_years,
            )
        ),
        buyer_closing_cost_rate=float(payload.get("buyer_closing_cost_rate", DEFAULT_SYSTEM_ASSUMPTIONS.buyer_closing_cost_rate)),
    )
    audit_payload = payload.get("audit_trail")
    audit_trail = tuple(_parse_audit_item(item) for item in audit_payload) if audit_payload else build_default_audit_trail()
    return AssumptionBundle(assumptions=assumptions, audit_trail=audit_trail)


def assumption_bundle_to_payload(bundle: AssumptionBundle) -> dict:
    assumptions = bundle.assumptions
    monte_carlo = assumptions.monte_carlo
    behavioral = assumptions.behavioral
    return {
        "model_version": assumptions.model_version,
        "mortgage_rate": assumptions.mortgage_rate,
        "property_tax_rate": assumptions.property_tax_rate,
        "annual_home_insurance_cents": assumptions.annual_home_insurance_cents,
        "annual_rent_growth_rate": assumptions.annual_rent_growth_rate,
        "maintenance_rate": assumptions.maintenance_rate,
        "selling_cost_rate": assumptions.selling_cost_rate,
        "annual_pmi_rate": assumptions.annual_pmi_rate,
        "retirement_return_autocorrelation": assumptions.retirement_return_autocorrelation,
        "job_offer_bonus_market_beta": assumptions.job_offer_bonus_market_beta,
        "job_offer_equity_market_beta": assumptions.job_offer_equity_market_beta,
        "college_tuition_inflation_rate": assumptions.college_tuition_inflation_rate,
        "college_student_loan_rate": assumptions.college_student_loan_rate,
        "college_student_loan_term_years": assumptions.college_student_loan_term_years,
        "buyer_closing_cost_rate": assumptions.buyer_closing_cost_rate,
        "monte_carlo": {
            "scenario_count": monte_carlo.scenario_count,
            "appreciation_stddev": monte_carlo.appreciation_stddev,
            "rent_growth_stddev": monte_carlo.rent_growth_stddev,
            "mortgage_rate_stddev": monte_carlo.mortgage_rate_stddev,
            "annual_appreciation_mean": monte_carlo.annual_appreciation_mean,
            "annual_rent_growth_mean": monte_carlo.annual_rent_growth_mean,
            "investment_volatility_by_risk": {
                profile.value: {
                    "low": band.low,
                    "stated": band.stated,
                    "high": band.high,
                }
                for profile, band in monte_carlo.investment_volatility_by_risk.items()
            },
            "correlation_matrix": [list(row) for row in monte_carlo.correlation_matrix],
        },
        "behavioral": {
            "loss_aversion_lambda": behavioral.loss_aversion_lambda,
            "panic_sale_expected_return_penalty": behavioral.panic_sale_expected_return_penalty,
            "stable_income_liquidity_premium": behavioral.stable_income_liquidity_premium,
            "variable_income_liquidity_premium": behavioral.variable_income_liquidity_premium,
        },
        "audit_trail": [
            {
                "name": item.name,
                "parameter": item.parameter,
                "value": item.value,
                "source": item.source,
                "sourced_at": item.sourced_at,
                "last_updated": item.last_updated.isoformat() if item.last_updated else None,
                "notes": item.notes,
            }
            for item in bundle.audit_trail
        ],
    }


def load_assumption_bundle(path: str | Path | None = None) -> AssumptionBundle:
    config_path = Path(path or DEFAULT_ASSUMPTIONS_PATH)
    if not config_path.exists():
        return default_assumption_bundle()

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return assumption_bundle_from_payload(payload)
