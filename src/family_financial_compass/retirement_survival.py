from __future__ import annotations

from datetime import date

import numpy as np

from .config import build_behavioral_audit_trail
from .models import (
    AssumptionAuditItem,
    LossBehavior,
    RetirementDeterministicSummary,
    RetirementMonteCarloSummary,
    RetirementScenarioInput,
    RetirementSurvivalAnalysis,
    RetirementYearProjectionRow,
    SystemAssumptions,
)

_SAFE_WITHDRAWAL_TARGET = 0.95


class RetirementSurvivalEngine:
    def __init__(self, assumptions: SystemAssumptions) -> None:
        self.assumptions = assumptions

    def analyze(
        self,
        user_inputs: RetirementScenarioInput,
        audit_trail: list[AssumptionAuditItem] | None = None,
        seed: int = 7,
    ) -> RetirementSurvivalAnalysis:
        deterministic_path = self._run_deterministic_path(user_inputs)
        monte_carlo = self._run_monte_carlo(user_inputs, deterministic_path, seed)
        warnings = self._build_warnings(user_inputs, monte_carlo)
        return RetirementSurvivalAnalysis(
            deterministic=RetirementDeterministicSummary(
                net_annual_withdrawal_cents=user_inputs.net_annual_withdrawal_cents,
                current_withdrawal_rate=user_inputs.current_withdrawal_rate,
                depletion_year=self._depletion_year(deterministic_path),
                terminal_wealth_cents=int(deterministic_path[-1]),
            ),
            monte_carlo=monte_carlo,
            audit_trail=audit_trail or self._build_audit_trail(user_inputs),
            warnings=tuple(warnings),
        )

    def _effective_expected_return(self, user_inputs: RetirementScenarioInput) -> float:
        annual_return = user_inputs.expected_annual_return_rate
        if user_inputs.loss_behavior == LossBehavior.SELL_TO_CASH:
            annual_return -= self.assumptions.behavioral.panic_sale_expected_return_penalty
        return max(annual_return, -0.95)

    def _volatility(self, user_inputs: RetirementScenarioInput) -> float:
        band = self.assumptions.monte_carlo.investment_volatility_by_risk[user_inputs.risk_profile]
        if user_inputs.loss_behavior == LossBehavior.SELL_TO_CASH:
            return band.low
        if user_inputs.loss_behavior == LossBehavior.BUY_MORE:
            return band.high
        return band.stated

    def _run_deterministic_path(self, user_inputs: RetirementScenarioInput) -> np.ndarray:
        path = np.zeros(user_inputs.retirement_years, dtype=np.int64)
        balance = float(user_inputs.current_portfolio_cents)
        annual_return = self._effective_expected_return(user_inputs)
        annual_withdrawal = float(user_inputs.net_annual_withdrawal_cents)
        for year in range(user_inputs.retirement_years):
            balance = max(balance * (1.0 + annual_return) - annual_withdrawal, 0.0)
            path[year] = int(round(balance))
        return path

    def _simulate_paths(
        self,
        user_inputs: RetirementScenarioInput,
        annual_withdrawal_cents: int,
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
        returns = np.clip(returns, -0.95, 1.50)

        paths = np.zeros((scenario_count, horizon), dtype=np.int64)
        balances = np.full(scenario_count, float(user_inputs.current_portfolio_cents), dtype=np.float64)
        annual_withdrawal = float(annual_withdrawal_cents)
        for year in range(horizon):
            balances = np.maximum(balances * (1.0 + returns[:, year]) - annual_withdrawal, 0.0)
            paths[:, year] = np.round(balances).astype(np.int64)
        return paths

    def _depletion_year(self, path: np.ndarray) -> int | None:
        depleted = np.flatnonzero(path <= 0)
        if depleted.size == 0:
            return None
        return int(depleted[0] + 1)

    def _safe_withdrawal_rate(self, user_inputs: RetirementScenarioInput, seed: int) -> float:
        low = 0.0
        high = max(user_inputs.current_withdrawal_rate * 2.0, 0.20)
        for _ in range(18):
            midpoint = (low + high) / 2.0
            withdrawal_cents = int(round(user_inputs.current_portfolio_cents * midpoint))
            paths = self._simulate_paths(user_inputs, withdrawal_cents, seed)
            survival_probability = float(np.mean(paths[:, -1] > 0))
            if survival_probability >= _SAFE_WITHDRAWAL_TARGET:
                low = midpoint
            else:
                high = midpoint
        if low < 1e-6:
            return 0.0
        return low

    def _run_monte_carlo(
        self,
        user_inputs: RetirementScenarioInput,
        deterministic_path: np.ndarray,
        seed: int,
    ) -> RetirementMonteCarloSummary:
        paths = self._simulate_paths(user_inputs, user_inputs.net_annual_withdrawal_cents, seed)
        terminal = paths[:, -1]
        depletion_mask = paths <= 0
        depleted_any = np.any(depletion_mask, axis=1)
        depletion_years = np.where(depleted_any, np.argmax(depletion_mask, axis=1) + 1, 0)
        conditional_median_depletion_year = (
            int(np.median(depletion_years[depleted_any]))
            if np.any(depleted_any)
            else None
        )
        yearly_rows = tuple(
            RetirementYearProjectionRow(
                year=year + 1,
                deterministic_portfolio_cents=int(deterministic_path[year]),
                median_portfolio_cents=int(np.percentile(paths[:, year], 50)),
                p10_portfolio_cents=int(np.percentile(paths[:, year], 10)),
                p90_portfolio_cents=int(np.percentile(paths[:, year], 90)),
                cumulative_depletion_probability=float(np.mean(paths[:, year] <= 0)),
            )
            for year in range(user_inputs.retirement_years)
        )
        return RetirementMonteCarloSummary(
            scenario_count=self.assumptions.monte_carlo.scenario_count,
            probability_portfolio_survives=float(np.mean(terminal > 0)),
            safe_withdrawal_rate_95=self._safe_withdrawal_rate(user_inputs, seed),
            median_terminal_wealth_cents=int(np.percentile(terminal, 50)),
            p10_terminal_wealth_cents=int(np.percentile(terminal, 10)),
            p90_terminal_wealth_cents=int(np.percentile(terminal, 90)),
            conditional_median_depletion_year=conditional_median_depletion_year,
            yearly_rows=yearly_rows,
        )

    def _build_audit_trail(self, user_inputs: RetirementScenarioInput) -> list[AssumptionAuditItem]:
        trail = list(build_behavioral_audit_trail())
        trail.extend([
            AssumptionAuditItem(
                name="Expected portfolio return",
                parameter="expected_annual_return_rate",
                value=f"{user_inputs.expected_annual_return_rate * 100:.2f}%",
                source="User input",
            ),
            AssumptionAuditItem(
                name=f"Portfolio return volatility ({user_inputs.risk_profile.value} profile)",
                parameter="retirement_return_volatility",
                value=f"{self._volatility(user_inputs) * 100:.2f}%",
                source="Internal risk calibration; consistent with Vanguard and Morningstar historical portfolio return distributions",
                notes=(
                    "Annualized standard deviation applied to simulated portfolio returns. "
                    f"Uses the {user_inputs.risk_profile.value} risk profile "
                    f"with {user_inputs.loss_behavior.value.replace('_', ' ')} loss behavior."
                ),
            ),
            AssumptionAuditItem(
                name="Return autocorrelation",
                parameter="retirement_return_autocorrelation",
                value=round(self.assumptions.retirement_return_autocorrelation, 2),
                source="Retirement simulation calibration. AR(1) momentum parameter.",
                last_updated=date(2025, 1, 1),
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
        return trail

    def _build_warnings(
        self,
        user_inputs: RetirementScenarioInput,
        monte_carlo: RetirementMonteCarloSummary,
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        if monte_carlo.probability_portfolio_survives < 0.75:
            warnings.append(
                "The current withdrawal plan survives in fewer than 75% of simulated market paths."
            )
        if user_inputs.current_withdrawal_rate > monte_carlo.safe_withdrawal_rate_95:
            warnings.append(
                "Your current withdrawal rate is above the modeled 95% survival withdrawal rate."
            )
        if user_inputs.loss_behavior == LossBehavior.SELL_TO_CASH:
            warnings.append(
                "Expected returns were reduced to reflect likely selling after a severe market drawdown."
            )
        return tuple(warnings)
