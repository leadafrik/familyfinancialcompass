export type RiskProfile = "conservative" | "moderate" | "aggressive";
export type LossBehavior = "sell_to_cash" | "hold" | "buy_more";
export type IncomeStability = "stable" | "variable";
export type HousingStatus = "renting" | "owning";
export type FilingStatus = "single" | "married_filing_jointly";

export interface RentVsBuyInputPayload {
  target_home_price_cents: number;
  down_payment_cents: number;
  loan_term_years: 15 | 20 | 30;
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

export interface CollegeVsRetirementInputPayload {
  current_retirement_savings_cents: number;
  current_college_savings_cents: number;
  annual_savings_budget_cents: number;
  annual_college_cost_cents: number;
  years_until_college: number;
  years_in_college: number;
  retirement_years: number;
  expected_annual_return_rate: number;
  risk_profile: RiskProfile;
  loss_behavior: LossBehavior;
}

export interface JobOfferOfferPayload {
  label: string;
  base_salary_cents: number;
  target_bonus_cents: number;
  annual_equity_vesting_cents: number;
  sign_on_bonus_cents: number;
  relocation_cost_cents: number;
  annual_cost_of_living_delta_cents: number;
  annual_commute_cost_cents: number;
  annual_comp_growth_rate: number;
  annual_equity_growth_rate: number;
  bonus_payout_volatility: number;
  equity_volatility: number;
}

export interface JobOfferInputPayload {
  offer_a: JobOfferOfferPayload;
  offer_b: JobOfferOfferPayload;
  comparison_years: number;
  marginal_tax_rate: number;
  local_market_concentration: boolean;
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

export interface JobOfferYearComparisonRow {
  year: number;
  offer_a_annual_net_value_cents: number;
  offer_b_annual_net_value_cents: number;
  offer_a_cumulative_value_cents: number;
  offer_b_cumulative_value_cents: number;
  offer_b_minus_offer_a_cents: number;
}

export interface JobOfferDeterministicSummary {
  break_even_month: number | null;
  end_of_horizon_advantage_cents: number;
  yearly_rows: JobOfferYearComparisonRow[];
}

export interface JobOfferMonteCarloSummary {
  scenario_count: number;
  probability_offer_b_wins: number;
  probability_break_even_within_horizon: number;
  conditional_median_break_even_month: number | null;
  median_terminal_advantage_cents: number;
  p10_terminal_advantage_cents: number;
  p90_terminal_advantage_cents: number;
  utility_adjusted_p50_advantage_cents: number;
}

export interface JobOfferAnalysis {
  deterministic: JobOfferDeterministicSummary;
  monte_carlo: JobOfferMonteCarloSummary;
  audit_trail: AuditTrailItem[];
  warnings: string[];
}

export interface JobOfferAnalysisEnvelope {
  model_version: string;
  disclaimer: string;
  analysis: JobOfferAnalysis;
}

export interface CollegeVsRetirementYearComparisonRow {
  year: number;
  college_first_net_worth_cents: number;
  retirement_first_net_worth_cents: number;
  retirement_first_minus_college_first_cents: number;
  college_first_retirement_cents: number;
  retirement_first_retirement_cents: number;
  college_first_college_fund_cents: number;
  retirement_first_college_fund_cents: number;
  college_first_loan_balance_cents: number;
  retirement_first_loan_balance_cents: number;
}

export interface CollegeVsRetirementDeterministicSummary {
  break_even_year: number | null;
  end_of_horizon_advantage_cents: number;
  college_first_terminal_retirement_cents: number;
  retirement_first_terminal_retirement_cents: number;
  college_first_total_loan_cents: number;
  retirement_first_total_loan_cents: number;
  yearly_rows: CollegeVsRetirementYearComparisonRow[];
}

export interface CollegeVsRetirementMonteCarloSummary {
  scenario_count: number;
  probability_retirement_first_wins: number;
  probability_break_even_within_horizon: number;
  conditional_median_break_even_year: number | null;
  median_terminal_advantage_cents: number;
  p10_terminal_advantage_cents: number;
  p90_terminal_advantage_cents: number;
  median_retirement_first_terminal_retirement_cents: number;
  median_college_first_terminal_retirement_cents: number;
  utility_adjusted_p50_advantage_cents: number;
}

export interface CollegeVsRetirementAnalysis {
  deterministic: CollegeVsRetirementDeterministicSummary;
  monte_carlo: CollegeVsRetirementMonteCarloSummary;
  audit_trail: AuditTrailItem[];
  warnings: string[];
}

export interface CollegeVsRetirementAnalysisEnvelope {
  model_version: string;
  disclaimer: string;
  analysis: CollegeVsRetirementAnalysis;
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

export interface RetirementSurvivalReport {
  generated_at: string;
  model_version: string;
  disclaimer: string;
  verdict: {
    probability_portfolio_survives: number;
    safe_withdrawal_rate_95: number;
    deterministic_depletion_year: number | null;
    conditional_median_depletion_year: number | null;
    horizon_years: number;
  };
  inputs_summary: ReportInputsSummaryRow[];
  assumptions_summary: ReportInputsSummaryRow[];
  yearly_projection: Array<{
    year: number;
    deterministic_portfolio_cents: number;
    median_portfolio_cents: number;
    p10_portfolio_cents: number;
    p90_portfolio_cents: number;
    cumulative_depletion_probability: number;
  }>;
  wealth_at_horizon: {
    deterministic_terminal_wealth_cents: number;
    median_terminal_wealth_cents: number;
    p10_terminal_wealth_cents: number;
    p90_terminal_wealth_cents: number;
  };
  withdrawal_analysis: {
    current_withdrawal_rate: number;
    safe_withdrawal_rate_95: number;
    withdrawal_rate_gap: number;
    safe_withdrawal_annual_cents: number;
    safe_withdrawal_gap_cents: number;
    net_annual_withdrawal_cents: number;
  };
  audit_trail: ReportAuditTrailRow[];
  warnings: string[];
  narratives: {
    survival_verdict: string;
    withdrawal_rate_summary: string;
    wealth_range_summary: string;
    risk_summary: string;
    summary: string;
  };
  narrative_source: "groq" | "template";
}

export interface JobOfferReport {
  generated_at: string;
  model_version: string;
  disclaimer: string;
  verdict: {
    winner_label: string;
    break_even_month: number | null;
    probability_offer_b_wins: number;
    end_of_horizon_advantage_cents: number;
    utility_adjusted_advantage_cents: number;
  };
  offers: {
    offer_a_label: string;
    offer_b_label: string;
    offer_a_summary: ReportInputsSummaryRow[];
    offer_b_summary: ReportInputsSummaryRow[];
  };
  yearly_comparison: Array<{
    year: number;
    offer_a_annual_net_value_cents: number;
    offer_b_annual_net_value_cents: number;
    offer_a_cumulative_value_cents: number;
    offer_b_cumulative_value_cents: number;
    offer_b_minus_offer_a_cents: number;
  }>;
  risk: {
    p10_terminal_advantage_cents: number;
    median_terminal_advantage_cents: number;
    p90_terminal_advantage_cents: number;
    local_market_concentration: boolean;
    warnings: string[];
  };
  hidden_costs: {
    offer_a: {
      relocation_cost_cents: number;
      annual_cost_of_living_delta_cents: number;
      annual_commute_cost_cents: number;
      after_tax_sign_on_bonus_cents: number;
    };
    offer_b: {
      relocation_cost_cents: number;
      annual_cost_of_living_delta_cents: number;
      annual_commute_cost_cents: number;
      after_tax_sign_on_bonus_cents: number;
    };
    offer_b_minus_offer_a_first_year_friction_cents: number;
  };
  sensitivity: {
    rows: Array<{
      label: string;
      break_even_month: number | null;
      break_even_label: string;
      probability_offer_b_wins: number;
      probability_offer_b_wins_label: string;
      probability_shift_points: number;
    }>;
    most_sensitive_label: string;
    largest_probability_shift_points: number;
  };
  audit_trail: ReportAuditTrailRow[];
  narratives: {
    offer_comparison: string;
    break_even_summary: string;
    risk_summary: string;
    hidden_costs_summary: string;
    summary: string;
  };
  narrative_source: "groq" | "template";
}

export interface CollegeVsRetirementReport {
  generated_at: string;
  model_version: string;
  disclaimer: string;
  verdict: {
    winner_label: string;
    break_even_year: number | null;
    probability_retirement_first_wins: number;
    end_of_horizon_advantage_cents: number;
    utility_adjusted_advantage_cents: number;
  };
  inputs_summary: ReportInputsSummaryRow[];
  funding_analysis: {
    college_first_total_loan_cents: number;
    retirement_first_total_loan_cents: number;
    college_first_annual_loan_payment_cents: number;
    retirement_first_annual_loan_payment_cents: number;
    college_first_total_interest_cents: number;
    retirement_first_total_interest_cents: number;
  };
  retirement_outcomes: {
    college_first_terminal_retirement_cents: number;
    retirement_first_terminal_retirement_cents: number;
    median_retirement_first_terminal_retirement_cents: number;
    median_college_first_terminal_retirement_cents: number;
    p10_terminal_advantage_cents: number;
    p90_terminal_advantage_cents: number;
  };
  yearly_comparison: Array<{
    year: number;
    college_first_net_worth_cents: number;
    retirement_first_net_worth_cents: number;
    retirement_first_minus_college_first_cents: number;
    college_first_retirement_cents: number;
    retirement_first_retirement_cents: number;
    college_first_college_fund_cents: number;
    retirement_first_college_fund_cents: number;
    college_first_loan_balance_cents: number;
    retirement_first_loan_balance_cents: number;
  }>;
  warnings: string[];
  audit_trail: ReportAuditTrailRow[];
  narratives: {
    allocation_verdict: string;
    loan_impact_summary: string;
    retirement_outcome_summary: string;
    risk_summary: string;
    summary: string;
  };
  narrative_source: "groq" | "template";
}

export interface ReportEnvelope<TReport = RentVsBuyReport> {
  model_version: string;
  disclaimer: string;
  report: TReport;
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
  loanTermYears: "15" | "20" | "30";
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

export interface JobOfferFormSideState {
  label: string;
  baseSalary: string;
  targetBonus: string;
  annualEquityVesting: string;
  signOnBonus: string;
  relocationCost: string;
  annualCostOfLivingDelta: string;
  annualCommuteCost: string;
  annualCompGrowthRate: string;
  annualEquityGrowthRate: string;
  bonusPayoutVolatility: string;
  equityVolatility: string;
}

export interface JobOfferFormState {
  offerA: JobOfferFormSideState;
  offerB: JobOfferFormSideState;
  comparisonYears: string;
  marginalTaxRate: string;
  localMarketConcentration: boolean;
}

export interface CollegeVsRetirementFormState {
  currentRetirementSavings: string;
  currentCollegeSavings: string;
  annualSavingsBudget: string;
  annualCollegeCost: string;
  yearsUntilCollege: string;
  yearsInCollege: string;
  retirementYears: string;
  expectedAnnualReturn: string;
  riskProfile: RiskProfile;
  lossBehavior: LossBehavior;
}
