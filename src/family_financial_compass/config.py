from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

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

REGIONAL_CALIBRATIONS: dict[str, MonteCarloCalibration] = {
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
}

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
    buyer_closing_cost_rate=0.03,
)


@dataclass(frozen=True)
class AssumptionBundle:
    assumptions: SystemAssumptions
    audit_trail: tuple[AssumptionAuditItem, ...]


def build_default_audit_trail() -> list[AssumptionAuditItem]:
    return [
        AssumptionAuditItem(
            name="30-year mortgage rate",
            parameter="mortgage_rate",
            value="6.82%",
            source="Freddie Mac PMMS",
            sourced_at=DEFAULT_REFERENCE_DATES.mortgage_rate_date.isoformat(),
            last_updated=DEFAULT_REFERENCE_DATES.mortgage_rate_date,
        ),
        AssumptionAuditItem(
            name="State property tax",
            parameter="property_tax_rate",
            value="1.74%",
            source="Tax Foundation 2025",
            sourced_at=DEFAULT_REFERENCE_DATES.property_tax_date.isoformat(),
            last_updated=DEFAULT_REFERENCE_DATES.property_tax_date,
        ),
        AssumptionAuditItem(
            name="Annual home insurance",
            parameter="annual_home_insurance_cents",
            value="$2,400",
            source="Insurance Information Institute 2025",
            sourced_at=DEFAULT_REFERENCE_DATES.insurance_date.isoformat(),
            last_updated=DEFAULT_REFERENCE_DATES.insurance_date,
        ),
        AssumptionAuditItem(
            name="CPI / rent growth",
            parameter="annual_rent_growth_rate",
            value="3.20%",
            source="BLS CPI, Feb 2026",
            sourced_at=DEFAULT_REFERENCE_DATES.inflation_date.isoformat(),
            last_updated=DEFAULT_REFERENCE_DATES.inflation_date,
        ),
        AssumptionAuditItem(
            parameter="buyer_closing_cost_rate",
            value=0.03,
            source="CFPB: What are mortgage closing costs? (2024)",
            last_updated=date(2024, 1, 1),
            notes="Covers origination, title insurance, escrow. Excludes prepaids and reserves.",
        ),
    ]


def get_calibration(market_region: str) -> MonteCarloCalibration:
    return REGIONAL_CALIBRATIONS.get(market_region, DEFAULT_MONTE_CARLO)


def default_assumption_bundle() -> AssumptionBundle:
    return AssumptionBundle(
        assumptions=DEFAULT_SYSTEM_ASSUMPTIONS,
        audit_trail=tuple(build_default_audit_trail()),
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


def load_assumption_bundle(path: str | Path | None = None) -> AssumptionBundle:
    config_path = Path(path or DEFAULT_ASSUMPTIONS_PATH)
    if not config_path.exists():
        return default_assumption_bundle()

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    monte_carlo_payload = payload["monte_carlo"]
    behavioral_payload = payload["behavioral"]
    volatility_payload = monte_carlo_payload.get(
        "investment_volatility_by_risk",
        monte_carlo_payload.get("investment_volatility_bands"),
    )

    monte_carlo = MonteCarloCalibration(
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
            for row in monte_carlo_payload["correlation_matrix"]
        ),
        annual_appreciation_mean=float(
            monte_carlo_payload.get("annual_appreciation_mean", DEFAULT_MONTE_CARLO.annual_appreciation_mean)
        ),
        annual_rent_growth_mean=float(
            monte_carlo_payload.get("annual_rent_growth_mean", DEFAULT_MONTE_CARLO.annual_rent_growth_mean)
        ),
    )
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
        buyer_closing_cost_rate=float(payload.get("buyer_closing_cost_rate", DEFAULT_SYSTEM_ASSUMPTIONS.buyer_closing_cost_rate)),
    )
    audit_payload = payload.get("audit_trail")
    audit_trail = tuple(_parse_audit_item(item) for item in audit_payload) if audit_payload else tuple(build_default_audit_trail())
    return AssumptionBundle(assumptions=assumptions, audit_trail=audit_trail)
