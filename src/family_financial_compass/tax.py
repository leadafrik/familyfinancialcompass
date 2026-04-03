from __future__ import annotations

from .models import FilingStatus


def incremental_itemized_deduction_cents(
    annual_mortgage_interest_cents: int,
    annual_property_tax_cents: int,
    standard_deduction_cents: int,
) -> int:
    itemized_total = annual_mortgage_interest_cents + annual_property_tax_cents
    return max(0, itemized_total - standard_deduction_cents)


def mortgage_interest_tax_saving_cents(
    annual_mortgage_interest_cents: int,
    annual_property_tax_cents: int,
    marginal_tax_rate: float,
    itemizes: bool,
    standard_deduction_cents: int,
) -> int:
    if not itemizes:
        return 0
    incremental = incremental_itemized_deduction_cents(
        annual_mortgage_interest_cents=annual_mortgage_interest_cents,
        annual_property_tax_cents=annual_property_tax_cents,
        standard_deduction_cents=standard_deduction_cents,
    )
    return int(round(incremental * marginal_tax_rate))


def incremental_mortgage_interest_deduction_cents(
    annual_interest_paid_cents: int,
    annual_property_tax_cents: int,
    marginal_tax_rate: float,
    itemizes: bool,
    standard_deduction_cents: int,
) -> int:
    return mortgage_interest_tax_saving_cents(
        annual_mortgage_interest_cents=annual_interest_paid_cents,
        annual_property_tax_cents=annual_property_tax_cents,
        marginal_tax_rate=marginal_tax_rate,
        itemizes=itemizes,
        standard_deduction_cents=standard_deduction_cents,
    )


def capital_gains_tax_on_sale_cents(
    sale_price_cents: int,
    purchase_price_cents: int,
    capital_improvements_cents: int,
    primary_residence_years: float,
    filing_status: FilingStatus | str,
    lt_cg_rate: float = 0.15,
) -> int:
    if not isinstance(filing_status, FilingStatus):
        filing_status = FilingStatus(filing_status)

    adjusted_basis = purchase_price_cents + capital_improvements_cents
    gain = sale_price_cents - adjusted_basis
    if gain <= 0:
        return 0

    if primary_residence_years >= 2.0:
        if filing_status == FilingStatus.MARRIED_FILING_JOINTLY:
            exclusion_cents = 500_000_00
        else:
            exclusion_cents = 250_000_00
    else:
        exclusion_cents = 0

    taxable_gain = max(0, gain - exclusion_cents)
    return int(round(taxable_gain * lt_cg_rate))


def after_tax_investment_return(
    annual_gross_return: float,
    turnover_rate: float = 0.05,
    lt_cg_rate: float = 0.15,
    qualified_dividend_yield: float = 0.015,
    dividend_tax_rate: float = 0.15,
) -> float:
    tax_drag = (annual_gross_return * turnover_rate * lt_cg_rate) + (qualified_dividend_yield * dividend_tax_rate)
    return annual_gross_return - tax_drag


_STANDARD_DEDUCTION_BY_FILING_STATUS: dict[FilingStatus, int] = {
    FilingStatus.MARRIED_FILING_JOINTLY: 2_950_000,
    FilingStatus.SINGLE: 1_490_000,
}


def standard_deduction_cents(filing_status: FilingStatus | str) -> int:
    if not isinstance(filing_status, FilingStatus):
        filing_status = FilingStatus(filing_status)
    return _STANDARD_DEDUCTION_BY_FILING_STATUS[filing_status]
