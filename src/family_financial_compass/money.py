from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


CENT = Decimal("0.01")


def dollars_to_cents(amount: float | int | Decimal) -> int:
    decimal_amount = Decimal(str(amount)).quantize(CENT, rounding=ROUND_HALF_UP)
    return int(decimal_amount * 100)


def cents_to_dollars(cents: int) -> Decimal:
    return (Decimal(cents) / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)


def annual_to_monthly_rate(annual_rate: float) -> float:
    return (1.0 + annual_rate) ** (1.0 / 12.0) - 1.0


def annual_to_monthly_payment(annual_cents: int) -> int:
    return int(round(annual_cents / 12))


def percentage(value: float) -> str:
    return f"{value * 100:.2f}%"
