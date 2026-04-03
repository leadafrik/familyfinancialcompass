from __future__ import annotations

import numpy as np

from .models import (
    AssumptionAuditItem,
    JobOffer,
    JobOfferAnalysis,
    JobOfferDeterministicSummary,
    JobOfferMonteCarloSummary,
    JobOfferScenarioInput,
    JobOfferYearComparisonRow,
    SystemAssumptions,
)

_BONUS_FACTOR_CAP = 2.5
_EQUITY_FACTOR_CAP = 5.0


class JobOfferEngine:
    def __init__(self, assumptions: SystemAssumptions) -> None:
        self.assumptions = assumptions

    def analyze(
        self,
        user_inputs: JobOfferScenarioInput,
        audit_trail: tuple[AssumptionAuditItem, ...] | None = None,
        seed: int = 7,
    ) -> JobOfferAnalysis:
        deterministic = self._run_deterministic(user_inputs)
        monte_carlo = self._run_monte_carlo(user_inputs, seed)
        warnings = self._build_warnings(user_inputs, deterministic, monte_carlo)
        return JobOfferAnalysis(
            deterministic=deterministic,
            monte_carlo=monte_carlo,
            audit_trail=tuple(audit_trail) if audit_trail is not None else self._build_audit_trail(user_inputs),
            warnings=tuple(warnings),
        )

    def _after_tax(self, taxable_value_cents, marginal_tax_rate: float):
        return np.rint(np.asarray(taxable_value_cents, dtype=np.float64) * (1.0 - marginal_tax_rate)).astype(np.int64)

    def _offer_components(
        self,
        offer: JobOffer,
        comparison_years: int,
        marginal_tax_rate: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int]:
        year_index = np.arange(comparison_years, dtype=np.float64)
        comp_growth = np.power(1.0 + offer.annual_comp_growth_rate, year_index)
        equity_growth = np.power(1.0 + offer.annual_equity_growth_rate, year_index)
        salary = np.rint(offer.base_salary_cents * comp_growth).astype(np.int64)
        bonus = np.rint(offer.target_bonus_cents * comp_growth).astype(np.int64)
        equity = np.rint(offer.annual_equity_vesting_cents * equity_growth).astype(np.int64)
        annual_costs = offer.annual_cost_of_living_delta_cents + offer.annual_commute_cost_cents
        one_time_net = int(self._after_tax(offer.sign_on_bonus_cents, marginal_tax_rate)) - offer.relocation_cost_cents
        return salary, bonus, equity, annual_costs, one_time_net

    def _annual_to_monthly(self, annual_values: np.ndarray) -> np.ndarray:
        values = np.asarray(annual_values, dtype=np.int64)
        is_vector = values.ndim == 1
        if is_vector:
            values = values[np.newaxis, :]
        base = values // 12
        monthly = np.repeat(base, 12, axis=1)
        remainders = values - (base * 12)
        monthly[:, np.arange(values.shape[1]) * 12] += remainders
        if is_vector:
            return monthly[0]
        return monthly

    def _break_even_month(self, monthly_advantage: np.ndarray) -> int | None:
        cumulative = np.cumsum(monthly_advantage)
        crossing = np.flatnonzero(cumulative >= 0)
        if crossing.size == 0:
            return None
        return int(crossing[0] + 1)

    def _run_deterministic(self, user_inputs: JobOfferScenarioInput) -> JobOfferDeterministicSummary:
        salary_a, bonus_a, equity_a, annual_costs_a, one_time_a = self._offer_components(
            user_inputs.offer_a,
            user_inputs.comparison_years,
            user_inputs.marginal_tax_rate,
        )
        salary_b, bonus_b, equity_b, annual_costs_b, one_time_b = self._offer_components(
            user_inputs.offer_b,
            user_inputs.comparison_years,
            user_inputs.marginal_tax_rate,
        )

        annual_a = self._after_tax(salary_a + bonus_a + equity_a, user_inputs.marginal_tax_rate) - annual_costs_a
        annual_b = self._after_tax(salary_b + bonus_b + equity_b, user_inputs.marginal_tax_rate) - annual_costs_b
        annual_a[0] += one_time_a
        annual_b[0] += one_time_b

        cumulative_a = np.cumsum(annual_a)
        cumulative_b = np.cumsum(annual_b)
        monthly_advantage = self._annual_to_monthly(annual_b - annual_a)
        yearly_rows = tuple(
            JobOfferYearComparisonRow(
                year=year + 1,
                offer_a_annual_net_value_cents=int(annual_a[year]),
                offer_b_annual_net_value_cents=int(annual_b[year]),
                offer_a_cumulative_value_cents=int(cumulative_a[year]),
                offer_b_cumulative_value_cents=int(cumulative_b[year]),
                offer_b_minus_offer_a_cents=int(cumulative_b[year] - cumulative_a[year]),
            )
            for year in range(user_inputs.comparison_years)
        )
        return JobOfferDeterministicSummary(
            break_even_month=self._break_even_month(monthly_advantage),
            end_of_horizon_advantage_cents=int(cumulative_b[-1] - cumulative_a[-1]),
            yearly_rows=yearly_rows,
        )

    def _simulate_offer_annual_values(
        self,
        offer: JobOffer,
        comparison_years: int,
        marginal_tax_rate: float,
        market_factor: np.ndarray,
        rng: np.random.Generator,
    ) -> np.ndarray:
        scenario_count = market_factor.shape[0]
        salary, bonus, equity, annual_costs, one_time_net = self._offer_components(
            offer,
            comparison_years,
            marginal_tax_rate,
        )
        bonus_noise = rng.normal(size=(scenario_count, comparison_years))
        equity_noise = rng.normal(size=(scenario_count, comparison_years))
        bonus_factor = np.clip(
            1.0
            + (self.assumptions.job_offer_bonus_market_beta * market_factor)
            + (offer.bonus_payout_volatility * bonus_noise),
            0.0,
            _BONUS_FACTOR_CAP,
        )
        equity_factor = np.clip(
            1.0
            + (self.assumptions.job_offer_equity_market_beta * market_factor)
            + (offer.equity_volatility * equity_noise),
            0.0,
            _EQUITY_FACTOR_CAP,
        )
        bonus_realized = np.rint(bonus[np.newaxis, :] * bonus_factor).astype(np.int64)
        equity_realized = np.rint(equity[np.newaxis, :] * equity_factor).astype(np.int64)
        taxable = salary[np.newaxis, :] + bonus_realized + equity_realized
        annual_net = self._after_tax(taxable, marginal_tax_rate) - annual_costs
        annual_net[:, 0] += one_time_net
        return annual_net

    def _run_monte_carlo(
        self,
        user_inputs: JobOfferScenarioInput,
        seed: int,
    ) -> JobOfferMonteCarloSummary:
        scenario_count = self.assumptions.monte_carlo.scenario_count
        horizon = user_inputs.comparison_years
        rng = np.random.default_rng(seed)
        market_factor = rng.normal(size=(scenario_count, horizon))
        rng_a = np.random.default_rng(rng.integers(2**31))
        rng_b = np.random.default_rng(rng.integers(2**31))
        annual_a = self._simulate_offer_annual_values(
            user_inputs.offer_a,
            horizon,
            user_inputs.marginal_tax_rate,
            market_factor,
            rng_a,
        )
        annual_b = self._simulate_offer_annual_values(
            user_inputs.offer_b,
            horizon,
            user_inputs.marginal_tax_rate,
            market_factor,
            rng_b,
        )

        monthly_advantage = self._annual_to_monthly(annual_b - annual_a)
        cumulative_advantage = np.cumsum(monthly_advantage, axis=1)
        terminal_advantage = cumulative_advantage[:, -1]
        crossed = cumulative_advantage >= 0
        any_cross = np.any(crossed, axis=1)
        first_cross = np.where(any_cross, np.argmax(crossed, axis=1) + 1, 0)
        lambda_ = self.assumptions.behavioral.loss_aversion_lambda
        utility_advantage = np.where(
            terminal_advantage >= 0,
            terminal_advantage.astype(np.float64),
            lambda_ * terminal_advantage.astype(np.float64),
        )
        conditional_median_break_even_month = (
            int(np.median(first_cross[any_cross]))
            if np.any(any_cross)
            else None
        )
        return JobOfferMonteCarloSummary(
            scenario_count=scenario_count,
            probability_offer_b_wins=float(np.mean(terminal_advantage > 0)),
            probability_break_even_within_horizon=float(np.mean(any_cross)),
            conditional_median_break_even_month=conditional_median_break_even_month,
            median_terminal_advantage_cents=int(np.percentile(terminal_advantage, 50)),
            p10_terminal_advantage_cents=int(np.percentile(terminal_advantage, 10)),
            p90_terminal_advantage_cents=int(np.percentile(terminal_advantage, 90)),
            utility_adjusted_p50_advantage_cents=int(np.percentile(utility_advantage, 50)),
        )

    def _equity_share(self, offer: JobOffer) -> float:
        gross = offer.base_salary_cents + offer.target_bonus_cents + offer.annual_equity_vesting_cents
        if gross <= 0:
            return 0.0
        return offer.annual_equity_vesting_cents / gross

    def _build_audit_trail(self, user_inputs: JobOfferScenarioInput) -> tuple[AssumptionAuditItem, ...]:
        return tuple([
            AssumptionAuditItem(
                name="Marginal tax rate",
                parameter="job_offer_marginal_tax_rate",
                value=f"{user_inputs.marginal_tax_rate * 100:.2f}%",
                source="User input",
            ),
            AssumptionAuditItem(
                name="Monte Carlo scenario count",
                parameter="job_offer_scenario_count",
                value=self.assumptions.monte_carlo.scenario_count,
                source="System calibration",
            ),
            AssumptionAuditItem(
                name="Loss aversion lambda",
                parameter="loss_aversion_lambda",
                value=round(self.assumptions.behavioral.loss_aversion_lambda, 2),
                source="Behavioral calibration",
            ),
            AssumptionAuditItem(
                name=f"{user_inputs.offer_a.label} bonus volatility",
                parameter="offer_a_bonus_volatility",
                value=f"{user_inputs.offer_a.bonus_payout_volatility * 100:.0f}%",
                source="User input",
            ),
            AssumptionAuditItem(
                name=f"{user_inputs.offer_a.label} equity volatility",
                parameter="offer_a_equity_volatility",
                value=f"{user_inputs.offer_a.equity_volatility * 100:.0f}%",
                source="User input",
            ),
            AssumptionAuditItem(
                name=f"{user_inputs.offer_b.label} bonus volatility",
                parameter="offer_b_bonus_volatility",
                value=f"{user_inputs.offer_b.bonus_payout_volatility * 100:.0f}%",
                source="User input",
            ),
            AssumptionAuditItem(
                name=f"{user_inputs.offer_b.label} equity volatility",
                parameter="offer_b_equity_volatility",
                value=f"{user_inputs.offer_b.equity_volatility * 100:.0f}%",
                source="User input",
            ),
        ])

    def _build_warnings(
        self,
        user_inputs: JobOfferScenarioInput,
        deterministic: JobOfferDeterministicSummary,
        monte_carlo: JobOfferMonteCarloSummary,
    ) -> list[str]:
        warnings: list[str] = []
        if deterministic.break_even_month is None and deterministic.end_of_horizon_advantage_cents < 0:
            warnings.append("Offer B does not recover its upfront friction within the selected horizon.")
        if self._equity_share(user_inputs.offer_b) >= 0.35:
            warnings.append("Offer B relies heavily on equity compensation, so realized value may diverge sharply from face value.")
        if (
            user_inputs.local_market_concentration
            and user_inputs.offer_b.annual_equity_vesting_cents > 0
            and user_inputs.offer_b.annual_cost_of_living_delta_cents > user_inputs.offer_a.annual_cost_of_living_delta_cents
        ):
            warnings.append("Offer B increases both employer-specific income exposure and local cost exposure at the same time.")
        if 0.45 <= monte_carlo.probability_offer_b_wins <= 0.55:
            warnings.append("The comparison is statistically close; small changes in bonus or equity realization can flip the result.")
        if monte_carlo.median_terminal_advantage_cents > 0 and monte_carlo.p10_terminal_advantage_cents < 0:
            warnings.append("Offer B has positive median upside but still loses in the downside tail.")
        return warnings
