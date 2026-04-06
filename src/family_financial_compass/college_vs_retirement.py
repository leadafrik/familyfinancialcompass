from __future__ import annotations

from datetime import date

import numpy as np

from .config import build_behavioral_audit_trail
from .models import (
    AssumptionAuditItem,
    CollegeVsRetirementAnalysis,
    CollegeVsRetirementDeterministicSummary,
    CollegeVsRetirementMonteCarloSummary,
    CollegeVsRetirementScenarioInput,
    CollegeVsRetirementYearComparisonRow,
    LossBehavior,
    SystemAssumptions,
)


class CollegeVsRetirementEngine:
    def __init__(self, assumptions: SystemAssumptions) -> None:
        self.assumptions = assumptions

    def analyze(
        self,
        user_inputs: CollegeVsRetirementScenarioInput,
        audit_trail: list[AssumptionAuditItem] | tuple[AssumptionAuditItem, ...] | None = None,
        seed: int = 7,
    ) -> CollegeVsRetirementAnalysis:
        deterministic = self._run_deterministic(user_inputs)
        monte_carlo = self._run_monte_carlo(user_inputs, seed)
        warnings = self._build_warnings(user_inputs, deterministic, monte_carlo)
        base_trail = tuple(audit_trail or ())
        return CollegeVsRetirementAnalysis(
            deterministic=deterministic,
            monte_carlo=monte_carlo,
            audit_trail=base_trail + self._build_audit_trail(user_inputs),
            warnings=tuple(warnings),
        )

    def _effective_expected_return(self, user_inputs: CollegeVsRetirementScenarioInput) -> float:
        annual_return = user_inputs.expected_annual_return_rate
        if user_inputs.loss_behavior == LossBehavior.SELL_TO_CASH:
            annual_return -= self.assumptions.behavioral.panic_sale_expected_return_penalty
        return max(annual_return, -0.95)

    def _volatility(self, user_inputs: CollegeVsRetirementScenarioInput) -> float:
        band = self.assumptions.monte_carlo.investment_volatility_by_risk[user_inputs.risk_profile]
        if user_inputs.loss_behavior == LossBehavior.SELL_TO_CASH:
            return band.low
        if user_inputs.loss_behavior == LossBehavior.BUY_MORE:
            return band.high
        return band.stated

    def _tuition_schedule(self, user_inputs: CollegeVsRetirementScenarioInput) -> np.ndarray:
        schedule = np.zeros(user_inputs.retirement_years, dtype=np.int64)
        for offset in range(user_inputs.years_in_college):
            year_index = user_inputs.years_until_college + offset
            if year_index >= user_inputs.retirement_years:
                break
            inflated_cost = user_inputs.annual_college_cost_cents * (
                (1.0 + self.assumptions.college_tuition_inflation_rate) ** year_index
            )
            schedule[year_index] = int(round(inflated_cost))
        return schedule

    def _amortizing_payment(self, principal: float) -> float:
        if principal <= 0:
            return 0.0
        rate = self.assumptions.college_student_loan_rate
        term = self.assumptions.college_student_loan_term_years
        if rate == 0.0:
            return principal / term
        return principal * rate / (1.0 - ((1.0 + rate) ** (-term)))

    def _simulate_strategy(
        self,
        user_inputs: CollegeVsRetirementScenarioInput,
        returns: np.ndarray,
        prioritize_college: bool,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
        horizon = user_inputs.retirement_years
        tuition_schedule = self._tuition_schedule(user_inputs)
        net_worth = np.zeros(horizon, dtype=np.int64)
        retirement_path = np.zeros(horizon, dtype=np.int64)
        college_path = np.zeros(horizon, dtype=np.int64)
        loan_path = np.zeros(horizon, dtype=np.int64)

        retirement_balance = float(user_inputs.current_retirement_savings_cents)
        college_balance = float(user_inputs.current_college_savings_cents)
        loan_balance = 0.0
        annual_loan_payment = 0.0
        repayment_years_remaining = 0
        max_loan_balance = 0.0

        for year in range(horizon):
            annual_return = float(returns[year])
            retirement_balance *= 1.0 + annual_return
            college_balance *= 1.0 + annual_return

            available_retirement_contribution = float(user_inputs.annual_savings_budget_cents)
            if repayment_years_remaining > 0 and loan_balance > 0.0:
                loan_balance *= 1.0 + self.assumptions.college_student_loan_rate
                payment = min(annual_loan_payment, loan_balance)
                loan_balance -= payment
                available_retirement_contribution = max(
                    available_retirement_contribution - payment,
                    0.0,
                )
                repayment_years_remaining -= 1

            if prioritize_college and year < user_inputs.years_until_college:
                college_balance += user_inputs.annual_savings_budget_cents
            else:
                retirement_balance += available_retirement_contribution

            tuition_due = float(tuition_schedule[year])
            if tuition_due > 0.0:
                funded = min(college_balance, tuition_due)
                college_balance -= funded
                shortfall = tuition_due - funded
                if shortfall > 0.0:
                    loan_balance += shortfall
                    max_loan_balance = max(max_loan_balance, loan_balance)

            if (
                year == (user_inputs.years_until_college + user_inputs.years_in_college - 1)
                and loan_balance > 0.0
                and repayment_years_remaining == 0
            ):
                annual_loan_payment = self._amortizing_payment(loan_balance)
                repayment_years_remaining = self.assumptions.college_student_loan_term_years

            net_worth[year] = int(round(retirement_balance + college_balance - loan_balance))
            retirement_path[year] = int(round(retirement_balance))
            college_path[year] = int(round(college_balance))
            loan_path[year] = int(round(loan_balance))

        return (
            net_worth,
            retirement_path,
            college_path,
            loan_path,
            int(round(max_loan_balance)),
        )

    def _break_even_year(self, advantage: np.ndarray) -> int | None:
        crossing = np.flatnonzero(advantage >= 0)
        if crossing.size == 0:
            return None
        return int(crossing[0] + 1)

    def _run_deterministic(
        self,
        user_inputs: CollegeVsRetirementScenarioInput,
    ) -> CollegeVsRetirementDeterministicSummary:
        annual_return = np.full(
            user_inputs.retirement_years,
            self._effective_expected_return(user_inputs),
            dtype=np.float64,
        )
        (
            college_first_net_worth,
            college_first_retirement,
            college_first_college,
            college_first_loan,
            college_first_total_loan,
        ) = self._simulate_strategy(user_inputs, annual_return, prioritize_college=True)
        (
            retirement_first_net_worth,
            retirement_first_retirement,
            retirement_first_college,
            retirement_first_loan,
            retirement_first_total_loan,
        ) = self._simulate_strategy(user_inputs, annual_return, prioritize_college=False)

        advantage = retirement_first_net_worth - college_first_net_worth
        yearly_rows = tuple(
            CollegeVsRetirementYearComparisonRow(
                year=year + 1,
                college_first_net_worth_cents=int(college_first_net_worth[year]),
                retirement_first_net_worth_cents=int(retirement_first_net_worth[year]),
                retirement_first_minus_college_first_cents=int(advantage[year]),
                college_first_retirement_cents=int(college_first_retirement[year]),
                retirement_first_retirement_cents=int(retirement_first_retirement[year]),
                college_first_college_fund_cents=int(college_first_college[year]),
                retirement_first_college_fund_cents=int(retirement_first_college[year]),
                college_first_loan_balance_cents=int(college_first_loan[year]),
                retirement_first_loan_balance_cents=int(retirement_first_loan[year]),
            )
            for year in range(user_inputs.retirement_years)
        )
        return CollegeVsRetirementDeterministicSummary(
            break_even_year=self._break_even_year(advantage),
            end_of_horizon_advantage_cents=int(advantage[-1]),
            college_first_terminal_retirement_cents=int(college_first_retirement[-1]),
            retirement_first_terminal_retirement_cents=int(retirement_first_retirement[-1]),
            college_first_total_loan_cents=college_first_total_loan,
            retirement_first_total_loan_cents=retirement_first_total_loan,
            yearly_rows=yearly_rows,
        )

    def _simulate_returns(
        self,
        user_inputs: CollegeVsRetirementScenarioInput,
        seed: int,
    ) -> np.ndarray:
        scenario_count = self.assumptions.monte_carlo.scenario_count
        horizon = user_inputs.retirement_years
        mean_return = self._effective_expected_return(user_inputs)
        volatility = self._volatility(user_inputs)
        rng = np.random.default_rng(seed)
        innovations = rng.normal(size=(scenario_count, horizon))
        returns = np.empty((scenario_count, horizon), dtype=np.float64)
        returns[:, 0] = mean_return + volatility * innovations[:, 0]
        autocorrelation = self.assumptions.retirement_return_autocorrelation
        scaled_volatility = volatility * np.sqrt(max(1.0 - (autocorrelation ** 2), 0.0))
        for year in range(1, horizon):
            returns[:, year] = (
                mean_return
                + autocorrelation * (returns[:, year - 1] - mean_return)
                + scaled_volatility * innovations[:, year]
            )
        return np.clip(returns, -0.95, 1.50)

    def _run_monte_carlo(
        self,
        user_inputs: CollegeVsRetirementScenarioInput,
        seed: int,
    ) -> CollegeVsRetirementMonteCarloSummary:
        returns = self._simulate_returns(user_inputs, seed)
        scenario_count = returns.shape[0]
        horizon = returns.shape[1]

        college_first_net = np.zeros((scenario_count, horizon), dtype=np.int64)
        retirement_first_net = np.zeros((scenario_count, horizon), dtype=np.int64)
        college_first_retirement_terminal = np.zeros(scenario_count, dtype=np.int64)
        retirement_first_retirement_terminal = np.zeros(scenario_count, dtype=np.int64)

        for index in range(scenario_count):
            college_first = self._simulate_strategy(user_inputs, returns[index], prioritize_college=True)
            retirement_first = self._simulate_strategy(user_inputs, returns[index], prioritize_college=False)
            college_first_net[index] = college_first[0]
            retirement_first_net[index] = retirement_first[0]
            college_first_retirement_terminal[index] = college_first[1][-1]
            retirement_first_retirement_terminal[index] = retirement_first[1][-1]

        advantage = retirement_first_net - college_first_net
        terminal_advantage = advantage[:, -1]
        crossed = advantage >= 0
        any_cross = np.any(crossed, axis=1)
        first_cross = np.where(any_cross, np.argmax(crossed, axis=1) + 1, 0)
        lambda_ = self.assumptions.behavioral.loss_aversion_lambda
        utility_advantage = np.where(
            terminal_advantage >= 0,
            terminal_advantage.astype(np.float64),
            lambda_ * terminal_advantage.astype(np.float64),
        )
        conditional_median_break_even_year = (
            int(np.median(first_cross[any_cross]))
            if np.any(any_cross)
            else None
        )
        return CollegeVsRetirementMonteCarloSummary(
            scenario_count=scenario_count,
            probability_retirement_first_wins=float(np.mean(terminal_advantage > 0)),
            probability_break_even_within_horizon=float(np.mean(any_cross)),
            conditional_median_break_even_year=conditional_median_break_even_year,
            median_terminal_advantage_cents=int(np.percentile(terminal_advantage, 50)),
            p10_terminal_advantage_cents=int(np.percentile(terminal_advantage, 10)),
            p90_terminal_advantage_cents=int(np.percentile(terminal_advantage, 90)),
            median_retirement_first_terminal_retirement_cents=int(
                np.percentile(retirement_first_retirement_terminal, 50)
            ),
            median_college_first_terminal_retirement_cents=int(
                np.percentile(college_first_retirement_terminal, 50)
            ),
            utility_adjusted_p50_advantage_cents=int(np.percentile(utility_advantage, 50)),
        )

    def _build_audit_trail(
        self,
        user_inputs: CollegeVsRetirementScenarioInput,
    ) -> tuple[AssumptionAuditItem, ...]:
        trail = [
            item
            for item in build_behavioral_audit_trail()
            if item.parameter in {"scenario_count", "loss_aversion_lambda", "panic_sale_expected_return_penalty"}
        ]
        trail.extend([
            AssumptionAuditItem(
                name="Expected portfolio return",
                parameter="expected_annual_return_rate",
                value=f"{user_inputs.expected_annual_return_rate * 100:.2f}%",
                source="User input",
            ),
            AssumptionAuditItem(
                name="Return autocorrelation",
                parameter="retirement_return_autocorrelation",
                value=round(self.assumptions.retirement_return_autocorrelation, 2),
                source="Retirement simulation calibration. AR(1) momentum parameter.",
                last_updated=date(2025, 1, 1),
            ),
            AssumptionAuditItem(
                name="Tuition inflation rate",
                parameter="college_tuition_inflation_rate",
                value=f"{self.assumptions.college_tuition_inflation_rate * 100:.2f}%",
                source="College Board - Trends in College Pricing 2024. 40-year average net tuition inflation approximately 4-5% annually.",
                last_updated=date(2024, 1, 1),
                notes="Applied to current tuition to project future costs.",
            ),
            AssumptionAuditItem(
                name="Federal student loan rate",
                parameter="college_student_loan_rate",
                value=f"{self.assumptions.college_student_loan_rate * 100:.2f}%",
                source="U.S. Department of Education - Federal Direct Unsubsidized Loan rate for undergraduates, 2024-2025 academic year.",
                last_updated=date(2024, 7, 1),
            ),
            AssumptionAuditItem(
                name="Standard loan repayment term",
                parameter="college_student_loan_term_years",
                value=self.assumptions.college_student_loan_term_years,
                source="U.S. Department of Education - Standard Repayment Plan, 10-year term.",
                last_updated=date(2024, 1, 1),
                notes="Actual repayment term varies by plan (income-driven plans: 20-25 years).",
            ),
            AssumptionAuditItem(
                name=f"Portfolio return volatility ({user_inputs.risk_profile.value} profile)",
                parameter="college_vs_retirement_return_volatility",
                value=f"{self._volatility(user_inputs) * 100:.2f}%",
                source="Internal risk calibration; consistent with Vanguard and Morningstar historical portfolio return distributions",
                notes=(
                    "Annualized standard deviation applied to simulated portfolio returns. "
                    f"Uses the {user_inputs.risk_profile.value} risk profile "
                    f"with {user_inputs.loss_behavior.value.replace('_', ' ')} loss behavior."
                ),
            ),
        ])
        if user_inputs.loss_behavior == LossBehavior.SELL_TO_CASH:
            trail.append(
                AssumptionAuditItem(
                    name="Panic-sale return penalty applied",
                    parameter="panic_sale_expected_return_penalty",
                    value=f"{self.assumptions.behavioral.panic_sale_expected_return_penalty * 100:.2f}%",
                    source="DALBAR QAIB 2023",
                    notes="Return reduced because loss_behavior is SELL_TO_CASH.",
                )
            )
        return tuple(trail)

    def _build_warnings(
        self,
        user_inputs: CollegeVsRetirementScenarioInput,
        deterministic: CollegeVsRetirementDeterministicSummary,
        monte_carlo: CollegeVsRetirementMonteCarloSummary,
    ) -> list[str]:
        warnings: list[str] = []
        if deterministic.retirement_first_total_loan_cents > 0:
            warnings.append(
                "Prioritizing retirement leaves a modeled college funding shortfall that turns into student-loan drag after graduation."
            )
        if deterministic.college_first_terminal_retirement_cents < deterministic.retirement_first_terminal_retirement_cents:
            warnings.append(
                "Prioritizing college first leaves less retirement capital compounding over the full horizon."
            )
        if 0.45 <= monte_carlo.probability_retirement_first_wins <= 0.55:
            warnings.append(
                "The tradeoff is statistically close; small changes in market returns or tuition inflation can flip the result."
            )
        if monte_carlo.median_terminal_advantage_cents > 0 and monte_carlo.p10_terminal_advantage_cents < 0:
            warnings.append(
                "Retirement-first improves the median outcome but still loses in the downside tail."
            )
        if user_inputs.loss_behavior == LossBehavior.SELL_TO_CASH:
            warnings.append(
                "Expected returns were reduced to reflect likely selling after a severe market drawdown."
            )
        return warnings
