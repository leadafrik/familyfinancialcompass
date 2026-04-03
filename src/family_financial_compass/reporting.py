from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np

from .college_vs_retirement import CollegeVsRetirementEngine
from .job_offer import JobOfferEngine
from .legal import OUTPUT_DISCLAIMER
from .models import (
    AssumptionAuditItem,
    CollegeVsRetirementScenarioInput,
    FilingStatus,
    JobOfferScenarioInput,
    RetirementScenarioInput,
    UserScenarioInput,
)
from .money import annual_to_monthly_rate
from .rent_vs_buy import RentVsBuyEngine
from .retirement_survival import RetirementSurvivalEngine
from .tax import incremental_mortgage_interest_deduction_cents, standard_deduction_cents


def _format_currency(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    return f"{sign}${absolute / 100:,.0f}"


def _format_months(month: int | None) -> str:
    if month is None:
        return "No break-even"
    return f"Month {month}"


def _format_years(year: int | None) -> str:
    if year is None:
        return "No break-even"
    return f"Year {year}"


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


def _serialize_audit_trail(
    audit_trail: list[AssumptionAuditItem] | tuple[AssumptionAuditItem, ...],
) -> list[dict[str, object]]:
    return [
        {
            "label": item.name or item.parameter or "assumption",
            "value": _audit_display_value(item.value),
            "source": item.source,
            "last_updated": item.last_updated.isoformat() if item.last_updated else item.sourced_at,
        }
        for item in audit_trail
    ]


def _merge_audit_trails(
    base_audit_trail: list[AssumptionAuditItem] | tuple[AssumptionAuditItem, ...],
    extra_audit_trail: list[AssumptionAuditItem] | tuple[AssumptionAuditItem, ...],
    prefer_extra_parameters: set[str] | None = None,
) -> list[AssumptionAuditItem]:
    merged = list(base_audit_trail)
    prefer_extra = prefer_extra_parameters or set()
    positions = {
        item.parameter: index
        for index, item in enumerate(merged)
        if item.parameter
    }
    for item in extra_audit_trail:
        if item.parameter and item.parameter in positions:
            if item.parameter in prefer_extra:
                merged[positions[item.parameter]] = item
            continue
        if item.parameter:
            positions[item.parameter] = len(merged)
        merged.append(item)
    return merged


def _exclusion_cents(user_inputs: UserScenarioInput) -> int:
    if user_inputs.horizon_months < 24:
        return 0
    if user_inputs.filing_status == FilingStatus.MARRIED_FILING_JOINTLY:
        return 500_000_00
    return 250_000_00


def _loan_payment(principal_cents: int, annual_rate: float, term_years: int) -> int:
    if principal_cents <= 0:
        return 0
    principal = principal_cents / 100.0
    if annual_rate == 0.0:
        return int(round((principal / term_years) * 100))
    payment = principal * annual_rate / (1.0 - ((1.0 + annual_rate) ** (-term_years)))
    return int(round(payment * 100))


def _groq_narratives(
    report_context: dict[str, object],
    api_key: str,
    model: str,
    base_url: str,
    schema_name: str,
    required_fields: list[str],
) -> dict[str, str]:
    schema = {
        "name": schema_name,
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                field: {"type": "string"}
                for field in required_fields
            },
            "required": required_fields,
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
    schema_name: str,
    required_fields: list[str],
    fallback_fn,
) -> tuple[dict[str, str], str]:
    fallback = fallback_fn(report_context)
    if not groq_api_key:
        return fallback, "template"
    try:
        generated = _groq_narratives(
            report_context=report_context,
            api_key=groq_api_key,
            model=groq_model,
            base_url=groq_base_url,
            schema_name=schema_name,
            required_fields=required_fields,
        )
    except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError, ValueError):
        return fallback, "template"

    merged = fallback.copy()
    for key, value in generated.items():
        if value:
            merged[key] = value
    return merged, "groq"


def _fallback_rent_vs_buy_narratives(report_context: dict[str, object]) -> dict[str, str]:
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


def _fallback_retirement_narratives(report_context: dict[str, object]) -> dict[str, str]:
    verdict = report_context["verdict"]
    questions = report_context["questions"]
    wealth = report_context["wealth_spread"]
    return {
        "survival_verdict": (
            f"The portfolio survives through year {verdict['horizon_years']} in {_format_percent(verdict['survives'])} of simulated futures."
        ),
        "withdrawal_rate_summary": (
            f"Your current withdrawal rate is {_format_percent(questions['withdrawal_rate']['current_rate'], 2)}, "
            f"while the modeled 95% safe rate is {_format_percent(questions['withdrawal_rate']['safe_rate_95'], 2)}."
        ),
        "wealth_range_summary": (
            f"Terminal wealth ranges from about {_format_currency(wealth['p10_terminal_cents'])} in the downside case "
            f"to {_format_currency(wealth['p90_terminal_cents'])} in the upside case, with a median of "
            f"{_format_currency(wealth['median_terminal_cents'])}."
        ),
        "risk_summary": (
            f"The model flags {questions['risk']['warning_count']} warning item(s). "
            f"{questions['risk']['lead_warning']}"
        ),
        "summary": (
            f"The retirement plan is modeled over {verdict['horizon_years']} years, with a deterministic depletion year of "
            f"{verdict['deterministic_depletion_year'] or 'none'}. The survival result is descriptive, not a guarantee."
        ),
    }


def _fallback_job_offer_narratives(report_context: dict[str, object]) -> dict[str, str]:
    offers = report_context["offers"]
    verdict = report_context["verdict"]
    risk = report_context["risk"]
    hidden_costs = report_context["hidden_costs"]
    return {
        "offer_comparison": (
            f"{offers['winner_label']} leads in the deterministic comparison, and offer B wins in "
            f"{_format_percent(verdict['probability_offer_b_wins'])} of simulated futures."
        ),
        "break_even_summary": (
            f"The modeled break-even point is {_format_months(verdict['break_even_month'])}, "
            f"with a deterministic end-of-horizon advantage of {_format_currency(verdict['end_of_horizon_advantage_cents'])}."
        ),
        "risk_summary": (
            f"The downside case is {_format_currency(risk['p10_advantage_cents'])} and the upside case is "
            f"{_format_currency(risk['p90_advantage_cents'])}. Local market concentration is "
            f"{'elevated' if risk['local_market_concentration'] else 'not flagged'}."
        ),
        "hidden_costs_summary": (
            f"The first-year friction difference, including relocation, cost-of-living, and commute effects, is "
            f"{_format_currency(hidden_costs['offer_b_minus_offer_a_first_year_friction_cents'])}."
        ),
        "summary": (
            f"The comparison weighs recurring after-tax value, one-time frictions, and uncertainty around bonus and equity outcomes. "
            f"The utility-adjusted median advantage is {_format_currency(verdict['utility_adjusted_advantage_cents'])}."
        ),
    }


def _fallback_college_vs_retirement_narratives(report_context: dict[str, object]) -> dict[str, str]:
    verdict = report_context["verdict"]
    funding_gap = report_context["funding_gap"]
    retirement_outcomes = report_context["retirement_outcomes"]
    risk = report_context["risk"]
    return {
        "allocation_verdict": (
            f"{verdict['winner_label']} leads in the deterministic path, and retirement-first wins in "
            f"{_format_percent(verdict['probability_retirement_first_wins'])} of simulated futures."
        ),
        "loan_impact_summary": (
            f"College-first produces {_format_currency(funding_gap['college_first_total_loan_cents'])} of modeled student debt, "
            f"versus {_format_currency(funding_gap['retirement_first_total_loan_cents'])} under retirement-first."
        ),
        "retirement_outcome_summary": (
            f"The deterministic terminal retirement balances are {_format_currency(retirement_outcomes['college_first_terminal_cents'])} "
            f"for college-first and {_format_currency(retirement_outcomes['retirement_first_terminal_cents'])} for retirement-first."
        ),
        "risk_summary": (
            f"The downside terminal advantage is {_format_currency(risk['p10_advantage_cents'])} and the upside case is "
            f"{_format_currency(risk['p90_advantage_cents'])}. {risk['lead_warning']}"
        ),
        "summary": (
            f"The model frames the tradeoff between student-loan drag and long-horizon retirement compounding. "
            f"The median utility-adjusted advantage is {_format_currency(verdict['utility_adjusted_advantage_cents'])}."
        ),
    }


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


def _job_offer_sensitivity_entries(
    engine: JobOfferEngine,
    user_inputs: JobOfferScenarioInput,
    seed: int,
) -> list[dict[str, object]]:
    cases: list[tuple[str, JobOfferScenarioInput]] = [("Base case", user_inputs)]
    shorter_years = max(1, user_inputs.comparison_years - 1)
    longer_years = min(10, user_inputs.comparison_years + 2)
    lower_tax = max(0.0, user_inputs.marginal_tax_rate - 0.05)
    higher_tax = min(0.60, user_inputs.marginal_tax_rate + 0.05)
    lower_equity_vol = max(0.0, user_inputs.offer_b.equity_volatility - 0.20)
    higher_equity_vol = min(3.0, user_inputs.offer_b.equity_volatility + 0.20)

    if shorter_years != user_inputs.comparison_years:
        cases.append((f"Comparison window {shorter_years} years", replace(user_inputs, comparison_years=shorter_years)))
    if longer_years != user_inputs.comparison_years:
        cases.append((f"Comparison window {longer_years} years", replace(user_inputs, comparison_years=longer_years)))
    if lower_tax != user_inputs.marginal_tax_rate:
        cases.append((f"Marginal tax rate {lower_tax * 100:.0f}%", replace(user_inputs, marginal_tax_rate=lower_tax)))
    if higher_tax != user_inputs.marginal_tax_rate:
        cases.append((f"Marginal tax rate {higher_tax * 100:.0f}%", replace(user_inputs, marginal_tax_rate=higher_tax)))
    if lower_equity_vol != user_inputs.offer_b.equity_volatility:
        cases.append(
            (
                f"{user_inputs.offer_b.label} equity volatility {lower_equity_vol * 100:.0f}%",
                replace(user_inputs, offer_b=replace(user_inputs.offer_b, equity_volatility=lower_equity_vol)),
            )
        )
    if higher_equity_vol != user_inputs.offer_b.equity_volatility:
        cases.append(
            (
                f"{user_inputs.offer_b.label} equity volatility {higher_equity_vol * 100:.0f}%",
                replace(user_inputs, offer_b=replace(user_inputs.offer_b, equity_volatility=higher_equity_vol)),
            )
        )

    rows: list[dict[str, object]] = []
    for label, scenario_inputs in cases:
        analysis = engine.analyze(scenario_inputs, seed=seed)
        rows.append(
            {
                "label": label,
                "break_even_month": analysis.deterministic.break_even_month,
                "break_even_label": _format_months(analysis.deterministic.break_even_month),
                "probability_offer_b_wins": analysis.monte_carlo.probability_offer_b_wins,
                "probability_offer_b_wins_label": _format_percent(analysis.monte_carlo.probability_offer_b_wins),
            }
        )
    return rows


def build_rent_vs_buy_report(
    engine: RentVsBuyEngine,
    user_inputs: UserScenarioInput,
    audit_trail: list[AssumptionAuditItem] | tuple[AssumptionAuditItem, ...],
    seed: int,
    groq_api_key: str | None = None,
    groq_model: str = "llama-3.3-70b-versatile",
    groq_base_url: str = "https://api.groq.com/openai/v1/chat/completions",
) -> dict[str, object]:
    analysis = engine.analyze(user_inputs, seed=seed)
    report_audit_trail = _merge_audit_trails(
        audit_trail,
        analysis.audit_trail,
        prefer_extra_parameters={"liquidity_premium_rate"},
    )
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
        schema_name="rent_vs_buy_report_narratives",
        required_fields=[
            "verdict_driver",
            "net_worth_summary",
            "sensitivity_summary",
            "question_timeline",
            "question_liquidity",
            "question_risk",
            "summary",
        ],
        fallback_fn=_fallback_rent_vs_buy_narratives,
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
        "audit_trail": _serialize_audit_trail(report_audit_trail),
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


def build_retirement_survival_report(
    engine: RetirementSurvivalEngine,
    user_inputs: RetirementScenarioInput,
    audit_trail: list[AssumptionAuditItem] | tuple[AssumptionAuditItem, ...],
    seed: int,
    groq_api_key: str | None = None,
    groq_model: str = "llama-3.3-70b-versatile",
    groq_base_url: str = "https://api.groq.com/openai/v1/chat/completions",
) -> dict[str, object]:
    analysis = engine.analyze(user_inputs, seed=seed)
    report_audit_trail = _merge_audit_trails(audit_trail, analysis.audit_trail)
    safe_withdrawal_annual_cents = int(round(analysis.monte_carlo.safe_withdrawal_rate_95 * user_inputs.current_portfolio_cents))
    safe_withdrawal_gap_cents = safe_withdrawal_annual_cents - analysis.deterministic.net_annual_withdrawal_cents

    report_context = {
        "verdict": {
            "survives": analysis.monte_carlo.probability_portfolio_survives,
            "safe_withdrawal_rate_95": analysis.monte_carlo.safe_withdrawal_rate_95,
            "deterministic_depletion_year": analysis.deterministic.depletion_year,
            "horizon_years": user_inputs.retirement_years,
        },
        "questions": {
            "withdrawal_rate": {
                "current_rate": analysis.deterministic.current_withdrawal_rate,
                "safe_rate_95": analysis.monte_carlo.safe_withdrawal_rate_95,
                "gap": analysis.monte_carlo.safe_withdrawal_rate_95 - analysis.deterministic.current_withdrawal_rate,
            },
            "risk": {
                "warning_count": len(analysis.warnings),
                "lead_warning": analysis.warnings[0] if analysis.warnings else "No warnings.",
            },
        },
        "wealth_spread": {
            "p10_terminal_cents": analysis.monte_carlo.p10_terminal_wealth_cents,
            "p90_terminal_cents": analysis.monte_carlo.p90_terminal_wealth_cents,
            "median_terminal_cents": analysis.monte_carlo.median_terminal_wealth_cents,
        },
    }
    narratives, narrative_source = _generate_narratives(
        report_context=report_context,
        groq_api_key=groq_api_key,
        groq_model=groq_model,
        groq_base_url=groq_base_url,
        schema_name="retirement_survival_report_narratives",
        required_fields=[
            "survival_verdict",
            "withdrawal_rate_summary",
            "wealth_range_summary",
            "risk_summary",
            "summary",
        ],
        fallback_fn=_fallback_retirement_narratives,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": engine.assumptions.model_version,
        "disclaimer": OUTPUT_DISCLAIMER,
        "verdict": {
            "probability_portfolio_survives": analysis.monte_carlo.probability_portfolio_survives,
            "safe_withdrawal_rate_95": analysis.monte_carlo.safe_withdrawal_rate_95,
            "deterministic_depletion_year": analysis.deterministic.depletion_year,
            "conditional_median_depletion_year": analysis.monte_carlo.conditional_median_depletion_year,
            "horizon_years": user_inputs.retirement_years,
        },
        "inputs_summary": [
            {"label": "Current portfolio", "value": _format_currency(user_inputs.current_portfolio_cents)},
            {"label": "Annual spending", "value": _format_currency(user_inputs.annual_spending_cents)},
            {"label": "Guaranteed income", "value": _format_currency(user_inputs.annual_guaranteed_income_cents)},
            {"label": "Net annual withdrawal", "value": _format_currency(analysis.deterministic.net_annual_withdrawal_cents)},
            {"label": "Retirement horizon", "value": f"{user_inputs.retirement_years} years"},
            {"label": "Expected return", "value": _format_percent(user_inputs.expected_annual_return_rate, 2)},
            {"label": "Risk profile", "value": user_inputs.risk_profile.value.replace("_", " ").title()},
            {"label": "Loss behavior", "value": user_inputs.loss_behavior.value.replace("_", " ").title()},
        ],
        "assumptions_summary": [
            {"label": "Return autocorrelation", "value": f"{engine.assumptions.retirement_return_autocorrelation:.2f}"},
            {"label": "Scenario count", "value": f"{engine.assumptions.monte_carlo.scenario_count:,}"},
            {"label": "Applied volatility", "value": _format_percent(engine._volatility(user_inputs), 2)},
        ],
        "yearly_projection": [
            {
                "year": row.year,
                "deterministic_portfolio_cents": row.deterministic_portfolio_cents,
                "median_portfolio_cents": row.median_portfolio_cents,
                "p10_portfolio_cents": row.p10_portfolio_cents,
                "p90_portfolio_cents": row.p90_portfolio_cents,
                "cumulative_depletion_probability": row.cumulative_depletion_probability,
            }
            for row in analysis.monte_carlo.yearly_rows
        ],
        "wealth_at_horizon": {
            "deterministic_terminal_wealth_cents": analysis.deterministic.terminal_wealth_cents,
            "median_terminal_wealth_cents": analysis.monte_carlo.median_terminal_wealth_cents,
            "p10_terminal_wealth_cents": analysis.monte_carlo.p10_terminal_wealth_cents,
            "p90_terminal_wealth_cents": analysis.monte_carlo.p90_terminal_wealth_cents,
        },
        "withdrawal_analysis": {
            "current_withdrawal_rate": analysis.deterministic.current_withdrawal_rate,
            "safe_withdrawal_rate_95": analysis.monte_carlo.safe_withdrawal_rate_95,
            "withdrawal_rate_gap": analysis.monte_carlo.safe_withdrawal_rate_95 - analysis.deterministic.current_withdrawal_rate,
            "safe_withdrawal_annual_cents": safe_withdrawal_annual_cents,
            "safe_withdrawal_gap_cents": safe_withdrawal_gap_cents,
            "net_annual_withdrawal_cents": analysis.deterministic.net_annual_withdrawal_cents,
        },
        "audit_trail": _serialize_audit_trail(report_audit_trail),
        "warnings": list(analysis.warnings),
        "narratives": narratives,
        "narrative_source": narrative_source,
    }


def build_job_offer_report(
    engine: JobOfferEngine,
    user_inputs: JobOfferScenarioInput,
    audit_trail: list[AssumptionAuditItem] | tuple[AssumptionAuditItem, ...],
    seed: int,
    groq_api_key: str | None = None,
    groq_model: str = "llama-3.3-70b-versatile",
    groq_base_url: str = "https://api.groq.com/openai/v1/chat/completions",
) -> dict[str, object]:
    analysis = engine.analyze(user_inputs, seed=seed)
    report_audit_trail = _merge_audit_trails(audit_trail, analysis.audit_trail)
    winner_label = user_inputs.offer_b.label if analysis.deterministic.end_of_horizon_advantage_cents >= 0 else user_inputs.offer_a.label
    offer_a_sign_on_net = int(round(user_inputs.offer_a.sign_on_bonus_cents * (1.0 - user_inputs.marginal_tax_rate)))
    offer_b_sign_on_net = int(round(user_inputs.offer_b.sign_on_bonus_cents * (1.0 - user_inputs.marginal_tax_rate)))
    sensitivity_rows = _job_offer_sensitivity_entries(engine, user_inputs, seed)
    base_probability = float(sensitivity_rows[0]["probability_offer_b_wins"])
    perturbed_rows = [
        {
            **row,
            "probability_shift_points": abs(float(row["probability_offer_b_wins"]) - base_probability) * 100,
        }
        for row in sensitivity_rows[1:]
    ]
    most_sensitive = max(perturbed_rows, key=lambda row: float(row["probability_shift_points"]))

    hidden_cost_delta = (
        (user_inputs.offer_b.relocation_cost_cents - offer_b_sign_on_net)
        - (user_inputs.offer_a.relocation_cost_cents - offer_a_sign_on_net)
        + (user_inputs.offer_b.annual_cost_of_living_delta_cents - user_inputs.offer_a.annual_cost_of_living_delta_cents)
        + (user_inputs.offer_b.annual_commute_cost_cents - user_inputs.offer_a.annual_commute_cost_cents)
    )
    report_context = {
        "offers": {
            "offer_a_label": user_inputs.offer_a.label,
            "offer_b_label": user_inputs.offer_b.label,
            "winner_label": winner_label,
        },
        "verdict": {
            "probability_offer_b_wins": analysis.monte_carlo.probability_offer_b_wins,
            "break_even_month": analysis.deterministic.break_even_month,
            "end_of_horizon_advantage_cents": analysis.deterministic.end_of_horizon_advantage_cents,
            "utility_adjusted_advantage_cents": analysis.monte_carlo.utility_adjusted_p50_advantage_cents,
        },
        "risk": {
            "p10_advantage_cents": analysis.monte_carlo.p10_terminal_advantage_cents,
            "p90_advantage_cents": analysis.monte_carlo.p90_terminal_advantage_cents,
            "local_market_concentration": user_inputs.local_market_concentration,
        },
        "hidden_costs": {
            "offer_b_minus_offer_a_first_year_friction_cents": hidden_cost_delta,
        },
    }
    narratives, narrative_source = _generate_narratives(
        report_context=report_context,
        groq_api_key=groq_api_key,
        groq_model=groq_model,
        groq_base_url=groq_base_url,
        schema_name="job_offer_report_narratives",
        required_fields=[
            "offer_comparison",
            "break_even_summary",
            "risk_summary",
            "hidden_costs_summary",
            "summary",
        ],
        fallback_fn=_fallback_job_offer_narratives,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": engine.assumptions.model_version,
        "disclaimer": OUTPUT_DISCLAIMER,
        "verdict": {
            "winner_label": winner_label,
            "break_even_month": analysis.deterministic.break_even_month,
            "probability_offer_b_wins": analysis.monte_carlo.probability_offer_b_wins,
            "end_of_horizon_advantage_cents": analysis.deterministic.end_of_horizon_advantage_cents,
            "utility_adjusted_advantage_cents": analysis.monte_carlo.utility_adjusted_p50_advantage_cents,
        },
        "offers": {
            "offer_a_label": user_inputs.offer_a.label,
            "offer_b_label": user_inputs.offer_b.label,
            "offer_a_summary": [
                {"label": "Base salary", "value": _format_currency(user_inputs.offer_a.base_salary_cents)},
                {"label": "Target bonus", "value": _format_currency(user_inputs.offer_a.target_bonus_cents)},
                {"label": "Annual equity vesting", "value": _format_currency(user_inputs.offer_a.annual_equity_vesting_cents)},
                {"label": "Sign-on bonus", "value": _format_currency(user_inputs.offer_a.sign_on_bonus_cents)},
                {"label": "Relocation cost", "value": _format_currency(user_inputs.offer_a.relocation_cost_cents)},
                {"label": "Cost-of-living delta", "value": _format_currency(user_inputs.offer_a.annual_cost_of_living_delta_cents)},
                {"label": "Commute cost", "value": _format_currency(user_inputs.offer_a.annual_commute_cost_cents)},
            ],
            "offer_b_summary": [
                {"label": "Base salary", "value": _format_currency(user_inputs.offer_b.base_salary_cents)},
                {"label": "Target bonus", "value": _format_currency(user_inputs.offer_b.target_bonus_cents)},
                {"label": "Annual equity vesting", "value": _format_currency(user_inputs.offer_b.annual_equity_vesting_cents)},
                {"label": "Sign-on bonus", "value": _format_currency(user_inputs.offer_b.sign_on_bonus_cents)},
                {"label": "Relocation cost", "value": _format_currency(user_inputs.offer_b.relocation_cost_cents)},
                {"label": "Cost-of-living delta", "value": _format_currency(user_inputs.offer_b.annual_cost_of_living_delta_cents)},
                {"label": "Commute cost", "value": _format_currency(user_inputs.offer_b.annual_commute_cost_cents)},
            ],
        },
        "yearly_comparison": [
            {
                "year": row.year,
                "offer_a_annual_net_value_cents": row.offer_a_annual_net_value_cents,
                "offer_b_annual_net_value_cents": row.offer_b_annual_net_value_cents,
                "offer_a_cumulative_value_cents": row.offer_a_cumulative_value_cents,
                "offer_b_cumulative_value_cents": row.offer_b_cumulative_value_cents,
                "offer_b_minus_offer_a_cents": row.offer_b_minus_offer_a_cents,
            }
            for row in analysis.deterministic.yearly_rows
        ],
        "risk": {
            "p10_terminal_advantage_cents": analysis.monte_carlo.p10_terminal_advantage_cents,
            "median_terminal_advantage_cents": analysis.monte_carlo.median_terminal_advantage_cents,
            "p90_terminal_advantage_cents": analysis.monte_carlo.p90_terminal_advantage_cents,
            "local_market_concentration": user_inputs.local_market_concentration,
            "warnings": list(analysis.warnings),
        },
        "hidden_costs": {
            "offer_a": {
                "relocation_cost_cents": user_inputs.offer_a.relocation_cost_cents,
                "annual_cost_of_living_delta_cents": user_inputs.offer_a.annual_cost_of_living_delta_cents,
                "annual_commute_cost_cents": user_inputs.offer_a.annual_commute_cost_cents,
                "after_tax_sign_on_bonus_cents": offer_a_sign_on_net,
            },
            "offer_b": {
                "relocation_cost_cents": user_inputs.offer_b.relocation_cost_cents,
                "annual_cost_of_living_delta_cents": user_inputs.offer_b.annual_cost_of_living_delta_cents,
                "annual_commute_cost_cents": user_inputs.offer_b.annual_commute_cost_cents,
                "after_tax_sign_on_bonus_cents": offer_b_sign_on_net,
            },
            "offer_b_minus_offer_a_first_year_friction_cents": hidden_cost_delta,
        },
        "sensitivity": {
            "rows": [
                {
                    **row,
                    "probability_shift_points": 0.0 if row["label"] == "Base case" else abs(float(row["probability_offer_b_wins"]) - base_probability) * 100,
                }
                for row in sensitivity_rows
            ],
            "most_sensitive_label": str(most_sensitive["label"]),
            "largest_probability_shift_points": float(most_sensitive["probability_shift_points"]),
        },
        "audit_trail": _serialize_audit_trail(report_audit_trail),
        "narratives": narratives,
        "narrative_source": narrative_source,
    }


def build_college_vs_retirement_report(
    engine: CollegeVsRetirementEngine,
    user_inputs: CollegeVsRetirementScenarioInput,
    audit_trail: list[AssumptionAuditItem] | tuple[AssumptionAuditItem, ...],
    seed: int,
    groq_api_key: str | None = None,
    groq_model: str = "llama-3.3-70b-versatile",
    groq_base_url: str = "https://api.groq.com/openai/v1/chat/completions",
) -> dict[str, object]:
    analysis = engine.analyze(user_inputs, seed=seed)
    report_audit_trail = _merge_audit_trails(audit_trail, analysis.audit_trail)
    college_first_payment_cents = _loan_payment(
        analysis.deterministic.college_first_total_loan_cents,
        engine.assumptions.college_student_loan_rate,
        engine.assumptions.college_student_loan_term_years,
    )
    retirement_first_payment_cents = _loan_payment(
        analysis.deterministic.retirement_first_total_loan_cents,
        engine.assumptions.college_student_loan_rate,
        engine.assumptions.college_student_loan_term_years,
    )
    college_first_total_interest_cents = max(
        college_first_payment_cents * engine.assumptions.college_student_loan_term_years
        - analysis.deterministic.college_first_total_loan_cents,
        0,
    )
    retirement_first_total_interest_cents = max(
        retirement_first_payment_cents * engine.assumptions.college_student_loan_term_years
        - analysis.deterministic.retirement_first_total_loan_cents,
        0,
    )
    winner_label = "Retirement first" if analysis.deterministic.end_of_horizon_advantage_cents >= 0 else "College first"
    report_context = {
        "verdict": {
            "probability_retirement_first_wins": analysis.monte_carlo.probability_retirement_first_wins,
            "end_of_horizon_advantage_cents": analysis.deterministic.end_of_horizon_advantage_cents,
            "winner_label": winner_label,
            "utility_adjusted_advantage_cents": analysis.monte_carlo.utility_adjusted_p50_advantage_cents,
        },
        "funding_gap": {
            "college_first_total_loan_cents": analysis.deterministic.college_first_total_loan_cents,
            "retirement_first_total_loan_cents": analysis.deterministic.retirement_first_total_loan_cents,
        },
        "retirement_outcomes": {
            "college_first_terminal_cents": analysis.deterministic.college_first_terminal_retirement_cents,
            "retirement_first_terminal_cents": analysis.deterministic.retirement_first_terminal_retirement_cents,
            "median_retirement_first_cents": analysis.monte_carlo.median_retirement_first_terminal_retirement_cents,
            "median_college_first_cents": analysis.monte_carlo.median_college_first_terminal_retirement_cents,
        },
        "risk": {
            "p10_advantage_cents": analysis.monte_carlo.p10_terminal_advantage_cents,
            "p90_advantage_cents": analysis.monte_carlo.p90_terminal_advantage_cents,
            "lead_warning": analysis.warnings[0] if analysis.warnings else "No warnings were triggered.",
        },
    }
    narratives, narrative_source = _generate_narratives(
        report_context=report_context,
        groq_api_key=groq_api_key,
        groq_model=groq_model,
        groq_base_url=groq_base_url,
        schema_name="college_vs_retirement_report_narratives",
        required_fields=[
            "allocation_verdict",
            "loan_impact_summary",
            "retirement_outcome_summary",
            "risk_summary",
            "summary",
        ],
        fallback_fn=_fallback_college_vs_retirement_narratives,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": engine.assumptions.model_version,
        "disclaimer": OUTPUT_DISCLAIMER,
        "verdict": {
            "winner_label": winner_label,
            "break_even_year": analysis.deterministic.break_even_year,
            "probability_retirement_first_wins": analysis.monte_carlo.probability_retirement_first_wins,
            "end_of_horizon_advantage_cents": analysis.deterministic.end_of_horizon_advantage_cents,
            "utility_adjusted_advantage_cents": analysis.monte_carlo.utility_adjusted_p50_advantage_cents,
        },
        "inputs_summary": [
            {"label": "Current retirement savings", "value": _format_currency(user_inputs.current_retirement_savings_cents)},
            {"label": "Current college savings", "value": _format_currency(user_inputs.current_college_savings_cents)},
            {"label": "Annual savings budget", "value": _format_currency(user_inputs.annual_savings_budget_cents)},
            {"label": "Annual college cost", "value": _format_currency(user_inputs.annual_college_cost_cents)},
            {"label": "Years until college", "value": f"{user_inputs.years_until_college}"},
            {"label": "Years in college", "value": f"{user_inputs.years_in_college}"},
            {"label": "Retirement horizon", "value": f"{user_inputs.retirement_years} years"},
        ],
        "funding_analysis": {
            "college_first_total_loan_cents": analysis.deterministic.college_first_total_loan_cents,
            "retirement_first_total_loan_cents": analysis.deterministic.retirement_first_total_loan_cents,
            "college_first_annual_loan_payment_cents": college_first_payment_cents,
            "retirement_first_annual_loan_payment_cents": retirement_first_payment_cents,
            "college_first_total_interest_cents": college_first_total_interest_cents,
            "retirement_first_total_interest_cents": retirement_first_total_interest_cents,
        },
        "retirement_outcomes": {
            "college_first_terminal_retirement_cents": analysis.deterministic.college_first_terminal_retirement_cents,
            "retirement_first_terminal_retirement_cents": analysis.deterministic.retirement_first_terminal_retirement_cents,
            "median_retirement_first_terminal_retirement_cents": analysis.monte_carlo.median_retirement_first_terminal_retirement_cents,
            "median_college_first_terminal_retirement_cents": analysis.monte_carlo.median_college_first_terminal_retirement_cents,
            "p10_terminal_advantage_cents": analysis.monte_carlo.p10_terminal_advantage_cents,
            "p90_terminal_advantage_cents": analysis.monte_carlo.p90_terminal_advantage_cents,
        },
        "yearly_comparison": [
            {
                "year": row.year,
                "college_first_net_worth_cents": row.college_first_net_worth_cents,
                "retirement_first_net_worth_cents": row.retirement_first_net_worth_cents,
                "retirement_first_minus_college_first_cents": row.retirement_first_minus_college_first_cents,
                "college_first_retirement_cents": row.college_first_retirement_cents,
                "retirement_first_retirement_cents": row.retirement_first_retirement_cents,
                "college_first_college_fund_cents": row.college_first_college_fund_cents,
                "retirement_first_college_fund_cents": row.retirement_first_college_fund_cents,
                "college_first_loan_balance_cents": row.college_first_loan_balance_cents,
                "retirement_first_loan_balance_cents": row.retirement_first_loan_balance_cents,
            }
            for row in analysis.deterministic.yearly_rows
        ],
        "warnings": list(analysis.warnings),
        "audit_trail": _serialize_audit_trail(report_audit_trail),
        "narratives": narratives,
        "narrative_source": narrative_source,
    }
