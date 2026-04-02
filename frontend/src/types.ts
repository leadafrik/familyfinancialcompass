export type RiskProfile = "conservative" | "moderate" | "aggressive";
export type LossBehavior = "sell_to_cash" | "hold" | "buy_more";
export type IncomeStability = "stable" | "variable";
export type HousingStatus = "renting" | "owning";
export type FilingStatus = "single" | "married_filing_jointly";

export interface RentVsBuyInputPayload {
  target_home_price_cents: number;
  down_payment_cents: number;
  loan_term_years: 15 | 30;
  expected_years_in_home: number;
  current_monthly_rent_cents: number;
  annual_household_income_cents: number;
  current_savings_cents: number;
  monthly_savings_cents: number;
  expected_home_appreciation_rate: number;
  expected_investment_return_rate: number;
  risk_profile: RiskProfile;
  loss_behavior: LossBehavior;
  income_stability: IncomeStability;
  employment_tied_to_local_economy: boolean;
  current_housing_status: HousingStatus;
  market_region: string;
  marginal_tax_rate: number;
  itemizes_deductions: boolean;
  filing_status: FilingStatus;
}

export interface AnalyzeRequestPayload {
  input: RentVsBuyInputPayload;
  simulation_seed: number;
}

export interface CreateScenarioPayload extends AnalyzeRequestPayload {
  user_id: string;
  idempotency_key: string;
}

export interface CostBreakdown {
  principal_and_interest_cents: number;
  property_tax_cents: number;
  insurance_cents: number;
  maintenance_cents: number;
  pmi_cents: number;
  liquidity_premium_cents: number;
  closing_costs_cents: number;
  total_mortgage_interest_deduction_cents: number;
  capital_gains_tax_on_sale_cents: number;
  total_interest_paid_cents: number;
  total_cost_of_buying_cents: number;
}

export interface YearlyComparisonRow {
  year: number;
  rent_net_worth_cents: number;
  buy_net_worth_cents: number;
  buy_minus_rent_cents: number;
  home_equity_cents: number;
  rent_portfolio_cents: number;
  buy_liquid_portfolio_cents: number;
  home_value_cents: number;
  remaining_principal_cents: number;
  pmi_cents: number;
  total_buy_cost_cents: number;
}

export interface DeterministicSummary {
  break_even_month: number | null;
  end_of_horizon_advantage_cents: number;
  horizon_months: number;
  first_year_cost_breakdown: CostBreakdown;
  yearly_rows: YearlyComparisonRow[];
}

export interface MonteCarloSummary {
  scenario_count: number;
  probability_buy_beats_rent: number;
  probability_break_even_within_horizon: number;
  median_break_even_month: number | null;
  break_even_ci_80: [number | null, number | null];
  median_terminal_advantage_cents: number;
  p10_terminal_advantage_cents: number;
  p90_terminal_advantage_cents: number;
  utility_adjusted_p50_advantage_cents: number;
  probability_utility_positive: number;
}

export interface AuditTrailItem {
  parameter?: string | null;
  name?: string | null;
  value?: string | number | null;
  source: string;
  sourced_at?: string | null;
  last_updated?: string | null;
  notes?: string | null;
}

export interface CalibrationUsed {
  annual_appreciation_mean: number;
  annual_rent_growth_mean: number;
  scenario_count: number;
}

export interface RentVsBuyAnalysis {
  deterministic: DeterministicSummary;
  monte_carlo: MonteCarloSummary;
  audit_trail: AuditTrailItem[];
  warnings: string[];
  calibration_used?: CalibrationUsed | null;
}

export interface AnalysisEnvelope {
  model_version: string;
  disclaimer: string;
  analysis: RentVsBuyAnalysis;
}

export interface ScenarioEnvelope {
  scenario_id: string;
  user_id: string;
  created_at: string;
  computed_at: string;
  model_version: string;
  disclaimer: string;
  inputs_snapshot: Record<string, unknown>;
  assumptions_snapshot: Record<string, unknown>;
  analysis: RentVsBuyAnalysis;
}

export interface ScenarioListEnvelope {
  items: ScenarioEnvelope[];
  next_cursor: string | null;
}

export interface FormState {
  targetHomePrice: string;
  downPayment: string;
  loanTermYears: "15" | "30";
  expectedYearsInHome: string;
  monthlyRent: string;
  annualIncome: string;
  currentSavings: string;
  monthlySavings: string;
  appreciationRate: string;
  investmentReturnRate: string;
  riskProfile: RiskProfile;
  lossBehavior: LossBehavior;
  incomeStability: IncomeStability;
  employmentTiedToLocalEconomy: boolean;
  currentHousingStatus: HousingStatus;
  marketRegion: string;
  marginalTaxRate: string;
  itemizesDeductions: boolean;
  filingStatus: FilingStatus;
}
