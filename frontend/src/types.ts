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

export interface RetirementInputPayload {
  current_portfolio_cents: number;
  annual_spending_cents: number;
  annual_guaranteed_income_cents: number;
  retirement_years: number;
  expected_annual_return_rate: number;
  risk_profile: RiskProfile;
  loss_behavior: LossBehavior;
}

export interface AssumptionOverridesPayload {
  mortgage_rate?: number;
  property_tax_rate?: number;
  annual_home_insurance_cents?: number;
  annual_rent_growth_rate?: number;
  maintenance_rate?: number;
  selling_cost_rate?: number;
  annual_pmi_rate?: number;
  buyer_closing_cost_rate?: number;
}

export interface AnalyzeRequestPayload {
  input: RentVsBuyInputPayload;
  simulation_seed: number;
  assumption_overrides?: AssumptionOverridesPayload;
  assumptions_snapshot?: Record<string, unknown>;
  audit_trail_snapshot?: AuditTrailItem[];
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

export interface RetirementYearProjectionRow {
  year: number;
  deterministic_portfolio_cents: number;
  median_portfolio_cents: number;
  p10_portfolio_cents: number;
  p90_portfolio_cents: number;
  cumulative_depletion_probability: number;
}

export interface RetirementDeterministicSummary {
  net_annual_withdrawal_cents: number;
  current_withdrawal_rate: number;
  depletion_year: number | null;
  terminal_wealth_cents: number;
}

export interface RetirementMonteCarloSummary {
  scenario_count: number;
  probability_portfolio_survives: number;
  safe_withdrawal_rate_95: number;
  median_terminal_wealth_cents: number;
  p10_terminal_wealth_cents: number;
  p90_terminal_wealth_cents: number;
  conditional_median_depletion_year: number | null;
  yearly_rows: RetirementYearProjectionRow[];
}

export interface RetirementAnalysis {
  deterministic: RetirementDeterministicSummary;
  monte_carlo: RetirementMonteCarloSummary;
  audit_trail: AuditTrailItem[];
  warnings: string[];
}

export interface RetirementAnalysisEnvelope {
  model_version: string;
  disclaimer: string;
  analysis: RetirementAnalysis;
}

export interface ReportInputsSummaryRow {
  label: string;
  value: string;
}

export interface ReportAuditTrailRow {
  label: string;
  value: string | number | null;
  source: string;
  last_updated: string | null;
}

export interface ReportYearRow {
  year: number;
  rent_net_worth_cents: number;
  buy_net_worth_cents: number;
  difference_cents: number;
}

export interface ReportYearOneCosts {
  principal_and_interest_cents: number;
  property_tax_cents: number;
  insurance_cents: number;
  maintenance_cents: number;
  pmi_cents: number;
  liquidity_premium_cents: number;
  gross_annual_cents: number;
  gross_monthly_cents: number;
  mortgage_interest_tax_saving_cents: number;
  true_annual_cents: number;
  true_monthly_cents: number;
  current_rent_annual_cents: number;
  cash_difference_annual_cents: number;
}

export interface ReportHiddenFactors {
  initial_purchase_cash_cents: number;
  equity_after_sale_horizon_cents: number;
  closing_costs_cents: number;
  opportunity_cost_future_value_cents: number;
  actual_tax_saving_year_one_cents: number;
  hypothetical_itemized_year_one_cents: number;
  capital_gains: {
    estimated_gain_cents: number;
    exclusion_cents: number;
    capital_gains_tax_cents: number;
  };
}

export interface ReportSensitivityRow {
  label: string;
  break_even_month: number | null;
  break_even_label: string;
  probability_buy_beats_rent: number;
  probability_buy_beats_rent_label: string;
  probability_shift_points: number;
}

export interface ReportQuestions {
  timeline: {
    break_even_month: number | null;
    planned_horizon_months: number;
    margin_months: number | null;
  };
  liquidity: {
    remaining_savings_cents: number;
    buffer_threshold_cents: number;
  };
  risk: {
    warnings: string[];
  };
}

export interface ReportNarratives {
  verdict_driver: string;
  net_worth_summary: string;
  sensitivity_summary: string;
  question_timeline: string;
  question_liquidity: string;
  question_risk: string;
  summary: string;
}

export interface RentVsBuyReport {
  generated_at: string;
  model_version: string;
  disclaimer: string;
  winner: "buying" | "renting";
  verdict: {
    headline: string;
    winner_label: string;
    break_even_month: number | null;
    break_even_years: number | null;
    horizon_years: number;
    deterministic_advantage_cents: number;
    probability_buy_beats_rent: number;
    p10_terminal_advantage_cents: number;
    p90_terminal_advantage_cents: number;
  };
  inputs_summary: ReportInputsSummaryRow[];
  assumptions_summary: ReportInputsSummaryRow[];
  audit_trail: ReportAuditTrailRow[];
  yearly_net_worth: ReportYearRow[];
  year_one_costs: ReportYearOneCosts;
  hidden_factors: ReportHiddenFactors;
  sensitivity: {
    rows: ReportSensitivityRow[];
    most_sensitive_label: string;
    largest_probability_shift_points: number;
  };
  questions: ReportQuestions;
  narratives: ReportNarratives;
  narrative_source: "groq" | "template";
}

export interface ReportEnvelope {
  model_version: string;
  disclaimer: string;
  report: RentVsBuyReport;
}

export interface CurrentAssumptionsEnvelope {
  model_version: string;
  disclaimer: string;
  source: string;
  cache_date: string;
  assumptions: {
    model_version: string;
    mortgage_rate: number;
    property_tax_rate: number;
    annual_home_insurance_cents: number;
    annual_rent_growth_rate: number;
    maintenance_rate: number;
    selling_cost_rate: number;
    annual_pmi_rate: number;
    buyer_closing_cost_rate: number;
    monte_carlo: {
      annual_appreciation_mean: number;
      annual_rent_growth_mean: number;
      scenario_count: number;
    };
    behavioral: {
      stable_income_liquidity_premium: number;
      variable_income_liquidity_premium: number;
    };
  };
  audit_trail: AuditTrailItem[];
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

export interface AssumptionFormState {
  mortgageRate: string;
  propertyTaxRate: string;
  monthlyHomeInsurance: string;
  rentGrowthRate: string;
  maintenanceRate: string;
  sellerClosingRate: string;
  buyerClosingRate: string;
}

export interface RetirementFormState {
  currentPortfolio: string;
  annualSpending: string;
  annualGuaranteedIncome: string;
  retirementYears: string;
  expectedAnnualReturn: string;
  riskProfile: RiskProfile;
  lossBehavior: LossBehavior;
}
