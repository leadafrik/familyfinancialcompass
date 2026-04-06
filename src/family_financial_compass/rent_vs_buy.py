from __future__ import annotations

from datetime import date

import numpy as np
import numpy_financial as npf

from .config import build_behavioral_audit_trail, build_default_audit_trail, get_calibration, get_property_tax_rate
from .models import (
    AmortizationRow,
    AssumptionAuditItem,
    CostBreakdown,
    DeterministicSummary,
    HousingStatus,
    IncomeStability,
    LossBehavior,
    MonteCarloCalibration,
    MonteCarloSummary,
    RentVsBuyAnalysis,
    SystemAssumptions,
    UserScenarioInput,
    YearlyComparisonRow,
)
from .money import annual_to_monthly_payment, annual_to_monthly_rate, percentage
from .tax import (
    after_tax_investment_return,
    capital_gains_tax_on_sale_cents,
    incremental_mortgage_interest_deduction_cents,
    standard_deduction_cents,
)


class RentVsBuyEngine:
    def __init__(self, assumptions: SystemAssumptions):
        self.assumptions = assumptions

    def analyze(
        self,
        user_inputs: UserScenarioInput,
        audit_trail: list[AssumptionAuditItem] | None = None,
        seed: int = 7,
    ) -> RentVsBuyAnalysis:
        self._validate_inputs(user_inputs)
        calibration = self._get_calibration(user_inputs)
        deterministic = self._run_deterministic(user_inputs)
        monte_carlo = self._run_monte_carlo(user_inputs, calibration=calibration, seed=seed)
        warnings = self._build_warnings(user_inputs)
        return RentVsBuyAnalysis(
            deterministic=deterministic,
            monte_carlo=monte_carlo,
            audit_trail=audit_trail or self._build_audit_trail(user_inputs),
            warnings=warnings,
            calibration_used=calibration,
        )

    def analyze_with_calibration(
        self,
        user_inputs: UserScenarioInput,
        calibration: MonteCarloCalibration,
        seed: int = 7,
    ) -> tuple[DeterministicSummary, MonteCarloSummary]:
        """Run deterministic and Monte Carlo with an explicitly supplied calibration.

        Used by sensitivity analysis to vary both user inputs and market calibration
        together without going through the full audit-trail machinery.
        """
        self._validate_inputs(user_inputs)
        return (
            self._run_deterministic(user_inputs),
            self._run_monte_carlo(user_inputs, calibration=calibration, seed=seed),
        )

    def _get_calibration(self, user_inputs: UserScenarioInput) -> MonteCarloCalibration:
        return get_calibration(user_inputs.market_region)

    def _validate_inputs(self, user_inputs: UserScenarioInput) -> None:
        if user_inputs.loan_term_years not in {15, 20, 30}:
            raise ValueError("Loan term must be 15, 20, or 30 years.")
        if not (0.0 <= user_inputs.marginal_tax_rate <= 0.60):
            raise ValueError(
                f"marginal_tax_rate must be between 0.0 and 0.60, got {user_inputs.marginal_tax_rate}"
            )

        closing_costs_cents = self._closing_costs_cents(user_inputs)
        if user_inputs.current_savings_cents < user_inputs.down_payment_cents + closing_costs_cents:
            raise ValueError(
                f"Savings ({user_inputs.current_savings_cents} cents) are insufficient to cover the down payment "
                f"({user_inputs.down_payment_cents} cents) plus estimated buyer closing costs ({closing_costs_cents} cents)."
            )

    def _loan_amount_cents(self, user_inputs: UserScenarioInput) -> int:
        return user_inputs.target_home_price_cents - user_inputs.down_payment_cents

    def _term_months(self, user_inputs: UserScenarioInput) -> int:
        return user_inputs.loan_term_years * 12

    def _horizon_months(self, user_inputs: UserScenarioInput) -> int:
        return user_inputs.horizon_months

    def _closing_costs_cents(self, user_inputs: UserScenarioInput) -> int:
        return int(round(user_inputs.target_home_price_cents * self.assumptions.buyer_closing_cost_rate))

    def _effective_property_tax_rate(self, user_inputs: UserScenarioInput) -> float:
        return get_property_tax_rate(user_inputs.market_region, self.assumptions.property_tax_rate)

    def _liquidity_premium_rate(self, user_inputs: UserScenarioInput) -> float:
        if user_inputs.income_stability == IncomeStability.VARIABLE:
            return self.assumptions.behavioral.liquidity_premium_rate_variable
        return self.assumptions.behavioral.liquidity_premium_rate_stable

    def _effective_investment_return(self, user_inputs: UserScenarioInput) -> float:
        rate = user_inputs.expected_investment_return_rate
        if user_inputs.loss_behavior == LossBehavior.SELL_TO_CASH:
            return max(rate - self.assumptions.behavioral.panic_sale_expected_return_penalty, -0.99)
        return rate

    def _lt_cg_rate(self, user_inputs: UserScenarioInput) -> float:
        return min(max(user_inputs.marginal_tax_rate * 0.6, 0.0), 0.20)

    def _net_investment_return(self, user_inputs: UserScenarioInput, annual_gross_return: float) -> float:
        lt_cg_rate = self._lt_cg_rate(user_inputs)
        return after_tax_investment_return(
            annual_gross_return=annual_gross_return,
            lt_cg_rate=lt_cg_rate,
            dividend_tax_rate=lt_cg_rate,
        )

    def _investment_volatility(self, user_inputs: UserScenarioInput, calibration: MonteCarloCalibration) -> float:
        band = calibration.investment_volatility_by_risk[user_inputs.risk_profile]
        if user_inputs.loss_behavior == LossBehavior.SELL_TO_CASH:
            return band.low
        if user_inputs.loss_behavior == LossBehavior.BUY_MORE:
            return band.high
        return band.stated

    def _build_audit_trail(self, user_inputs: UserScenarioInput) -> list[AssumptionAuditItem]:
        default_parameters = {
            "mortgage_rate",
            "property_tax_rate",
            "annual_home_insurance_cents",
            "annual_rent_growth_rate",
            "buyer_closing_cost_rate",
            "maintenance_rate",
            "selling_cost_rate",
            "annual_pmi_rate",
            "loss_aversion_lambda",
            "panic_sale_expected_return_penalty",
        }
        behavioral_parameters = {
            "scenario_count",
            "appreciation_stddev",
        }
        trail = [
            item
            for item in build_default_audit_trail()
            if item.parameter in default_parameters
        ]
        trail.extend(
            item
            for item in build_behavioral_audit_trail()
            if item.parameter in behavioral_parameters
        )
        calibration = self._get_calibration(user_inputs)
        trail.extend([
            AssumptionAuditItem(
                name="Expected home appreciation",
                parameter="expected_home_appreciation_rate",
                value=percentage(user_inputs.expected_home_appreciation_rate),
                source="User input",
            ),
            AssumptionAuditItem(
                name="Expected investment return",
                parameter="expected_investment_return_rate",
                value=percentage(user_inputs.expected_investment_return_rate),
                source="User input",
            ),
            AssumptionAuditItem(
                name="Liquidity premium",
                parameter="liquidity_premium_rate",
                value=percentage(self._liquidity_premium_rate(user_inputs)),
                source="Internal behavioral calibration; informed by Lustig & Van Nieuwerburgh (2005) housing liquidity research",
                last_updated=date(2025, 1, 1),
                notes=(
                    "Annual implicit cost applied to home equity for the selected household income-stability profile."
                ),
            ),
            AssumptionAuditItem(
                name=f"Investment return volatility ({user_inputs.risk_profile.value} profile)",
                parameter="investment_return_volatility",
                value=percentage(self._investment_volatility(user_inputs, calibration)),
                source="Internal risk calibration; consistent with Vanguard and Morningstar historical portfolio return distributions",
                notes=(
                    f"Annualized standard deviation of investment returns applied in Monte Carlo simulation "
                    f"for a {user_inputs.risk_profile.value} risk profile with "
                    f"{user_inputs.loss_behavior.value.replace('_', ' ')} loss behavior."
                ),
            ),
        ])
        return trail

    def _build_warnings(self, user_inputs: UserScenarioInput) -> list[str]:
        warnings: list[str] = []
        if user_inputs.employment_tied_to_local_economy:
            warnings.append(
                "Employment tied to the local economy creates concentration risk that the cash-flow model does not fully price."
            )
        if user_inputs.current_housing_status == HousingStatus.RENTING:
            warnings.append(
                "Because your reference point is renting, review the 10th-percentile downside alongside the median outcome."
            )
        if user_inputs.loss_behavior == LossBehavior.SELL_TO_CASH:
            warnings.append(
                "Expected investment returns were reduced to reflect likely panic-selling behavior after a large drawdown."
            )
        return warnings

    def _build_amortization_arrays(
        self,
        loan_amount_cents: int,
        annual_rate: float,
        term_months: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        if loan_amount_cents == 0:
            zeros = np.zeros(term_months, dtype=np.int64)
            return zeros, zeros, zeros, zeros

        monthly_rate = annual_rate / 12.0
        periods = np.arange(1, term_months + 1)

        if abs(monthly_rate) < 1e-12:
            principal = np.full(term_months, loan_amount_cents // term_months, dtype=np.int64)
            principal[-1] += loan_amount_cents - int(principal.sum())
            interest = np.zeros(term_months, dtype=np.int64)
            payment = principal.copy()
        else:
            payment = np.round(np.abs(npf.pmt(monthly_rate, term_months, loan_amount_cents))).astype(np.int64)
            interest = np.round(np.abs(npf.ipmt(monthly_rate, periods, term_months, loan_amount_cents))).astype(np.int64)
            principal = np.round(np.abs(npf.ppmt(monthly_rate, periods, term_months, loan_amount_cents))).astype(np.int64)
            principal[-1] += loan_amount_cents - int(principal.sum())
            payment = interest + principal

        balances = loan_amount_cents - np.cumsum(principal)
        if abs(int(balances[-1])) >= 1:
            raise ValueError("Amortization schedule failed to close within one cent.")
        return payment, interest, principal, balances

    def _pad_or_truncate(self, values: np.ndarray, target_length: int) -> np.ndarray:
        if values.shape[0] >= target_length:
            return values[:target_length]
        return np.pad(values, (0, target_length - values.shape[0]))

    def _annual_tax_saving_schedule(
        self,
        interest_cents: np.ndarray,
        property_tax_cents: np.ndarray,
        user_inputs: UserScenarioInput,
    ) -> np.ndarray:
        horizon = interest_cents.shape[0]
        tax_savings = np.zeros(horizon, dtype=np.int64)
        standard_deduction = standard_deduction_cents(user_inputs.filing_status)
        for start in range(0, horizon, 12):
            end = min(start + 12, horizon)
            annual_interest = int(interest_cents[start:end].sum())
            annual_property_tax = int(property_tax_cents[start:end].sum())
            annual_tax_saving = incremental_mortgage_interest_deduction_cents(
                annual_interest_paid_cents=annual_interest,
                annual_property_tax_cents=annual_property_tax,
                marginal_tax_rate=user_inputs.marginal_tax_rate,
                itemizes=user_inputs.itemizes_deductions,
                standard_deduction_cents=standard_deduction,
            )
            base = annual_tax_saving // (end - start)
            tax_savings[start:end] = base
            tax_savings[start : start + (annual_tax_saving % (end - start))] += 1
        return tax_savings

    def _build_home_value_path(
        self,
        initial_home_value_cents: int,
        annual_appreciation_rate: float,
        horizon_months: int,
    ) -> np.ndarray:
        monthly_appreciation = annual_to_monthly_rate(annual_appreciation_rate)
        month_numbers = np.arange(1, horizon_months + 1)
        return np.round(
            initial_home_value_cents * np.power(1.0 + monthly_appreciation, month_numbers)
        ).astype(np.int64)

    def _build_rent_path(
        self,
        initial_monthly_rent_cents: int,
        annual_rent_growth_rate: float,
        horizon_months: int,
    ) -> np.ndarray:
        monthly_rent_growth = annual_to_monthly_rate(annual_rent_growth_rate)
        growth_factors = np.power(1.0 + monthly_rent_growth, np.arange(horizon_months))
        return np.round(initial_monthly_rent_cents * growth_factors).astype(np.int64)

    def _capital_gains_tax_path(
        self,
        home_values: np.ndarray,
        user_inputs: UserScenarioInput,
    ) -> np.ndarray:
        taxes = np.zeros(home_values.shape[0], dtype=np.int64)
        lt_cg_rate = self._lt_cg_rate(user_inputs)
        for index, sale_price_cents in enumerate(home_values):
            taxes[index] = capital_gains_tax_on_sale_cents(
                sale_price_cents=int(sale_price_cents),
                purchase_price_cents=user_inputs.target_home_price_cents,
                capital_improvements_cents=0,
                primary_residence_years=(index + 1) / 12.0,
                filing_status=user_inputs.filing_status,
                lt_cg_rate=lt_cg_rate,
            )
        return taxes

    def _monthly_paths(self, user_inputs: UserScenarioInput, annual_investment_return: float) -> dict[str, np.ndarray | int]:
        horizon = self._horizon_months(user_inputs)
        loan_amount = self._loan_amount_cents(user_inputs)
        term_months = self._term_months(user_inputs)
        closing_costs_cents = self._closing_costs_cents(user_inputs)

        full_payment, full_interest, full_principal, full_balances = self._build_amortization_arrays(
            loan_amount_cents=loan_amount,
            annual_rate=self.assumptions.mortgage_rate,
            term_months=term_months,
        )
        payment = self._pad_or_truncate(full_payment, horizon)
        interest = self._pad_or_truncate(full_interest, horizon)
        principal = self._pad_or_truncate(full_principal, horizon)
        balances = self._pad_or_truncate(full_balances, horizon)

        effective_annual_return = self._net_investment_return(user_inputs, annual_investment_return)
        monthly_investment_return = annual_to_monthly_rate(effective_annual_return)

        home_value = self._build_home_value_path(
            initial_home_value_cents=user_inputs.target_home_price_cents,
            annual_appreciation_rate=user_inputs.expected_home_appreciation_rate,
            horizon_months=horizon,
        )
        rent_path = self._build_rent_path(
            initial_monthly_rent_cents=user_inputs.current_monthly_rent_cents,
            annual_rent_growth_rate=self.assumptions.annual_rent_growth_rate,
            horizon_months=horizon,
        )
        property_tax = np.round(home_value * self._effective_property_tax_rate(user_inputs) / 12.0).astype(np.int64)
        insurance = np.round(
            annual_to_monthly_payment(self.assumptions.annual_home_insurance_cents)
            * np.power(1.0 + annual_to_monthly_rate(self.assumptions.annual_rent_growth_rate), np.arange(horizon))
        ).astype(np.int64)
        maintenance = np.round(home_value * self.assumptions.maintenance_rate / 12.0).astype(np.int64)
        equity = np.maximum(home_value - balances, 0)
        liquidity = np.round(equity * self._liquidity_premium_rate(user_inputs) / 12.0).astype(np.int64)
        tax_saving = self._annual_tax_saving_schedule(interest, property_tax, user_inputs)

        if user_inputs.down_payment_cents / user_inputs.target_home_price_cents >= 0.20:
            pmi = np.zeros(horizon, dtype=np.int64)
        else:
            pmi_amount = int(round(loan_amount * self.assumptions.annual_pmi_rate / 12.0))
            pmi = np.where(balances > (0.80 * home_value), pmi_amount, 0).astype(np.int64)

        buy_cost = payment + property_tax + insurance + maintenance + pmi + liquidity - tax_saving
        rent_extra = np.maximum(buy_cost - rent_path, 0)
        buy_extra = np.maximum(rent_path - buy_cost, 0)

        rent_contribution = np.full(horizon, user_inputs.monthly_savings_cents, dtype=np.int64) + rent_extra
        buy_contribution = np.full(horizon, user_inputs.monthly_savings_cents, dtype=np.int64) + buy_extra

        rent_portfolio = np.empty(horizon, dtype=np.int64)
        buy_portfolio = np.empty(horizon, dtype=np.int64)
        buyer_initial_investable = max(
            0,
            user_inputs.current_savings_cents - user_inputs.down_payment_cents - closing_costs_cents,
        )
        rent_running = np.int64(user_inputs.current_savings_cents)
        buy_running = np.int64(buyer_initial_investable)
        monthly_growth_factor = 1.0 + monthly_investment_return
        for month in range(horizon):
            rent_running = np.int64(round(float(rent_running) * monthly_growth_factor + float(rent_contribution[month])))
            buy_running = np.int64(round(float(buy_running) * monthly_growth_factor + float(buy_contribution[month])))
            rent_portfolio[month] = rent_running
            buy_portfolio[month] = buy_running

        exit_value = np.round(home_value * (1.0 - self.assumptions.selling_cost_rate)).astype(np.int64)
        capital_gains_tax = self._capital_gains_tax_path(home_value, user_inputs)
        home_equity_after_sale = exit_value - balances - capital_gains_tax
        buy_total_wealth = buy_portfolio + home_equity_after_sale
        rent_total_wealth = rent_portfolio
        advantage = buy_total_wealth - rent_total_wealth

        return {
            "payment": payment,
            "interest": interest,
            "principal": principal,
            "balances": balances,
            "home_value": home_value,
            "rent_path": rent_path,
            "property_tax": property_tax,
            "insurance": insurance,
            "maintenance": maintenance,
            "liquidity": liquidity,
            "pmi": pmi,
            "tax_saving": tax_saving,
            "buy_cost": buy_cost,
            "rent_portfolio": rent_portfolio,
            "buy_portfolio": buy_portfolio,
            "buy_total_wealth": buy_total_wealth,
            "rent_total_wealth": rent_total_wealth,
            "advantage": advantage,
            "home_equity_after_sale": home_equity_after_sale,
            "closing_costs_cents": closing_costs_cents,
            "buy_initial_portfolio_cents": buyer_initial_investable,
            "capital_gains_tax_path": capital_gains_tax,
            "total_interest_paid_cents": int(full_interest.sum()),
        }

    def _run_deterministic(self, user_inputs: UserScenarioInput) -> DeterministicSummary:
        paths = self._monthly_paths(
            user_inputs=user_inputs,
            annual_investment_return=self._effective_investment_return(user_inputs),
        )
        advantage = paths["advantage"]
        if not isinstance(advantage, np.ndarray):
            raise ValueError("Deterministic advantage path was not computed.")

        horizon = self._horizon_months(user_inputs)
        break_even_candidates = np.where(advantage >= 0)[0]
        break_even_month = int(break_even_candidates[0] + 1) if break_even_candidates.size else None
        first_year = min(12, horizon)
        terminal_capital_gains_tax = int(paths["capital_gains_tax_path"][-1])
        total_buy_cost = int(np.sum(paths["buy_cost"])) + int(paths["closing_costs_cents"]) + terminal_capital_gains_tax

        breakdown = CostBreakdown(
            principal_and_interest_cents=int(np.sum(paths["payment"][:first_year])),
            property_tax_cents=int(np.sum(paths["property_tax"][:first_year])),
            insurance_cents=int(np.sum(paths["insurance"][:first_year])),
            maintenance_cents=int(np.sum(paths["maintenance"][:first_year])),
            pmi_cents=int(np.sum(paths["pmi"][:first_year])),
            liquidity_premium_cents=int(np.sum(paths["liquidity"][:first_year])),
            closing_costs_cents=int(paths["closing_costs_cents"]),
            total_mortgage_interest_deduction_cents=int(np.sum(paths["tax_saving"])),
            capital_gains_tax_on_sale_cents=terminal_capital_gains_tax,
            total_interest_paid_cents=int(paths["total_interest_paid_cents"]),
            total_cost_of_buying_cents=total_buy_cost,
        )

        yearly_rows: list[YearlyComparisonRow] = []
        row_endpoints = list(range(12, horizon + 1, 12))
        if not row_endpoints or row_endpoints[-1] != horizon:
            row_endpoints.append(horizon)
        for month_index in row_endpoints:
            idx = month_index - 1
            year_start = max(0, month_index - 12)
            year_end = month_index
            yearly_rows.append(
                YearlyComparisonRow(
                    year=int(np.ceil(month_index / 12)),
                    rent_net_worth_cents=int(paths["rent_total_wealth"][idx]),
                    buy_net_worth_cents=int(paths["buy_total_wealth"][idx]),
                    buy_minus_rent_cents=int(advantage[idx]),
                    home_equity_cents=int(paths["home_equity_after_sale"][idx]),
                    rent_portfolio_cents=int(paths["rent_portfolio"][idx]),
                    buy_liquid_portfolio_cents=int(paths["buy_portfolio"][idx]),
                    home_value_cents=int(paths["home_value"][idx]),
                    remaining_principal_cents=int(paths["balances"][idx]),
                    pmi_cents=int(np.sum(paths["pmi"][year_start:year_end])),
                    total_buy_cost_cents=int(np.sum(paths["buy_cost"][year_start:year_end])),
                )
            )

        full_payment, full_interest, full_principal, full_balances = self._build_amortization_arrays(
            loan_amount_cents=self._loan_amount_cents(user_inputs),
            annual_rate=self.assumptions.mortgage_rate,
            term_months=self._term_months(user_inputs),
        )
        amortization_rows = [
            AmortizationRow(
                month=index + 1,
                payment_cents=int(full_payment[index]),
                interest_cents=int(full_interest[index]),
                principal_cents=int(full_principal[index]),
                balance_cents=int(full_balances[index]),
            )
            for index in range(len(full_payment))
        ]

        return DeterministicSummary(
            break_even_month=break_even_month,
            end_of_horizon_advantage_cents=int(advantage[-1]),
            horizon_months=horizon,
            first_year_cost_breakdown=breakdown,
            yearly_rows=yearly_rows,
            amortization_rows=amortization_rows,
        )

    def _base_case_mc_tax_schedule(self, user_inputs: UserScenarioInput, calibration: MonteCarloCalibration) -> np.ndarray:
        horizon = self._horizon_months(user_inputs)
        _, interest, _, _ = self._build_amortization_arrays(
            loan_amount_cents=self._loan_amount_cents(user_inputs),
            annual_rate=self.assumptions.mortgage_rate,
            term_months=self._term_months(user_inputs),
        )
        interest = self._pad_or_truncate(interest, horizon)
        property_tax = np.round(
            self._build_home_value_path(
                initial_home_value_cents=user_inputs.target_home_price_cents,
                annual_appreciation_rate=calibration.annual_appreciation_mean,
                horizon_months=horizon,
            )
            * self._effective_property_tax_rate(user_inputs)
            / 12.0
        ).astype(np.int64)
        return self._annual_tax_saving_schedule(interest, property_tax, user_inputs)

    def _capital_gains_tax_vectorized(
        self,
        sale_price_cents: np.ndarray,
        user_inputs: UserScenarioInput,
        primary_residence_years: float,
    ) -> np.ndarray:
        exclusion_cents = 0
        if primary_residence_years >= 2.0:
            if user_inputs.filing_status.value == "married_filing_jointly":
                exclusion_cents = 500_000_00
            else:
                exclusion_cents = 250_000_00
        gain = sale_price_cents - user_inputs.target_home_price_cents
        taxable_gain = np.maximum(0, gain - exclusion_cents)
        return np.round(taxable_gain * self._lt_cg_rate(user_inputs)).astype(np.int64)

    def _run_monte_carlo(
        self,
        user_inputs: UserScenarioInput,
        calibration: MonteCarloCalibration,
        seed: int,
    ) -> MonteCarloSummary:
        rng = np.random.default_rng(seed)
        scenario_count = calibration.scenario_count
        months = self._horizon_months(user_inputs)
        years = max(int(np.ceil(months / 12)), 1)
        loan_amount = self._loan_amount_cents(user_inputs)
        term_months = self._term_months(user_inputs)
        amortization_months = min(months, term_months)
        closing_costs_cents = self._closing_costs_cents(user_inputs)

        means = np.asarray(
            [
                calibration.annual_appreciation_mean,
                self._effective_investment_return(user_inputs),
                calibration.annual_rent_growth_mean,
                self.assumptions.mortgage_rate,
            ],
            dtype=np.float32,
        )
        stddevs = np.asarray(
            [
                calibration.appreciation_stddev,
                self._investment_volatility(user_inputs, calibration),
                calibration.rent_growth_stddev,
                calibration.mortgage_rate_stddev,
            ],
            dtype=np.float32,
        )
        correlation_cholesky = np.linalg.cholesky(
            np.asarray(calibration.correlation_matrix, dtype=np.float32)
        )
        samples = rng.standard_normal((scenario_count, years, len(means)), dtype=np.float32)
        correlated = samples @ correlation_cholesky.T
        annual_draws = means + correlated * stddevs

        appreciation_annual = np.clip(annual_draws[:, :, 0], -0.20, 0.20)
        investment_annual = np.clip(annual_draws[:, :, 1], -0.40, 0.25)
        lt_cg_rate = self._lt_cg_rate(user_inputs)
        investment_annual = after_tax_investment_return(
            annual_gross_return=investment_annual,
            lt_cg_rate=lt_cg_rate,
            dividend_tax_rate=lt_cg_rate,
        )
        rent_growth_annual = np.clip(annual_draws[:, :, 2], -0.05, 0.15)
        mortgage_rate_annual = np.clip(annual_draws[:, 0, 3], 0.0, 0.20)

        monthly_home_growth_by_year = np.power(1.0 + appreciation_annual, np.float32(1.0 / 12.0)) - 1.0
        monthly_investment_growth_by_year = np.power(1.0 + investment_annual, np.float32(1.0 / 12.0)) - 1.0
        monthly_rent_growth_by_year = np.power(1.0 + rent_growth_annual, np.float32(1.0 / 12.0)) - 1.0

        periods = np.arange(1, amortization_months + 1)
        if loan_amount == 0:
            balances = np.zeros((scenario_count, months), dtype=np.int64)
            payment_scalar = np.zeros(scenario_count, dtype=np.int64)
        else:
            monthly_rate = mortgage_rate_annual / 12.0
            payment_scalar = np.round(np.abs(npf.pmt(monthly_rate, term_months, loan_amount))).astype(np.int64)
            amortization_balances = np.round(
                np.abs(
                    npf.fv(
                        monthly_rate[:, np.newaxis],
                        periods[np.newaxis, :],
                        -payment_scalar[:, np.newaxis],
                        loan_amount,
                    )
                )
            ).astype(np.int64)
            balances = np.zeros((scenario_count, months), dtype=np.int64)
            balances[:, :amortization_months] = amortization_balances

        base_tax_saving = self._base_case_mc_tax_schedule(user_inputs, calibration)
        insurance_base = annual_to_monthly_payment(self.assumptions.annual_home_insurance_cents)
        liquidity_rate = self._liquidity_premium_rate(user_inputs)

        if user_inputs.down_payment_cents / user_inputs.target_home_price_cents >= 0.20:
            pmi_amount = 0
        else:
            pmi_amount = int(round(loan_amount * self.assumptions.annual_pmi_rate / 12.0))

        rent_portfolio = np.full(scenario_count, user_inputs.current_savings_cents, dtype=np.int64)
        buyer_initial_investable = max(
            0,
            user_inputs.current_savings_cents - user_inputs.down_payment_cents - closing_costs_cents,
        )
        buy_portfolio = np.full(scenario_count, buyer_initial_investable, dtype=np.int64)
        home_value = np.full(scenario_count, user_inputs.target_home_price_cents, dtype=np.int64)
        rent_level = np.full(scenario_count, user_inputs.current_monthly_rent_cents, dtype=np.int64)
        insurance_inflation_index = np.ones(scenario_count, dtype=np.float64)
        terminal_advantage = np.zeros(scenario_count, dtype=np.int64)
        first_break_even = np.full(scenario_count, -1, dtype=np.int32)

        for month in range(months):
            year_index = month // 12
            home_value = np.round(
                home_value.astype(np.float64) * (1.0 + monthly_home_growth_by_year[:, year_index])
            ).astype(np.int64)
            if month > 0:
                rent_level = np.round(
                    rent_level.astype(np.float64) * (1.0 + monthly_rent_growth_by_year[:, year_index])
                ).astype(np.int64)
                insurance_inflation_index *= 1.0 + monthly_rent_growth_by_year[:, year_index]

            balance = balances[:, month]
            monthly_payment = payment_scalar if month < amortization_months else 0
            property_tax = np.round(home_value * self._effective_property_tax_rate(user_inputs) / 12.0).astype(np.int64)
            insurance = np.round(insurance_base * insurance_inflation_index).astype(np.int64)
            maintenance = np.round(home_value * self.assumptions.maintenance_rate / 12.0).astype(np.int64)
            equity = np.maximum(home_value - balance, 0)
            monthly_liquidity = np.round(equity * liquidity_rate / 12.0).astype(np.int64)
            if pmi_amount:
                pmi = np.where(balance > (0.80 * home_value), pmi_amount, 0).astype(np.int64)
            else:
                pmi = 0

            # Tax saving uses base-case mortgage rate across all MC paths.
            # Per-path rate variation has second-order impact on deduction.
            buy_cost = monthly_payment + property_tax + insurance + maintenance + pmi + monthly_liquidity - base_tax_saving[month]
            rent_extra = np.maximum(buy_cost - rent_level, 0)
            buy_extra = np.maximum(rent_level - buy_cost, 0)
            investment_growth = 1.0 + monthly_investment_growth_by_year[:, year_index]

            rent_portfolio = np.round(
                rent_portfolio.astype(np.float64) * investment_growth + user_inputs.monthly_savings_cents + rent_extra
            ).astype(np.int64)
            buy_portfolio = np.round(
                buy_portfolio.astype(np.float64) * investment_growth + user_inputs.monthly_savings_cents + buy_extra
            ).astype(np.int64)

            exit_value = np.round(home_value * (1.0 - self.assumptions.selling_cost_rate)).astype(np.int64)
            capital_gains_tax = self._capital_gains_tax_vectorized(
                sale_price_cents=home_value,
                user_inputs=user_inputs,
                primary_residence_years=(month + 1) / 12.0,
            )
            current_advantage = (buy_portfolio + exit_value - balance - capital_gains_tax) - rent_portfolio

            newly_broken_even = (first_break_even < 0) & (current_advantage >= 0)
            first_break_even[newly_broken_even] = month + 1
            terminal_advantage = current_advantage.astype(np.int64)

        lambda_ = self.assumptions.behavioral.loss_aversion_lambda
        utility_advantage = np.where(
            terminal_advantage >= 0,
            terminal_advantage.astype(np.float64),
            lambda_ * terminal_advantage.astype(np.float64),
        )
        break_even_any = first_break_even > 0
        break_even_values = first_break_even[break_even_any]
        if break_even_values.size:
            low = int(np.percentile(break_even_values, 10))
            median = int(np.percentile(break_even_values, 50))
            high = int(np.percentile(break_even_values, 90))
        else:
            low = median = high = None

        return MonteCarloSummary(
            scenario_count=scenario_count,
            probability_buy_beats_rent=float(np.mean(terminal_advantage > 0)),
            probability_break_even_within_horizon=float(np.mean(break_even_any)),
            median_break_even_month=median,
            break_even_ci_80=(low, high),
            median_terminal_advantage_cents=int(np.percentile(terminal_advantage, 50)),
            p10_terminal_advantage_cents=int(np.percentile(terminal_advantage, 10)),
            p90_terminal_advantage_cents=int(np.percentile(terminal_advantage, 90)),
            utility_adjusted_p50_advantage_cents=int(np.percentile(utility_advantage, 50)),
            probability_utility_positive=float(np.mean(utility_advantage > 0)),
        )
