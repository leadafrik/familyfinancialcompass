from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np

from .legal import OUTPUT_DISCLAIMER
from .models import FilingStatus, UserScenarioInput
from .money import annual_to_monthly_rate
from .rent_vs_buy import RentVsBuyEngine
from .tax import incremental_mortgage_interest_deduction_cents, standard_deduction_cents


def _format_currency(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    return f"{sign}${absolute / 100:,.0f}"


def _format_months(month: int | None) -> str:
    if month is None:
        return "No break-even"
    return f"Month {month}"


def _format_percent(value: float, digits: int = 0) -> str:
    return f"{value * 100:.{digits}f}%"


def _display_filing_status(status: FilingStatus) -> str:
    if status == FilingStatus.MARRIED_FILING_JOINTLY:
        return "MFJ"
    return "Single"


def _audit_display_value(value: object) -> object:
    if isinstance(value, float):
        if 0.0 <= value <= 1.0:
            return _format_percent(value)
        return round(value, 4)
    return value


def _exclusion_cents(user_inputs: UserScenarioInput) -> int:
    if user_inputs.horizon_months < 24:
        return 0
    if user_inputs.filing_status == FilingStatus.MARRIED_FILING_JOINTLY:
        return 500_000_00
    return 250_000_00


def _fallback_narratives(report_context: dict[str, object]) -> dict[str, str]:
    verdict = report_context["verdict"]
    questions = report_context["questions"]
    sensitivity = report_context["sensitivity"]
    break_even_label = questions["timeline"]["break_even_label"]
    margin_months = questions["timeline"]["margin_months"]
    if verdict["break_even_label"] == "No break-even":
        verdict_driver = (
            f"The base case does not reach break-even inside {questions['timeline']['planned_horizon_months']} months, "
            f"and {sensitivity['most_sensitive_label'].lower()} changes the buy-win probability the most."
        )
    else:
        verdict_driver = (
            f"The base case reaches break-even at {verdict['break_even_label']}, and "
            f"{sensitivity['most_sensitive_label'].lower()} changes the buy-win probability the most."
        )
    if margin_months is None:
        timeline_sentence = (
            f"Your planned horizon is {questions['timeline']['planned_horizon_months']} months and the model does not reach break-even inside that window."
        )
    else:
        timeline_sentence = (
            f"Your planned horizon is {questions['timeline']['planned_horizon_months']} months and the model places break-even at "
            f"{break_even_label}. The gap between them is {margin_months} months."
        )
    return {
        "verdict_driver": verdict_driver,
        "net_worth_summary": (
            f"By year {verdict['horizon_years']:.1f}, the model shows {verdict['winner_label'].lower()} leading in the deterministic path, "
            f"while buying wins in {_format_percent(verdict['probability_buy_beats_rent'])} of simulated futures."
        ),
        "sensitivity_summary": (
            f"The most sensitive assumption is {sensitivity['most_sensitive_label'].lower()}, which moves buy-win probability by "
            f"{sensitivity['largest_probability_shift_points']:.0f} percentage points in this household."
        ),
        "question_timeline": timeline_sentence,
        "question_liquidity": (
            f"After the down payment and estimated closing costs, you retain {questions['liquidity']['remaining_savings_label']}. "
            f"Three months of income is roughly {questions['liquidity']['buffer_threshold_label']}."
        ),
        "question_risk": (
            f"The model flags {questions['risk']['warning_count']} warning item(s). "
            f"{questions['risk']['lead_warning']}"
        ),
        "summary": (
            f"{verdict['winner_label']} is the descriptive base-case result at your chosen horizon. "
            f"Buying wins in {_format_percent(verdict['probability_buy_beats_rent'])} of modeled futures, "
            f"so the decision remains sensitive to the assumptions named in the report."
        ),
    }


def _groq_narratives(
    report_context: dict[str, object],
    api_key: str,
    model: str,
    base_url: str,
) -> dict[str, str]:
    schema = {
        "name": "rent_vs_buy_report_narratives",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "verdict_driver": {"type": "string"},
                "net_worth_summary": {"type": "string"},
                "sensitivity_summary": {"type": "string"},
                "question_timeline": {"type": "string"},
                "question_liquidity": {"type": "string"},
                "question_risk": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": [
                "verdict_driver",
                "net_worth_summary",
                "sensitivity_summary",
                "question_timeline",
                "question_liquidity",
                "question_risk",
                "summary",
            ],
            "additionalProperties": False,
        },
    }
    request_body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write short factual report passages for a household financial analysis. "
                    "Never give prescriptive advice. Never say should, recommend, best choice, or must. "
                    "Use only the facts provided. Keep each field concise and plain-language."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(report_context),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": schema,
        },
    }
    request = Request(
        base_url,
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    content = payload["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    return {key: str(value).strip() for key, value in parsed.items()}


def _generate_narratives(
    report_context: dict[str, object],
    groq_api_key: str | None,
    groq_model: str,
    groq_base_url: str,
) -> tuple[dict[str, str], str]:
    fallback = _fallback_narratives(report_context)
    if not groq_api_key:
        return fallback, "template"
    try:
        generated = _groq_narratives(
            report_context=report_context,
            api_key=groq_api_key,
            model=groq_model,
            base_url=groq_base_url,
        )
    except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError, ValueError):
        return fallback, "template"

    merged = fallback.copy()
    for key, value in generated.items():
        if value:
            merged[key] = value
    return merged, "groq"


def _sensitivity_entries(
    engine: RentVsBuyEngine,
    user_inputs: UserScenarioInput,
    seed: int,
) -> list[dict[str, object]]:
    base_calibration = engine._get_calibration(user_inputs)
    cases = [
        ("Base case", user_inputs, engine.assumptions, base_calibration),
        (
            "Home appreciation 2%",
            replace(user_inputs, expected_home_appreciation_rate=0.02),
            engine.assumptions,
            replace(base_calibration, annual_appreciation_mean=0.02),
        ),
        (
            "Home appreciation 5%",
            replace(user_inputs, expected_home_appreciation_rate=0.05),
            engine.assumptions,
            replace(base_calibration, annual_appreciation_mean=0.05),
        ),
        ("Mortgage rate 5.5%", user_inputs, replace(engine.assumptions, mortgage_rate=0.055), base_calibration),
        ("Investment return 5%", replace(user_inputs, expected_investment_return_rate=0.05), engine.assumptions, base_calibration),
        ("Investment return 9%", replace(user_inputs, expected_investment_return_rate=0.09), engine.assumptions, base_calibration),
        (
            "Rent increases 5%/yr",
            user_inputs,
            replace(engine.assumptions, annual_rent_growth_rate=0.05),
            replace(base_calibration, annual_rent_growth_mean=0.05),
        ),
        ("Stay only 5 years", replace(user_inputs, expected_years_in_home=5.0), engine.assumptions, base_calibration),
        ("Stay 10 years", replace(user_inputs, expected_years_in_home=10.0), engine.assumptions, base_calibration),
    ]
    rows: list[dict[str, object]] = []
    for label, scenario_inputs, assumptions, calibration in cases:
        scenario_engine = RentVsBuyEngine(assumptions)
        deterministic, monte_carlo = scenario_engine.analyze_with_calibration(scenario_inputs, calibration, seed)
        rows.append(
            {
                "label": label,
                "break_even_month": deterministic.break_even_month,
                "break_even_label": _format_months(deterministic.break_even_month),
                "probability_buy_beats_rent": monte_carlo.probability_buy_beats_rent,
                "probability_buy_beats_rent_label": _format_percent(monte_carlo.probability_buy_beats_rent),
            }
        )
    return rows


def build_rent_vs_buy_report(
    engine: RentVsBuyEngine,
    user_inputs: UserScenarioInput,
    audit_trail: list,
    seed: int,
    groq_api_key: str | None = None,
    groq_model: str = "openai/gpt-oss-20b",
    groq_base_url: str = "https://api.groq.com/openai/v1/chat/completions",
) -> dict[str, object]:
    analysis = engine.analyze(user_inputs, audit_trail=list(audit_trail), seed=seed)
    paths = engine._monthly_paths(
        user_inputs=user_inputs,
        annual_investment_return=engine._effective_investment_return(user_inputs),
    )
    horizon_months = user_inputs.horizon_months
    first_year_months = min(12, horizon_months)
    closing_costs_cents = int(paths["closing_costs_cents"])
    gross_year_one_cents = int(
        np.sum(paths["payment"][:first_year_months])
        + np.sum(paths["property_tax"][:first_year_months])
        + np.sum(paths["insurance"][:first_year_months])
        + np.sum(paths["maintenance"][:first_year_months])
        + np.sum(paths["pmi"][:first_year_months])
        + np.sum(paths["liquidity"][:first_year_months])
    )
    actual_year_one_tax_saving = int(np.sum(paths["tax_saving"][:first_year_months]))
    true_year_one_cents = gross_year_one_cents - actual_year_one_tax_saving
    rent_year_one_cents = int(np.sum(paths["rent_path"][:first_year_months]))
    horizon_home_value_cents = int(paths["home_value"][-1])
    gain_before_exclusion_cents = max(horizon_home_value_cents - user_inputs.target_home_price_cents, 0)
    exclusion_cents = _exclusion_cents(user_inputs)
    remaining_savings_cents = user_inputs.current_savings_cents - user_inputs.down_payment_cents - closing_costs_cents
    buffer_threshold_cents = int(round(user_inputs.annual_household_income_cents / 4))

    hypothetical_itemizing = incremental_mortgage_interest_deduction_cents(
        annual_interest_paid_cents=int(np.sum(paths["interest"][:first_year_months])),
        annual_property_tax_cents=int(np.sum(paths["property_tax"][:first_year_months])),
        marginal_tax_rate=user_inputs.marginal_tax_rate,
        itemizes=True,
        standard_deduction_cents=standard_deduction_cents(user_inputs.filing_status),
    )

    effective_annual_return = engine._net_investment_return(
        user_inputs,
        engine._effective_investment_return(user_inputs),
    )
    opportunity_cost_future_value = int(
        round(
            (user_inputs.down_payment_cents + closing_costs_cents)
            * np.power(1.0 + annual_to_monthly_rate(effective_annual_return), horizon_months)
        )
    )

    sensitivity_rows = _sensitivity_entries(engine, user_inputs, seed)
    base_probability = float(sensitivity_rows[0]["probability_buy_beats_rent"])
    perturbed_rows = [
        {
            **row,
            "probability_shift_points": abs(float(row["probability_buy_beats_rent"]) - base_probability) * 100,
        }
        for row in sensitivity_rows[1:]
    ]
    most_sensitive = max(perturbed_rows, key=lambda row: float(row["probability_shift_points"]))

    winner = "buying" if analysis.deterministic.end_of_horizon_advantage_cents >= 0 else "renting"
    yearly_net_worth = [
        {
            "year": row.year,
            "rent_net_worth_cents": row.rent_net_worth_cents,
            "buy_net_worth_cents": row.buy_net_worth_cents,
            "difference_cents": row.buy_minus_rent_cents,
        }
        for row in analysis.deterministic.yearly_rows
    ]

    inputs_summary = [
        {"label": "Home price", "value": _format_currency(user_inputs.target_home_price_cents)},
        {"label": "Down payment", "value": _format_currency(user_inputs.down_payment_cents)},
        {"label": "Current rent", "value": f"{_format_currency(user_inputs.current_monthly_rent_cents)}/mo"},
        {"label": "Income", "value": _format_currency(user_inputs.annual_household_income_cents)},
        {"label": "Savings", "value": _format_currency(user_inputs.current_savings_cents)},
        {"label": "Tax rate", "value": _format_percent(user_inputs.marginal_tax_rate)},
        {"label": "Filing", "value": _display_filing_status(user_inputs.filing_status)},
        {"label": "Itemizing", "value": "Yes" if user_inputs.itemizes_deductions else "No"},
        {"label": "Years planned", "value": f"{user_inputs.expected_years_in_home:g}"},
    ]
    assumptions_summary = [
        {"label": "Mortgage rate", "value": _format_percent(engine.assumptions.mortgage_rate, 2)},
        {"label": "Property tax", "value": _format_percent(engine.assumptions.property_tax_rate, 2)},
        {"label": "Home insurance", "value": f"{_format_currency(int(round(engine.assumptions.annual_home_insurance_cents / 12)))}/mo"},
        {"label": "Maintenance", "value": f"{_format_percent(engine.assumptions.maintenance_rate, 1)}/yr"},
        {"label": "Home appreciation", "value": f"{_format_percent(user_inputs.expected_home_appreciation_rate, 1)}/yr"},
        {"label": "Investment return", "value": f"{_format_percent(user_inputs.expected_investment_return_rate, 1)}/yr"},
        {"label": "Rent increase", "value": f"{_format_percent(engine.assumptions.annual_rent_growth_rate, 1)}/yr"},
        {"label": "Buyer closing costs", "value": _format_percent(engine.assumptions.buyer_closing_cost_rate, 1)},
        {"label": "Seller closing", "value": _format_percent(engine.assumptions.selling_cost_rate, 1)},
        {"label": "Liquidity premium", "value": f"{_format_percent(engine._liquidity_premium_rate(user_inputs), 2)}/yr"},
    ]

    report_context = {
        "verdict": {
            "winner_label": winner.capitalize(),
            "horizon_years": user_inputs.expected_years_in_home,
            "break_even_label": _format_months(analysis.deterministic.break_even_month),
            "probability_buy_beats_rent": analysis.monte_carlo.probability_buy_beats_rent,
        },
        "sensitivity": {
            "most_sensitive_label": str(most_sensitive["label"]),
            "largest_probability_shift_points": float(most_sensitive["probability_shift_points"]),
        },
        "questions": {
            "timeline": {
                "planned_horizon_months": horizon_months,
                "break_even_label": _format_months(analysis.deterministic.break_even_month),
                "margin_months": None
                if analysis.deterministic.break_even_month is None
                else horizon_months - analysis.deterministic.break_even_month,
            },
            "liquidity": {
                "remaining_savings_label": _format_currency(remaining_savings_cents),
                "buffer_threshold_label": _format_currency(buffer_threshold_cents),
            },
            "risk": {
                "warning_count": len(analysis.warnings),
                "lead_warning": analysis.warnings[0] if analysis.warnings else "No model warnings were triggered.",
            },
        },
    }
    narratives, narrative_source = _generate_narratives(
        report_context=report_context,
        groq_api_key=groq_api_key,
        groq_model=groq_model,
        groq_base_url=groq_base_url,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": engine.assumptions.model_version,
        "disclaimer": OUTPUT_DISCLAIMER,
        "winner": winner,
        "verdict": {
            "headline": f"{winner.upper()} IS FINANCIALLY BETTER",
            "winner_label": winner.capitalize(),
            "break_even_month": analysis.deterministic.break_even_month,
            "break_even_years": None
            if analysis.deterministic.break_even_month is None
            else round(analysis.deterministic.break_even_month / 12.0, 2),
            "horizon_years": user_inputs.expected_years_in_home,
            "deterministic_advantage_cents": analysis.deterministic.end_of_horizon_advantage_cents,
            "probability_buy_beats_rent": analysis.monte_carlo.probability_buy_beats_rent,
            "p10_terminal_advantage_cents": analysis.monte_carlo.p10_terminal_advantage_cents,
            "p90_terminal_advantage_cents": analysis.monte_carlo.p90_terminal_advantage_cents,
        },
        "inputs_summary": inputs_summary,
        "assumptions_summary": assumptions_summary,
        "audit_trail": [
            {
                "label": item.name or item.parameter or "assumption",
                "value": _audit_display_value(item.value),
                "source": item.source,
                "last_updated": item.last_updated.isoformat() if item.last_updated else item.sourced_at,
            }
            for item in audit_trail
        ],
        "yearly_net_worth": yearly_net_worth,
        "year_one_costs": {
            "principal_and_interest_cents": int(np.sum(paths["payment"][:first_year_months])),
            "property_tax_cents": int(np.sum(paths["property_tax"][:first_year_months])),
            "insurance_cents": int(np.sum(paths["insurance"][:first_year_months])),
            "maintenance_cents": int(np.sum(paths["maintenance"][:first_year_months])),
            "pmi_cents": int(np.sum(paths["pmi"][:first_year_months])),
            "liquidity_premium_cents": int(np.sum(paths["liquidity"][:first_year_months])),
            "gross_annual_cents": gross_year_one_cents,
            "gross_monthly_cents": int(round(gross_year_one_cents / first_year_months)),
            "mortgage_interest_tax_saving_cents": actual_year_one_tax_saving,
            "true_annual_cents": true_year_one_cents,
            "true_monthly_cents": int(round(true_year_one_cents / first_year_months)),
            "current_rent_annual_cents": rent_year_one_cents,
            "cash_difference_annual_cents": true_year_one_cents - rent_year_one_cents,
        },
        "hidden_factors": {
            "initial_purchase_cash_cents": user_inputs.down_payment_cents + closing_costs_cents,
            "equity_after_sale_horizon_cents": int(paths["home_equity_after_sale"][-1]),
            "closing_costs_cents": closing_costs_cents,
            "opportunity_cost_future_value_cents": opportunity_cost_future_value,
            "actual_tax_saving_year_one_cents": actual_year_one_tax_saving,
            "hypothetical_itemized_year_one_cents": hypothetical_itemizing,
            "capital_gains": {
                "estimated_gain_cents": gain_before_exclusion_cents,
                "exclusion_cents": exclusion_cents,
                "capital_gains_tax_cents": int(paths["capital_gains_tax_path"][-1]),
            },
        },
        "sensitivity": {
            "rows": [
                {
                    **row,
                    "probability_shift_points": 0.0 if row["label"] == "Base case" else abs(float(row["probability_buy_beats_rent"]) - base_probability) * 100,
                }
                for row in sensitivity_rows
            ],
            "most_sensitive_label": str(most_sensitive["label"]),
            "largest_probability_shift_points": float(most_sensitive["probability_shift_points"]),
        },
        "questions": {
            "timeline": {
                "break_even_month": analysis.deterministic.break_even_month,
                "planned_horizon_months": horizon_months,
                "margin_months": None
                if analysis.deterministic.break_even_month is None
                else horizon_months - analysis.deterministic.break_even_month,
            },
            "liquidity": {
                "remaining_savings_cents": remaining_savings_cents,
                "buffer_threshold_cents": buffer_threshold_cents,
            },
            "risk": {
                "warnings": analysis.warnings,
            },
        },
        "narratives": narratives,
        "narrative_source": narrative_source,
    }
