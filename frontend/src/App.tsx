import { startTransition, useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import {
  buildCollegeVsRetirementReport,
  buildJobOfferReport,
  buildRentVsBuyReport,
  buildRetirementSurvivalReport,
  getCurrentRentVsBuyAssumptions,
  saveRentVsBuyScenario,
} from "./api";
import type {
  AuditTrailItem,
  AssumptionFormState,
  AssumptionOverridesPayload,
  CollegeVsRetirementFormState,
  CollegeVsRetirementInputPayload,
  CollegeVsRetirementReport,
  CurrentAssumptionsEnvelope,
  CreateScenarioPayload,
  FormState,
  JobOfferFormSideState,
  JobOfferFormState,
  JobOfferInputPayload,
  JobOfferReport,
  ReportAuditTrailRow,
  ReportEnvelope,
  ReportInputsSummaryRow,
  ReportYearRow,
  RetirementFormState,
  RetirementInputPayload,
  RetirementSurvivalReport,
  RentVsBuyInputPayload,
  RentVsBuyReport,
} from "./types";

type LiveModuleId =
  | "rent-vs-buy"
  | "job-offer"
  | "retirement-survival"
  | "college-vs-retirement";

type ModuleId = LiveModuleId | "debt-payoff-vs-invest";
type ModulePhase = "input" | "result";
type LaunchOptions = {
  initialModule: ModuleId;
  embedMode: boolean;
};

const modules: Array<{
  id: ModuleId;
  label: string;
  status: "live" | "queued";
  description: string;
}> = [
  {
    id: "rent-vs-buy",
    label: "Rent vs Buy",
    status: "live",
    description: "Model the tradeoff between renting flexibility and building home equity.",
  },
  {
    id: "job-offer",
    label: "Job Offer",
    status: "live",
    description: "Compare the economics of staying put versus switching roles.",
  },
  {
    id: "retirement-survival",
    label: "Retirement Survival",
    status: "live",
    description: "Stress test whether your portfolio can support your spending plan.",
  },
  {
    id: "college-vs-retirement",
    label: "College vs Retirement",
    status: "live",
    description: "See what prioritizing one family goal costs the other.",
  },
  {
    id: "debt-payoff-vs-invest",
    label: "Debt vs Invest",
    status: "queued",
    description: "Next in line after the core family finance engines.",
  },
];

function isModuleId(value: string | null | undefined): value is ModuleId {
  return modules.some((module) => module.id === value);
}

function parseBooleanFlag(value: string | null | undefined): boolean | null {
  if (!value) {
    return null;
  }
  const normalized = value.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) {
    return true;
  }
  if (["0", "false", "no", "off"].includes(normalized)) {
    return false;
  }
  return null;
}

function normalizeConfiguredModule(value: string | undefined): ModuleId {
  return isModuleId(value) ? value : "rent-vs-buy";
}

function readLaunchOptions(): LaunchOptions {
  const configuredModule = normalizeConfiguredModule(import.meta.env.VITE_DEFAULT_MODULE);
  const configuredEmbedMode = parseBooleanFlag(import.meta.env.VITE_EMBED_MODE) ?? false;

  if (typeof window === "undefined") {
    return {
      initialModule: configuredModule,
      embedMode: configuredEmbedMode,
    };
  }

  const params = new URLSearchParams(window.location.search);
  const requestedModule = params.get("module");
  const requestedEmbedMode = parseBooleanFlag(params.get("embed"));

  return {
    initialModule: isModuleId(requestedModule) ? requestedModule : configuredModule,
    embedMode: requestedEmbedMode ?? configuredEmbedMode,
  };
}

const phaseLabels: Record<LiveModuleId, string[]> = {
  "rent-vs-buy": ["The home", "Your situation", "Your plans", "Tax & behavior"],
  "job-offer": ["Current role", "New role", "Timeline & tax", "Uncertainty"],
  "retirement-survival": ["Portfolio", "Spending", "Market behavior"],
  "college-vs-retirement": ["Balances", "College timeline", "Retirement plan", "Market behavior"],
};

const loadingMessages: Record<LiveModuleId, string[]> = {
  "rent-vs-buy": [
    "Calculating your housing cash flows...",
    "Running 10,000 market scenarios...",
    "Building your report...",
  ],
  "job-offer": [
    "Calculating after-tax compensation...",
    "Running 10,000 market scenarios...",
    "Building your report...",
  ],
  "retirement-survival": [
    "Projecting the base-case retirement path...",
    "Running 10,000 market scenarios...",
    "Building your report...",
  ],
  "college-vs-retirement": [
    "Projecting both funding strategies...",
    "Running 10,000 market scenarios...",
    "Building your report...",
  ],
};

const taxBracketOptions = [
  { value: "12", label: "12% · lower bracket" },
  { value: "22", label: "22% · middle income" },
  { value: "24", label: "24% · upper middle income" },
  { value: "32", label: "32% · high income" },
  { value: "35", label: "35% · very high income" },
];

const defaultRentForm: FormState = {
  targetHomePrice: "550000",
  downPayment: "110000",
  loanTermYears: "30",
  expectedYearsInHome: "7",
  monthlyRent: "2850",
  annualIncome: "210000",
  currentSavings: "150000",
  monthlySavings: "3500",
  appreciationRate: "3.5",
  investmentReturnRate: "7.0",
  riskProfile: "moderate",
  lossBehavior: "hold",
  incomeStability: "stable",
  employmentTiedToLocalEconomy: false,
  currentHousingStatus: "renting",
  marketRegion: "national",
  marginalTaxRate: "24",
  itemizesDeductions: false,
  filingStatus: "married_filing_jointly",
};

const defaultAssumptionForm: AssumptionFormState = {
  mortgageRate: "6.82",
  propertyTaxRate: "1.74",
  monthlyHomeInsurance: "200",
  rentGrowthRate: "3.2",
  maintenanceRate: "1.0",
  sellerClosingRate: "7.0",
  buyerClosingRate: "3.0",
};

const defaultJobOfferForm: JobOfferFormState = {
  offerA: {
    label: "Current role",
    baseSalary: "160000",
    targetBonus: "20000",
    annualEquityVesting: "0",
    signOnBonus: "0",
    relocationCost: "0",
    annualCostOfLivingDelta: "0",
    annualCommuteCost: "3000",
    annualCompGrowthRate: "3.0",
    annualEquityGrowthRate: "0.0",
    bonusPayoutVolatility: "10",
    equityVolatility: "0",
  },
  offerB: {
    label: "New role",
    baseSalary: "190000",
    targetBonus: "30000",
    annualEquityVesting: "25000",
    signOnBonus: "20000",
    relocationCost: "15000",
    annualCostOfLivingDelta: "18000",
    annualCommuteCost: "5000",
    annualCompGrowthRate: "3.5",
    annualEquityGrowthRate: "0.0",
    bonusPayoutVolatility: "25",
    equityVolatility: "60",
  },
  comparisonYears: "4",
  marginalTaxRate: "30",
  localMarketConcentration: true,
};

const defaultRetirementForm: RetirementFormState = {
  currentPortfolio: "1500000",
  annualSpending: "80000",
  annualGuaranteedIncome: "20000",
  retirementYears: "30",
  expectedAnnualReturn: "6.0",
  riskProfile: "moderate",
  lossBehavior: "hold",
};

const defaultCollegeForm: CollegeVsRetirementFormState = {
  currentRetirementSavings: "400000",
  currentCollegeSavings: "20000",
  annualSavingsBudget: "18000",
  annualCollegeCost: "35000",
  yearsUntilCollege: "8",
  yearsInCollege: "4",
  retirementYears: "18",
  expectedAnnualReturn: "6.0",
  riskProfile: "moderate",
  lossBehavior: "hold",
};

type AssumptionBaseline = {
  assumptionsSnapshot: Record<string, unknown>;
  auditTrailSnapshot: AuditTrailItem[];
  assumptionForm: AssumptionFormState;
};

function dollarsToCents(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
}

function percentToRate(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed / 100 : 0;
}

function centsToMonthlyDollars(cents: number): string {
  return String(Math.round(cents / 1200));
}

function rateToPercentString(value: number, digits = 2): string {
  return (value * 100).toFixed(digits);
}

function formatCurrency(cents: number): string {
  const sign = cents < 0 ? "−" : "";
  return `${sign}$${(Math.abs(cents) / 100).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

function formatCompactCurrency(cents: number): string {
  const sign = cents < 0 ? "−" : "";
  return `${sign}$${(Math.abs(cents) / 100).toLocaleString("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  })}`;
}

function formatPercent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

function formatDate(value: string | null): string {
  if (!value) {
    return "Unknown";
  }
  return new Date(value).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatMonthLabel(month: number | null): string {
  return month === null ? "No break-even in horizon" : `Month ${month}`;
}

function formatYearLabel(year: number | null): string {
  return year === null ? "No break-even in horizon" : `Year ${year}`;
}

function buildRentPayload(form: FormState): RentVsBuyInputPayload {
  return {
    target_home_price_cents: dollarsToCents(form.targetHomePrice),
    down_payment_cents: dollarsToCents(form.downPayment),
    loan_term_years: Number(form.loanTermYears) as 15 | 20 | 30,
    expected_years_in_home: Number(form.expectedYearsInHome),
    current_monthly_rent_cents: dollarsToCents(form.monthlyRent),
    annual_household_income_cents: dollarsToCents(form.annualIncome),
    current_savings_cents: dollarsToCents(form.currentSavings),
    monthly_savings_cents: dollarsToCents(form.monthlySavings),
    expected_home_appreciation_rate: percentToRate(form.appreciationRate),
    expected_investment_return_rate: percentToRate(form.investmentReturnRate),
    risk_profile: form.riskProfile,
    loss_behavior: form.lossBehavior,
    income_stability: form.incomeStability,
    employment_tied_to_local_economy: form.employmentTiedToLocalEconomy,
    current_housing_status: form.currentHousingStatus,
    market_region: form.marketRegion,
    marginal_tax_rate: percentToRate(form.marginalTaxRate),
    itemizes_deductions: form.itemizesDeductions,
    filing_status: form.filingStatus,
  };
}

function buildRetirementPayload(form: RetirementFormState): RetirementInputPayload {
  return {
    current_portfolio_cents: dollarsToCents(form.currentPortfolio),
    annual_spending_cents: dollarsToCents(form.annualSpending),
    annual_guaranteed_income_cents: dollarsToCents(form.annualGuaranteedIncome),
    retirement_years: Number(form.retirementYears),
    expected_annual_return_rate: percentToRate(form.expectedAnnualReturn),
    risk_profile: form.riskProfile,
    loss_behavior: form.lossBehavior,
  };
}

function buildJobOfferSidePayload(form: JobOfferFormSideState) {
  return {
    label: form.label,
    base_salary_cents: dollarsToCents(form.baseSalary),
    target_bonus_cents: dollarsToCents(form.targetBonus),
    annual_equity_vesting_cents: dollarsToCents(form.annualEquityVesting),
    sign_on_bonus_cents: dollarsToCents(form.signOnBonus),
    relocation_cost_cents: dollarsToCents(form.relocationCost),
    annual_cost_of_living_delta_cents: dollarsToCents(form.annualCostOfLivingDelta),
    annual_commute_cost_cents: dollarsToCents(form.annualCommuteCost),
    annual_comp_growth_rate: percentToRate(form.annualCompGrowthRate),
    annual_equity_growth_rate: percentToRate(form.annualEquityGrowthRate),
    bonus_payout_volatility: percentToRate(form.bonusPayoutVolatility),
    equity_volatility: percentToRate(form.equityVolatility),
  };
}

function buildJobOfferPayload(form: JobOfferFormState): JobOfferInputPayload {
  return {
    offer_a: buildJobOfferSidePayload(form.offerA),
    offer_b: buildJobOfferSidePayload(form.offerB),
    comparison_years: Number(form.comparisonYears),
    marginal_tax_rate: percentToRate(form.marginalTaxRate),
    local_market_concentration: form.localMarketConcentration,
  };
}

function buildCollegePayload(form: CollegeVsRetirementFormState): CollegeVsRetirementInputPayload {
  return {
    current_retirement_savings_cents: dollarsToCents(form.currentRetirementSavings),
    current_college_savings_cents: dollarsToCents(form.currentCollegeSavings),
    annual_savings_budget_cents: dollarsToCents(form.annualSavingsBudget),
    annual_college_cost_cents: dollarsToCents(form.annualCollegeCost),
    years_until_college: Number(form.yearsUntilCollege),
    years_in_college: Number(form.yearsInCollege),
    retirement_years: Number(form.retirementYears),
    expected_annual_return_rate: percentToRate(form.expectedAnnualReturn),
    risk_profile: form.riskProfile,
    loss_behavior: form.lossBehavior,
  };
}

function snapshotToAssumptionForm(snapshot: Record<string, unknown>): AssumptionFormState {
  return {
    mortgageRate: rateToPercentString(Number(snapshot.mortgage_rate ?? 0), 2),
    propertyTaxRate: rateToPercentString(Number(snapshot.property_tax_rate ?? 0), 2),
    monthlyHomeInsurance: centsToMonthlyDollars(Number(snapshot.annual_home_insurance_cents ?? 0)),
    rentGrowthRate: rateToPercentString(Number(snapshot.annual_rent_growth_rate ?? 0), 2),
    maintenanceRate: rateToPercentString(Number(snapshot.maintenance_rate ?? 0), 2),
    sellerClosingRate: rateToPercentString(Number(snapshot.selling_cost_rate ?? 0), 2),
    buyerClosingRate: rateToPercentString(Number(snapshot.buyer_closing_cost_rate ?? 0), 2),
  };
}

function currentAssumptionsToBaseline(payload: CurrentAssumptionsEnvelope): AssumptionBaseline {
  return {
    assumptionsSnapshot: payload.assumptions as unknown as Record<string, unknown>,
    auditTrailSnapshot: payload.audit_trail.map((item) => ({ ...item })),
    assumptionForm: snapshotToAssumptionForm(payload.assumptions as unknown as Record<string, unknown>),
  };
}

function buildAssumptionOverrides(
  form: AssumptionFormState,
  baseline: AssumptionBaseline | null,
): AssumptionOverridesPayload | undefined {
  const candidate: AssumptionOverridesPayload = {
    mortgage_rate: percentToRate(form.mortgageRate),
    property_tax_rate: percentToRate(form.propertyTaxRate),
    annual_home_insurance_cents: dollarsToCents(form.monthlyHomeInsurance) * 12,
    annual_rent_growth_rate: percentToRate(form.rentGrowthRate),
    maintenance_rate: percentToRate(form.maintenanceRate),
    selling_cost_rate: percentToRate(form.sellerClosingRate),
    buyer_closing_cost_rate: percentToRate(form.buyerClosingRate),
  };
  if (!baseline) {
    return candidate;
  }

  const baselineCandidate: AssumptionOverridesPayload = {
    mortgage_rate: percentToRate(baseline.assumptionForm.mortgageRate),
    property_tax_rate: percentToRate(baseline.assumptionForm.propertyTaxRate),
    annual_home_insurance_cents: dollarsToCents(baseline.assumptionForm.monthlyHomeInsurance) * 12,
    annual_rent_growth_rate: percentToRate(baseline.assumptionForm.rentGrowthRate),
    maintenance_rate: percentToRate(baseline.assumptionForm.maintenanceRate),
    selling_cost_rate: percentToRate(baseline.assumptionForm.sellerClosingRate),
    buyer_closing_cost_rate: percentToRate(baseline.assumptionForm.buyerClosingRate),
  };

  const overrides = Object.fromEntries(
    Object.entries(candidate).filter(
      ([key, value]) => baselineCandidate[key as keyof AssumptionOverridesPayload] !== value,
    ),
  ) as AssumptionOverridesPayload;
  return Object.keys(overrides).length > 0 ? overrides : undefined;
}

function buildRentReportRequest(
  form: FormState,
  assumptionForm: AssumptionFormState,
  baseline: AssumptionBaseline | null,
) {
  const payload: {
    input: RentVsBuyInputPayload;
    simulation_seed: number;
    assumption_overrides?: AssumptionOverridesPayload;
    assumptions_snapshot?: Record<string, unknown>;
    audit_trail_snapshot?: AuditTrailItem[];
  } = {
    input: buildRentPayload(form),
    simulation_seed: 7,
  };
  const overrides = buildAssumptionOverrides(assumptionForm, baseline);
  if (overrides) {
    payload.assumption_overrides = overrides;
  }
  if (baseline) {
    payload.assumptions_snapshot = baseline.assumptionsSnapshot;
    payload.audit_trail_snapshot = baseline.auditTrailSnapshot;
  }
  return payload;
}

function buildScenarioPayload(
  form: FormState,
  assumptionForm: AssumptionFormState,
  baseline: AssumptionBaseline | null,
): CreateScenarioPayload {
  return {
    ...buildRentReportRequest(form, assumptionForm, baseline),
    user_id: "anonymous",
    idempotency_key: crypto.randomUUID(),
  };
}

function estimatePmiMessage(
  form: FormState,
  assumptions: CurrentAssumptionsEnvelope | null,
): string | null {
  const homePrice = dollarsToCents(form.targetHomePrice);
  const downPayment = dollarsToCents(form.downPayment);
  if (!homePrice || downPayment / homePrice >= 0.2) {
    return null;
  }
  const annualPmiRate = Number(assumptions?.assumptions.annual_pmi_rate ?? 0.01);
  const monthly = Math.round(((homePrice - downPayment) * annualPmiRate) / 12 / 100);
  return `PMI will likely apply and adds about $${monthly.toLocaleString("en-US")}/month until you reach 20% equity.`;
}

function buildLinePath(points: Array<{ x: number; y: number }>): string {
  return points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
}

function normalizePoints(values: number[], width: number, height: number, min: number, max: number) {
  const spread = max - min || 1;
  return values.map((value, index) => ({
    x: values.length === 1 ? width / 2 : (index / (values.length - 1)) * width,
    y: height - ((value - min) / spread) * height,
  }));
}

function buildBandPath(
  lower: Array<{ x: number; y: number }>,
  upper: Array<{ x: number; y: number }>,
): string {
  const forward = upper.map((point) => `${point.x} ${point.y}`).join(" L ");
  const backward = [...lower].reverse().map((point) => `${point.x} ${point.y}`).join(" L ");
  return `M ${forward} L ${backward} Z`;
}

function revokeObjectUrlLater(url: string): void {
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  revokeObjectUrlLater(url);
}

function openBlobPreview(blob: Blob, previewWindow?: Window | null): void {
  const url = URL.createObjectURL(blob);
  if (previewWindow && !previewWindow.closed) {
    previewWindow.location.href = url;
    previewWindow.focus?.();
  } else {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  }
  revokeObjectUrlLater(url);
}

export default function App() {
  const launchOptions = useMemo(() => readLaunchOptions(), []);
  const [activeModule, setActiveModule] = useState<ModuleId>(launchOptions.initialModule);
  const [phases, setPhases] = useState<Record<LiveModuleId, ModulePhase>>({
    "rent-vs-buy": "input",
    "job-offer": "input",
    "retirement-survival": "input",
    "college-vs-retirement": "input",
  });
  const [steps, setSteps] = useState<Record<LiveModuleId, number>>({
    "rent-vs-buy": 0,
    "job-offer": 0,
    "retirement-survival": 0,
    "college-vs-retirement": 0,
  });

  const [rentForm, setRentForm] = useState<FormState>(defaultRentForm);
  const [assumptionForm, setAssumptionForm] = useState<AssumptionFormState>(defaultAssumptionForm);
  const [jobOfferForm, setJobOfferForm] = useState<JobOfferFormState>(defaultJobOfferForm);
  const [retirementForm, setRetirementForm] = useState<RetirementFormState>(defaultRetirementForm);
  const [collegeForm, setCollegeForm] = useState<CollegeVsRetirementFormState>(defaultCollegeForm);

  const [currentAssumptions, setCurrentAssumptions] = useState<CurrentAssumptionsEnvelope | null>(null);
  const [assumptionError, setAssumptionError] = useState<string | null>(null);

  const [rentReportEnvelope, setRentReportEnvelope] = useState<ReportEnvelope<RentVsBuyReport> | null>(null);
  const [jobOfferReportEnvelope, setJobOfferReportEnvelope] = useState<ReportEnvelope<JobOfferReport> | null>(null);
  const [retirementReportEnvelope, setRetirementReportEnvelope] = useState<ReportEnvelope<RetirementSurvivalReport> | null>(null);
  const [collegeReportEnvelope, setCollegeReportEnvelope] = useState<ReportEnvelope<CollegeVsRetirementReport> | null>(null);

  const [isLoading, setIsLoading] = useState(false);
  const [loadingIndex, setLoadingIndex] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);
  const [auditSheet, setAuditSheet] = useState<{ title: string; rows: ReportAuditTrailRow[] } | null>(null);

  const activeLiveModule = activeModule === "debt-payoff-vs-invest" ? null : activeModule;
  const activeMeta = modules.find((module) => module.id === activeModule)!;
  const activePhase = activeLiveModule ? phases[activeLiveModule] : "input";
  const activeStep = activeLiveModule ? steps[activeLiveModule] : 0;
  const activeLoadingMessages = activeLiveModule ? loadingMessages[activeLiveModule] : [];
  const isEmbedMode = launchOptions.embedMode;
  const currentBaseline = useMemo(
    () => (currentAssumptions ? currentAssumptionsToBaseline(currentAssumptions) : null),
    [currentAssumptions],
  );
  const pmiMessage = useMemo(() => estimatePmiMessage(rentForm, currentAssumptions), [rentForm, currentAssumptions]);

  useEffect(() => {
    let active = true;
    getCurrentRentVsBuyAssumptions()
      .then((payload) => {
        if (!active) {
          return;
        }
        startTransition(() => {
          setCurrentAssumptions(payload);
          setAssumptionForm(currentAssumptionsToBaseline(payload).assumptionForm);
        });
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setAssumptionError(
          "We couldn't fetch the latest mortgage rate. Results use our last known defaults until the live feed responds.",
        );
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!isLoading || !activeLiveModule) {
      setLoadingIndex(0);
      return;
    }
    setLoadingIndex(0);
    const interval = window.setInterval(() => {
      setLoadingIndex((current) => Math.min(current + 1, loadingMessages[activeLiveModule].length - 1));
    }, 800);
    return () => window.clearInterval(interval);
  }, [activeLiveModule, isLoading]);

  function setPhase(module: LiveModuleId, phase: ModulePhase): void {
    setPhases((current) => ({ ...current, [module]: phase }));
  }

  function setStep(module: LiveModuleId, step: number): void {
    setSteps((current) => ({ ...current, [module]: step }));
  }

  async function handleRunRentVsBuy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setSaveMessage(null);
    setIsLoading(true);
    try {
      const report = await buildRentVsBuyReport(buildRentReportRequest(rentForm, assumptionForm, currentBaseline));
      startTransition(() => {
        setRentReportEnvelope(report);
        setPhase("rent-vs-buy", "result");
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "We couldn't run the housing analysis.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleRunJobOffer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setIsLoading(true);
    try {
      const report = await buildJobOfferReport({
        input: buildJobOfferPayload(jobOfferForm),
        simulation_seed: 7,
      });
      startTransition(() => {
        setJobOfferReportEnvelope(report);
        setPhase("job-offer", "result");
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "We couldn't compare the offers.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleRunRetirement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setIsLoading(true);
    try {
      const report = await buildRetirementSurvivalReport({
        input: buildRetirementPayload(retirementForm),
        simulation_seed: 7,
      });
      startTransition(() => {
        setRetirementReportEnvelope(report);
        setPhase("retirement-survival", "result");
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "We couldn't run the retirement analysis.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleRunCollege(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setIsLoading(true);
    try {
      const report = await buildCollegeVsRetirementReport({
        input: buildCollegePayload(collegeForm),
        simulation_seed: 7,
      });
      startTransition(() => {
        setCollegeReportEnvelope(report);
        setPhase("college-vs-retirement", "result");
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "We couldn't compare the two family goals.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSaveRentAnalysis() {
    setSaveMessage(null);
    setIsSaving(true);
    try {
      await saveRentVsBuyScenario(buildScenarioPayload(rentForm, assumptionForm, currentBaseline));
      setSaveMessage("Analysis saved. You can come back to this housing scenario later.");
    } catch (error) {
      setSaveMessage(error instanceof Error ? error.message : "We couldn't save this analysis.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDownloadRentPdf() {
    if (!rentReportEnvelope) {
      return;
    }
    setIsGeneratingPdf(true);
    try {
      const [{ pdf }, { RentVsBuyReportDocument }] = await Promise.all([
        import("@react-pdf/renderer"),
        import("./ReportDocument"),
      ]);
      const blob = await pdf(<RentVsBuyReportDocument report={rentReportEnvelope.report} />).toBlob();
      downloadBlob(blob, `family-financial-compass-${new Date().toISOString().slice(0, 10)}.pdf`);
    } catch (error) {
      setSaveMessage(error instanceof Error ? error.message : "We couldn't generate the PDF.");
    } finally {
      setIsGeneratingPdf(false);
    }
  }

  async function handleOpenRentPrintPdf() {
    if (!rentReportEnvelope) {
      return;
    }
    const previewWindow = window.open("", "_blank");
    setIsGeneratingPdf(true);
    try {
      const [{ pdf }, { RentVsBuyReportDocument }] = await Promise.all([
        import("@react-pdf/renderer"),
        import("./ReportDocument"),
      ]);
      const blob = await pdf(<RentVsBuyReportDocument report={rentReportEnvelope.report} />).toBlob();
      openBlobPreview(blob, previewWindow);
    } catch (error) {
      previewWindow?.close();
      setSaveMessage(error instanceof Error ? error.message : "We couldn't open the printable PDF.");
    } finally {
      setIsGeneratingPdf(false);
    }
  }

  async function handleDownloadJobOfferPdf() {
    if (!jobOfferReportEnvelope) {
      return;
    }
    setIsGeneratingPdf(true);
    try {
      const [{ pdf }, { JobOfferReportDocument }] = await Promise.all([
        import("@react-pdf/renderer"),
        import("./ReportDocument"),
      ]);
      const blob = await pdf(
        <JobOfferReportDocument report={jobOfferReportEnvelope.report} />,
      ).toBlob();
      downloadBlob(blob, `family-financial-compass-job-offer-${new Date().toISOString().slice(0, 10)}.pdf`);
    } catch (error) {
      setSaveMessage(error instanceof Error ? error.message : "We couldn't generate the PDF.");
    } finally {
      setIsGeneratingPdf(false);
    }
  }

  async function handleOpenJobOfferPrintPdf() {
    if (!jobOfferReportEnvelope) {
      return;
    }
    const previewWindow = window.open("", "_blank");
    setIsGeneratingPdf(true);
    try {
      const [{ pdf }, { JobOfferReportDocument }] = await Promise.all([
        import("@react-pdf/renderer"),
        import("./ReportDocument"),
      ]);
      const blob = await pdf(
        <JobOfferReportDocument report={jobOfferReportEnvelope.report} />,
      ).toBlob();
      openBlobPreview(blob, previewWindow);
    } catch (error) {
      previewWindow?.close();
      setSaveMessage(error instanceof Error ? error.message : "We couldn't open the printable PDF.");
    } finally {
      setIsGeneratingPdf(false);
    }
  }

  async function handleDownloadRetirementPdf() {
    if (!retirementReportEnvelope) {
      return;
    }
    setIsGeneratingPdf(true);
    try {
      const [{ pdf }, { RetirementSurvivalReportDocument }] = await Promise.all([
        import("@react-pdf/renderer"),
        import("./ReportDocument"),
      ]);
      const blob = await pdf(
        <RetirementSurvivalReportDocument report={retirementReportEnvelope.report} />,
      ).toBlob();
      downloadBlob(blob, `family-financial-compass-retirement-${new Date().toISOString().slice(0, 10)}.pdf`);
    } catch (error) {
      setSaveMessage(error instanceof Error ? error.message : "We couldn't generate the PDF.");
    } finally {
      setIsGeneratingPdf(false);
    }
  }

  async function handleOpenRetirementPrintPdf() {
    if (!retirementReportEnvelope) {
      return;
    }
    const previewWindow = window.open("", "_blank");
    setIsGeneratingPdf(true);
    try {
      const [{ pdf }, { RetirementSurvivalReportDocument }] = await Promise.all([
        import("@react-pdf/renderer"),
        import("./ReportDocument"),
      ]);
      const blob = await pdf(
        <RetirementSurvivalReportDocument report={retirementReportEnvelope.report} />,
      ).toBlob();
      openBlobPreview(blob, previewWindow);
    } catch (error) {
      previewWindow?.close();
      setSaveMessage(error instanceof Error ? error.message : "We couldn't open the printable PDF.");
    } finally {
      setIsGeneratingPdf(false);
    }
  }

  async function handleDownloadCollegePdf() {
    if (!collegeReportEnvelope) {
      return;
    }
    setIsGeneratingPdf(true);
    try {
      const [{ pdf }, { CollegeVsRetirementReportDocument }] = await Promise.all([
        import("@react-pdf/renderer"),
        import("./ReportDocument"),
      ]);
      const blob = await pdf(
        <CollegeVsRetirementReportDocument report={collegeReportEnvelope.report} />,
      ).toBlob();
      downloadBlob(blob, `family-financial-compass-college-${new Date().toISOString().slice(0, 10)}.pdf`);
    } catch (error) {
      setSaveMessage(error instanceof Error ? error.message : "We couldn't generate the PDF.");
    } finally {
      setIsGeneratingPdf(false);
    }
  }

  async function handleOpenCollegePrintPdf() {
    if (!collegeReportEnvelope) {
      return;
    }
    const previewWindow = window.open("", "_blank");
    setIsGeneratingPdf(true);
    try {
      const [{ pdf }, { CollegeVsRetirementReportDocument }] = await Promise.all([
        import("@react-pdf/renderer"),
        import("./ReportDocument"),
      ]);
      const blob = await pdf(
        <CollegeVsRetirementReportDocument report={collegeReportEnvelope.report} />,
      ).toBlob();
      openBlobPreview(blob, previewWindow);
    } catch (error) {
      previewWindow?.close();
      setSaveMessage(error instanceof Error ? error.message : "We couldn't open the printable PDF.");
    } finally {
      setIsGeneratingPdf(false);
    }
  }

  function openAuditSheet(title: string, rows: ReportAuditTrailRow[]) {
    setAuditSheet({ title, rows });
  }

  function renderInputPhase() {
    if (!activeLiveModule) {
      return (
        <section className="panel panel--placeholder">
          <span className="section-kicker">Queued engine</span>
          <h2>{activeMeta.label}</h2>
          <p>{activeMeta.description}</p>
          <p className="muted-block">
            The core family-finance suite is complete. This module stays out of the way until it
            earns its place.
          </p>
        </section>
      );
    }

    switch (activeLiveModule) {
      case "rent-vs-buy":
        return (
          <form className="panel" onSubmit={handleRunRentVsBuy}>
            <PhaseRail currentPhase="input" step={activeStep} steps={phaseLabels["rent-vs-buy"]} />
            <header className="panel-header">
              <span className="section-kicker">Phase 1 · Input</span>
              <h2>Rent vs buy</h2>
              <p>
                Answer only the questions that materially move the model. Everything else uses
                sourced defaults you can inspect.
              </p>
            </header>
            {activeStep === 0 && (
              <div className="step-layout">
                <FieldGroup title="The home" description="Start with the purchase itself.">
                  <CurrencyField
                    label="Target home price"
                    value={rentForm.targetHomePrice}
                    onChange={(value) =>
                      setRentForm((current) => ({ ...current, targetHomePrice: value }))
                    }
                  />
                  <CurrencyField
                    label="Down payment"
                    value={rentForm.downPayment}
                    onChange={(value) =>
                      setRentForm((current) => ({ ...current, downPayment: value }))
                    }
                    hint={pmiMessage ?? undefined}
                  />
                  <SegmentedField
                    label="Loan term"
                    value={rentForm.loanTermYears}
                    onChange={(value) =>
                      setRentForm((current) => ({ ...current, loanTermYears: value as "15" | "20" | "30" }))
                    }
                    options={[
                      { value: "15", label: "15 years" },
                      { value: "20", label: "20 years" },
                      { value: "30", label: "30 years" },
                    ]}
                    hint="The current model supports standard 15-year, 20-year, and 30-year fixed terms."
                  />
                </FieldGroup>
              </div>
            )}
            {activeStep === 1 && (
              <div className="step-layout">
                <FieldGroup
                  title="Your situation"
                  description="Focus on rent, income, and available cash."
                >
                  <CurrencyField
                    label="Current monthly rent"
                    value={rentForm.monthlyRent}
                    onChange={(value) => setRentForm((current) => ({ ...current, monthlyRent: value }))}
                    suffix="/mo"
                  />
                  <CurrencyField
                    label="Annual household income"
                    value={rentForm.annualIncome}
                    onChange={(value) => setRentForm((current) => ({ ...current, annualIncome: value }))}
                  />
                  <CurrencyField
                    label="Current savings"
                    value={rentForm.currentSavings}
                    onChange={(value) => setRentForm((current) => ({ ...current, currentSavings: value }))}
                  />
                  <CurrencyField
                    label="Monthly savings you can contribute"
                    value={rentForm.monthlySavings}
                    onChange={(value) => setRentForm((current) => ({ ...current, monthlySavings: value }))}
                    suffix="/mo"
                  />
                </FieldGroup>
              </div>
            )}
            {activeStep === 2 && (
              <div className="step-layout">
                <FieldGroup
                  title="Your plans"
                  description="This is where the time horizon and expected returns matter most."
                >
                  <SliderField
                    label="How many years do you plan to stay?"
                    min={1}
                    max={15}
                    step={1}
                    value={rentForm.expectedYearsInHome}
                    onChange={(value) =>
                      setRentForm((current) => ({ ...current, expectedYearsInHome: value }))
                    }
                    display={`${rentForm.expectedYearsInHome} years`}
                  />
                  <PresetField
                    label="Expected home appreciation"
                    value={rentForm.appreciationRate}
                    onChange={(value) =>
                      setRentForm((current) => ({ ...current, appreciationRate: value }))
                    }
                    presets={[
                      { label: "Conservative · 2%", value: "2.0" },
                      { label: "Moderate · 3.5%", value: "3.5" },
                      { label: "Optimistic · 5%", value: "5.0" },
                    ]}
                    suffix="% / yr"
                  />
                  <PresetField
                    label="Investment return if you rent"
                    value={rentForm.investmentReturnRate}
                    onChange={(value) =>
                      setRentForm((current) => ({ ...current, investmentReturnRate: value }))
                    }
                    presets={[
                      { label: "Conservative · 5%", value: "5.0" },
                      { label: "Moderate · 7%", value: "7.0" },
                      { label: "Aggressive · 9%", value: "9.0" },
                    ]}
                    suffix="% / yr"
                  />
                </FieldGroup>
              </div>
            )}
            {activeStep === 3 && (
              <div className="step-layout">
                <FieldGroup
                  title="Tax and behavior"
                  description="The model stays descriptive, but these choices change the economics."
                >
                  <SelectField
                    label="Marginal tax rate"
                    value={rentForm.marginalTaxRate}
                    onChange={(value) =>
                      setRentForm((current) => ({ ...current, marginalTaxRate: value }))
                    }
                    options={taxBracketOptions}
                  />
                  <SegmentedField
                    label="Filing status"
                    value={rentForm.filingStatus}
                    onChange={(value) =>
                      setRentForm((current) => ({
                        ...current,
                        filingStatus: value as FormState["filingStatus"],
                      }))
                    }
                    options={[
                      { value: "single", label: "Single" },
                      { value: "married_filing_jointly", label: "Married" },
                    ]}
                  />
                  <SegmentedField
                    label="Do you itemize deductions?"
                    value={rentForm.itemizesDeductions ? "yes" : "no"}
                    onChange={(value) =>
                      setRentForm((current) => ({ ...current, itemizesDeductions: value === "yes" }))
                    }
                    options={[
                      { value: "no", label: "No" },
                      { value: "yes", label: "Yes" },
                    ]}
                  />
                  <SegmentedField
                    label="If markets dropped 30%"
                    value={rentForm.lossBehavior}
                    onChange={(value) =>
                      setRentForm((current) => ({
                        ...current,
                        lossBehavior: value as FormState["lossBehavior"],
                      }))
                    }
                    options={[
                      { value: "hold", label: "Hold" },
                      { value: "sell_to_cash", label: "Sell" },
                      { value: "buy_more", label: "Buy more" },
                    ]}
                  />
                  <SegmentedField
                    label="Is your job tied to the local economy?"
                    value={rentForm.employmentTiedToLocalEconomy ? "yes" : "no"}
                    onChange={(value) =>
                      setRentForm((current) => ({
                        ...current,
                        employmentTiedToLocalEconomy: value === "yes",
                      }))
                    }
                    options={[
                      { value: "no", label: "No" },
                      { value: "yes", label: "Yes" },
                    ]}
                  />
                  <SegmentedField
                    label="Market region"
                    value={rentForm.marketRegion}
                    onChange={(value) => setRentForm((current) => ({ ...current, marketRegion: value }))}
                    options={[
                      { value: "national", label: "National" },
                      { value: "coastal_high_cost", label: "Coastal" },
                      { value: "midwest_stable", label: "Midwest" },
                      { value: "sunbelt_growth", label: "Sunbelt" },
                    ]}
                  />
                </FieldGroup>

                <FieldGroup
                  title="Live assumptions"
                  description="Defaults are fetched daily. You can still test a different housing scenario before you run it."
                >
                  {assumptionError && <InlineNotice tone="warning">{assumptionError}</InlineNotice>}
                  {currentAssumptions && (
                    <InlineNotice tone="muted">
                      Using {currentAssumptions.source} data last cached on{" "}
                      {formatDate(currentAssumptions.cache_date)}.
                    </InlineNotice>
                  )}
                  <SliderField
                    label="Mortgage rate"
                    min={3}
                    max={10}
                    step={0.01}
                    value={assumptionForm.mortgageRate}
                    onChange={(value) =>
                      setAssumptionForm((current) => ({ ...current, mortgageRate: value }))
                    }
                    display={`${assumptionForm.mortgageRate}%`}
                  />
                  <SliderField
                    label="Rent growth"
                    min={0}
                    max={8}
                    step={0.1}
                    value={assumptionForm.rentGrowthRate}
                    onChange={(value) =>
                      setAssumptionForm((current) => ({ ...current, rentGrowthRate: value }))
                    }
                    display={`${assumptionForm.rentGrowthRate}% / yr`}
                  />
                  <SliderField
                    label="Property tax"
                    min={0}
                    max={4}
                    step={0.01}
                    value={assumptionForm.propertyTaxRate}
                    onChange={(value) =>
                      setAssumptionForm((current) => ({ ...current, propertyTaxRate: value }))
                    }
                    display={`${assumptionForm.propertyTaxRate}%`}
                  />
                  <SliderField
                    label="Home insurance"
                    min={100}
                    max={600}
                    step={5}
                    value={assumptionForm.monthlyHomeInsurance}
                    onChange={(value) =>
                      setAssumptionForm((current) => ({ ...current, monthlyHomeInsurance: value }))
                    }
                    display={`$${Number(assumptionForm.monthlyHomeInsurance).toLocaleString("en-US")}/mo`}
                  />
                </FieldGroup>
              </div>
            )}
            {errorMessage && <InlineNotice tone="warning">{errorMessage}</InlineNotice>}
            <WizardActions
              canGoBack={activeStep > 0}
              onBack={() => setStep("rent-vs-buy", Math.max(0, activeStep - 1))}
              onNext={
                activeStep < phaseLabels["rent-vs-buy"].length - 1
                  ? () => setStep("rent-vs-buy", activeStep + 1)
                  : undefined
              }
              submitLabel="Explore your numbers"
              isSubmitting={isLoading}
            />
          </form>
        );
      case "job-offer":
        return (
          <form className="panel" onSubmit={handleRunJobOffer}>
            <PhaseRail currentPhase="input" step={activeStep} steps={phaseLabels["job-offer"]} />
            <header className="panel-header">
              <span className="section-kicker">Phase 1 · Input</span>
              <h2>Job offer</h2>
              <p>
                Keep the form fast. Compensation, friction, and uncertainty do most of the
                explanatory work here.
              </p>
            </header>
            {activeStep === 0 && (
              <OfferFields
                title="Offer A · Current role"
                form={jobOfferForm.offerA}
                onChange={(offerA) => setJobOfferForm((current) => ({ ...current, offerA }))}
              />
            )}
            {activeStep === 1 && (
              <OfferFields
                title="Offer B · New role"
                form={jobOfferForm.offerB}
                onChange={(offerB) => setJobOfferForm((current) => ({ ...current, offerB }))}
              />
            )}
            {activeStep === 2 && (
              <FieldGroup
                title="Timeline and tax"
                description="A high nominal comp number can still lose once taxes and friction land."
              >
                <SliderField
                  label="Comparison window"
                  min={1}
                  max={10}
                  step={1}
                  value={jobOfferForm.comparisonYears}
                  onChange={(value) =>
                    setJobOfferForm((current) => ({ ...current, comparisonYears: value }))
                  }
                  display={`${jobOfferForm.comparisonYears} years`}
                />
                <SelectField
                  label="Marginal tax rate"
                  value={jobOfferForm.marginalTaxRate}
                  onChange={(value) =>
                    setJobOfferForm((current) => ({ ...current, marginalTaxRate: value }))
                  }
                  options={taxBracketOptions}
                />
                <SegmentedField
                  label="Both offers in the same local market?"
                  value={jobOfferForm.localMarketConcentration ? "yes" : "no"}
                  onChange={(value) =>
                    setJobOfferForm((current) => ({
                      ...current,
                      localMarketConcentration: value === "yes",
                    }))
                  }
                  options={[
                    { value: "no", label: "No" },
                    { value: "yes", label: "Yes" },
                  ]}
                />
              </FieldGroup>
            )}
            {activeStep === 3 && (
              <FieldGroup
                title="Uncertainty"
                description="Bonus and equity volatility are the knobs that drive the probability, not the headline salary."
              >
                <PercentField
                  label={`${jobOfferForm.offerA.label} bonus volatility`}
                  value={jobOfferForm.offerA.bonusPayoutVolatility}
                  onChange={(value) =>
                    setJobOfferForm((current) => ({
                      ...current,
                      offerA: { ...current.offerA, bonusPayoutVolatility: value },
                    }))
                  }
                />
                <PercentField
                  label={`${jobOfferForm.offerB.label} bonus volatility`}
                  value={jobOfferForm.offerB.bonusPayoutVolatility}
                  onChange={(value) =>
                    setJobOfferForm((current) => ({
                      ...current,
                      offerB: { ...current.offerB, bonusPayoutVolatility: value },
                    }))
                  }
                />
                <PercentField
                  label={`${jobOfferForm.offerA.label} equity volatility`}
                  value={jobOfferForm.offerA.equityVolatility}
                  onChange={(value) =>
                    setJobOfferForm((current) => ({
                      ...current,
                      offerA: { ...current.offerA, equityVolatility: value },
                    }))
                  }
                />
                <PercentField
                  label={`${jobOfferForm.offerB.label} equity volatility`}
                  value={jobOfferForm.offerB.equityVolatility}
                  onChange={(value) =>
                    setJobOfferForm((current) => ({
                      ...current,
                      offerB: { ...current.offerB, equityVolatility: value },
                    }))
                  }
                />
              </FieldGroup>
            )}
            {errorMessage && <InlineNotice tone="warning">{errorMessage}</InlineNotice>}
            <WizardActions
              canGoBack={activeStep > 0}
              onBack={() => setStep("job-offer", Math.max(0, activeStep - 1))}
              onNext={
                activeStep < phaseLabels["job-offer"].length - 1
                  ? () => setStep("job-offer", activeStep + 1)
                  : undefined
              }
              submitLabel="Explore your numbers"
              isSubmitting={isLoading}
            />
          </form>
        );
      case "retirement-survival":
        return (
          <form className="panel" onSubmit={handleRunRetirement}>
            <PhaseRail
              currentPhase="input"
              step={activeStep}
              steps={phaseLabels["retirement-survival"]}
            />
            <header className="panel-header">
              <span className="section-kicker">Phase 1 · Input</span>
              <h2>Retirement survival</h2>
              <p>The question here is not whether you win. It is whether the plan lasts.</p>
            </header>
            {activeStep === 0 && (
              <FieldGroup title="Portfolio" description="Anchor the plan with what you already have.">
                <CurrencyField
                  label="Current portfolio"
                  value={retirementForm.currentPortfolio}
                  onChange={(value) =>
                    setRetirementForm((current) => ({ ...current, currentPortfolio: value }))
                  }
                />
                <CurrencyField
                  label="Annual guaranteed income"
                  value={retirementForm.annualGuaranteedIncome}
                  onChange={(value) =>
                    setRetirementForm((current) => ({ ...current, annualGuaranteedIncome: value }))
                  }
                />
              </FieldGroup>
            )}
            {activeStep === 1 && (
              <FieldGroup
                title="Spending"
                description="The gap between spending and guaranteed income determines the withdrawal burden."
              >
                <CurrencyField
                  label="Annual spending"
                  value={retirementForm.annualSpending}
                  onChange={(value) =>
                    setRetirementForm((current) => ({ ...current, annualSpending: value }))
                  }
                />
                <SliderField
                  label="Retirement horizon"
                  min={10}
                  max={40}
                  step={1}
                  value={retirementForm.retirementYears}
                  onChange={(value) =>
                    setRetirementForm((current) => ({ ...current, retirementYears: value }))
                  }
                  display={`${retirementForm.retirementYears} years`}
                />
                <PresetField
                  label="Expected return"
                  value={retirementForm.expectedAnnualReturn}
                  onChange={(value) =>
                    setRetirementForm((current) => ({ ...current, expectedAnnualReturn: value }))
                  }
                  presets={[
                    { label: "Conservative · 5%", value: "5.0" },
                    { label: "Moderate · 6%", value: "6.0" },
                    { label: "Aggressive · 7%", value: "7.0" },
                  ]}
                  suffix="% / yr"
                />
              </FieldGroup>
            )}
            {activeStep === 2 && (
              <FieldGroup
                title="Market behavior"
                description="Risk profile and behavior under losses matter more than exact decimal precision here."
              >
                <SegmentedField
                  label="Risk profile"
                  value={retirementForm.riskProfile}
                  onChange={(value) =>
                    setRetirementForm((current) => ({
                      ...current,
                      riskProfile: value as RetirementFormState["riskProfile"],
                    }))
                  }
                  options={[
                    { value: "conservative", label: "Conservative" },
                    { value: "moderate", label: "Moderate" },
                    { value: "aggressive", label: "Aggressive" },
                  ]}
                />
                <SegmentedField
                  label="If markets dropped 30%"
                  value={retirementForm.lossBehavior}
                  onChange={(value) =>
                    setRetirementForm((current) => ({
                      ...current,
                      lossBehavior: value as RetirementFormState["lossBehavior"],
                    }))
                  }
                  options={[
                    { value: "hold", label: "Hold" },
                    { value: "sell_to_cash", label: "Sell" },
                    { value: "buy_more", label: "Buy more" },
                  ]}
                />
              </FieldGroup>
            )}
            {errorMessage && <InlineNotice tone="warning">{errorMessage}</InlineNotice>}
            <WizardActions
              canGoBack={activeStep > 0}
              onBack={() => setStep("retirement-survival", Math.max(0, activeStep - 1))}
              onNext={
                activeStep < phaseLabels["retirement-survival"].length - 1
                  ? () => setStep("retirement-survival", activeStep + 1)
                  : undefined
              }
              submitLabel="Explore your numbers"
              isSubmitting={isLoading}
            />
          </form>
        );
      case "college-vs-retirement":
        return (
          <form className="panel" onSubmit={handleRunCollege}>
            <PhaseRail
              currentPhase="input"
              step={activeStep}
              steps={phaseLabels["college-vs-retirement"]}
            />
            <header className="panel-header">
              <span className="section-kicker">Phase 1 · Input</span>
              <h2>College vs retirement</h2>
              <p>Frame this as a tradeoff between two worthy goals, not a winner and loser.</p>
            </header>
            {activeStep === 0 && (
              <FieldGroup
                title="Balances"
                description="Start with what the family has already saved."
              >
                <CurrencyField
                  label="Current retirement savings"
                  value={collegeForm.currentRetirementSavings}
                  onChange={(value) =>
                    setCollegeForm((current) => ({ ...current, currentRetirementSavings: value }))
                  }
                />
                <CurrencyField
                  label="Current college savings"
                  value={collegeForm.currentCollegeSavings}
                  onChange={(value) =>
                    setCollegeForm((current) => ({ ...current, currentCollegeSavings: value }))
                  }
                />
                <CurrencyField
                  label="Annual savings budget"
                  value={collegeForm.annualSavingsBudget}
                  onChange={(value) =>
                    setCollegeForm((current) => ({ ...current, annualSavingsBudget: value }))
                  }
                />
              </FieldGroup>
            )}
            {activeStep === 1 && (
              <FieldGroup
                title="College timeline"
                description="When tuition hits determines how much time you have to compound before withdrawals start."
              >
                <CurrencyField
                  label="Annual college cost today"
                  value={collegeForm.annualCollegeCost}
                  onChange={(value) =>
                    setCollegeForm((current) => ({ ...current, annualCollegeCost: value }))
                  }
                />
                <SliderField
                  label="Years until college starts"
                  min={1}
                  max={18}
                  step={1}
                  value={collegeForm.yearsUntilCollege}
                  onChange={(value) =>
                    setCollegeForm((current) => ({ ...current, yearsUntilCollege: value }))
                  }
                  display={`${collegeForm.yearsUntilCollege} years`}
                />
                <SliderField
                  label="Years in college"
                  min={2}
                  max={6}
                  step={1}
                  value={collegeForm.yearsInCollege}
                  onChange={(value) =>
                    setCollegeForm((current) => ({ ...current, yearsInCollege: value }))
                  }
                  display={`${collegeForm.yearsInCollege} years`}
                />
              </FieldGroup>
            )}
            {activeStep === 2 && (
              <FieldGroup
                title="Retirement plan"
                description="The opportunity cost of redirecting money away from retirement is long compounding time."
              >
                <SliderField
                  label="Years until retirement"
                  min={5}
                  max={40}
                  step={1}
                  value={collegeForm.retirementYears}
                  onChange={(value) =>
                    setCollegeForm((current) => ({ ...current, retirementYears: value }))
                  }
                  display={`${collegeForm.retirementYears} years`}
                />
                <PresetField
                  label="Expected return"
                  value={collegeForm.expectedAnnualReturn}
                  onChange={(value) =>
                    setCollegeForm((current) => ({ ...current, expectedAnnualReturn: value }))
                  }
                  presets={[
                    { label: "Conservative · 5%", value: "5.0" },
                    { label: "Moderate · 6%", value: "6.0" },
                    { label: "Aggressive · 7%", value: "7.0" },
                  ]}
                  suffix="% / yr"
                />
              </FieldGroup>
            )}
            {activeStep === 3 && (
              <FieldGroup
                title="Market behavior"
                description="Use the same risk and loss assumptions you would apply to the rest of the family balance sheet."
              >
                <SegmentedField
                  label="Risk profile"
                  value={collegeForm.riskProfile}
                  onChange={(value) =>
                    setCollegeForm((current) => ({
                      ...current,
                      riskProfile: value as CollegeVsRetirementFormState["riskProfile"],
                    }))
                  }
                  options={[
                    { value: "conservative", label: "Conservative" },
                    { value: "moderate", label: "Moderate" },
                    { value: "aggressive", label: "Aggressive" },
                  ]}
                />
                <SegmentedField
                  label="If markets dropped 30%"
                  value={collegeForm.lossBehavior}
                  onChange={(value) =>
                    setCollegeForm((current) => ({
                      ...current,
                      lossBehavior: value as CollegeVsRetirementFormState["lossBehavior"],
                    }))
                  }
                  options={[
                    { value: "hold", label: "Hold" },
                    { value: "sell_to_cash", label: "Sell" },
                    { value: "buy_more", label: "Buy more" },
                  ]}
                />
              </FieldGroup>
            )}
            {errorMessage && <InlineNotice tone="warning">{errorMessage}</InlineNotice>}
            <WizardActions
              canGoBack={activeStep > 0}
              onBack={() => setStep("college-vs-retirement", Math.max(0, activeStep - 1))}
              onNext={
                activeStep < phaseLabels["college-vs-retirement"].length - 1
                  ? () => setStep("college-vs-retirement", activeStep + 1)
                  : undefined
              }
              submitLabel="Explore your numbers"
              isSubmitting={isLoading}
            />
          </form>
        );
    }
  }

  function renderLoadingPhase() {
    return (
      <section className="panel loading-panel">
        <PhaseRail currentPhase="result" step={0} steps={activeLiveModule ? phaseLabels[activeLiveModule] : []} />
        <header className="panel-header">
          <span className="section-kicker">Your result</span>
          <h2>Working through your numbers</h2>
          <p>This engine is doing real compute, not just waiting on a network response.</p>
        </header>
        <ol className="loading-steps">
          {activeLoadingMessages.map((message, index) => (
            <li
              key={message}
              className={
                index <= loadingIndex
                  ? "loading-steps__item loading-steps__item--active"
                  : "loading-steps__item"
              }
            >
              {message}
            </li>
          ))}
        </ol>
      </section>
    );
  }

  function renderRentVsBuyResult(report: RentVsBuyReport) {
    return (
      <ResultPage
        title="Rent vs buy"
        onEdit={() => setPhase("rent-vs-buy", "input")}
        onOpenAudit={() => openAuditSheet("Where these numbers come from", report.audit_trail)}
        disclaimer={report.disclaimer}
        actions={
          <StickyActions
            onExplore={() => document.getElementById("explore-rent")?.scrollIntoView({ behavior: "smooth" })}
            onPrint={handleOpenRentPrintPdf}
            onSave={handleSaveRentAnalysis}
            onDownloadPdf={handleDownloadRentPdf}
            isSaving={isSaving}
            isGeneratingPdf={isGeneratingPdf}
            saveLabel={saveMessage}
          />
        }
      >
        <VerdictCard
          eyebrow="Your result"
          title={report.narratives.summary}
          supporting={`How this model sees it over ${report.verdict.horizon_years.toFixed(1)} years.`}
        />
        <ProbabilityBar
          leftLabel="Renting better"
          rightLabel="Buying better"
          rightProbability={report.verdict.probability_buy_beats_rent}
          leftDetail={`P10 · ${formatCurrency(report.verdict.p10_terminal_advantage_cents)}`}
          centerDetail={`Base case · ${formatCurrency(report.verdict.deterministic_advantage_cents)}`}
          rightDetail={`P90 · ${formatCurrency(report.verdict.p90_terminal_advantage_cents)}`}
        />
        <KeyNumberGrid
          items={[
            {
              label: "Break-even point",
              value: formatMonthLabel(report.verdict.break_even_month),
              caption: "When buying first catches renting in the deterministic path.",
            },
            {
              label: "True monthly cost to own",
              value: formatCurrency(report.year_one_costs.true_monthly_cents),
              caption: "Year-one all-in owner cost after modeled tax effects.",
            },
            {
              label: "Cash needed to close",
              value: formatCurrency(report.hidden_factors.initial_purchase_cash_cents),
              caption: "Down payment plus modeled buyer closing costs.",
            },
          ]}
        />
        {report.questions.risk.warnings.length > 0 && (
          <WarningList warnings={report.questions.risk.warnings} />
        )}
        <NarrativeStack
          title="The numbers explained"
          paragraphs={[report.narratives.verdict_driver, report.narratives.net_worth_summary]}
        />
        <NarrativeStack
          title="Things to consider"
          paragraphs={[report.narratives.question_liquidity, report.narratives.question_risk]}
        />
        <section id="explore-rent" className="explore-block">
          <SectionHeader
            title="Full analysis"
            description="Where the answer comes from and how sensitive it is to each assumption."
          />
          <ChartCard
            title="Projected net worth over time"
            description="The shaded gap shows how far apart renting and buying end up each year."
          >
            <DualLineChart
              rows={report.yearly_net_worth}
              series={[
                {
                  label: "Renting",
                  color: "var(--accent)",
                  values: report.yearly_net_worth.map((row) => row.rent_net_worth_cents),
                },
                {
                  label: "Buying",
                  color: "var(--accent-soft-strong)",
                  values: report.yearly_net_worth.map((row) => row.buy_net_worth_cents),
                },
              ]}
              labels={report.yearly_net_worth.map((row) => `Y${row.year}`)}
              markerMonth={report.verdict.break_even_month}
              markerLabel={formatMonthLabel(report.verdict.break_even_month)}
            />
          </ChartCard>
          <SplitCard
            left={
              <InfoList
                title="Year-one ownership costs"
                rows={[
                  { label: "Mortgage payment", value: formatCurrency(report.year_one_costs.principal_and_interest_cents) },
                  { label: "Property tax", value: formatCurrency(report.year_one_costs.property_tax_cents) },
                  { label: "Insurance", value: formatCurrency(report.year_one_costs.insurance_cents) },
                  { label: "Maintenance", value: formatCurrency(report.year_one_costs.maintenance_cents) },
                  { label: "PMI", value: formatCurrency(report.year_one_costs.pmi_cents) },
                  { label: "Liquidity premium", value: formatCurrency(report.year_one_costs.liquidity_premium_cents) },
                  { label: "True annual cost", value: formatCurrency(report.year_one_costs.true_annual_cents), strong: true },
                ]}
              />
            }
            right={
              <InfoList
                title="Hidden factors"
                rows={[
                  { label: "Equity after sale", value: formatCurrency(report.hidden_factors.equity_after_sale_horizon_cents) },
                  { label: "Closing costs", value: formatCurrency(report.hidden_factors.closing_costs_cents) },
                  { label: "Opportunity cost", value: formatCurrency(report.hidden_factors.opportunity_cost_future_value_cents) },
                  { label: "Actual tax saving", value: formatCurrency(report.hidden_factors.actual_tax_saving_year_one_cents) },
                  { label: "Capital gains tax", value: formatCurrency(report.hidden_factors.capital_gains.capital_gains_tax_cents) },
                ]}
              />
            }
          />
          <SensitivitySection
            title="How sensitive is this?"
            description={`Most sensitive assumption: ${report.sensitivity.most_sensitive_label}.`}
            rows={report.sensitivity.rows.map((row) => ({
              label: row.label,
              primary: row.probability_buy_beats_rent_label,
              secondary: row.break_even_label,
              delta: row.probability_shift_points === 0 ? "—" : `${row.probability_shift_points.toFixed(0)} pts`,
            }))}
          />
        </section>
      </ResultPage>
    );
  }

  function renderJobOfferResult(report: JobOfferReport) {
    const warnings = report.risk.local_market_concentration
      ? [
          "Both offers are in the same job market. The diversification benefit of switching employers is limited.",
          ...report.risk.warnings,
        ]
      : report.risk.warnings;
    return (
      <ResultPage
        title="Job offer"
        onEdit={() => setPhase("job-offer", "input")}
        onOpenAudit={() => openAuditSheet("Where these numbers come from", report.audit_trail)}
        disclaimer={jobOfferReportEnvelope?.disclaimer ?? "Not financial advice."}
        actions={
          <StickyActions
            onExplore={() => document.getElementById("explore-job")?.scrollIntoView({ behavior: "smooth" })}
            onPrint={handleOpenJobOfferPrintPdf}
            onDownloadPdf={handleDownloadJobOfferPdf}
            isGeneratingPdf={isGeneratingPdf}
          />
        }
      >
        <VerdictCard
          eyebrow="Your result"
          title={report.narratives.summary}
          supporting="How this model sees the tradeoff between compensation, friction, and uncertainty."
        />
        <ProbabilityBar
          leftLabel={report.offers.offer_a_label}
          rightLabel={report.offers.offer_b_label}
          rightProbability={report.verdict.probability_offer_b_wins}
          leftDetail={`P10 · ${formatCurrency(report.risk.p10_terminal_advantage_cents)}`}
          centerDetail={`Median · ${formatCurrency(report.risk.median_terminal_advantage_cents)}`}
          rightDetail={`P90 · ${formatCurrency(report.risk.p90_terminal_advantage_cents)}`}
        />
        <KeyNumberGrid
          items={[
            {
              label: "Break-even point",
              value: formatMonthLabel(report.verdict.break_even_month),
              caption: "When the new role overtakes the current one.",
            },
            {
              label: "Deterministic advantage",
              value: formatCurrency(report.verdict.end_of_horizon_advantage_cents),
              caption: `${report.verdict.winner_label} leads at the end of the chosen horizon in the base case.`,
            },
            {
              label: "Risk-adjusted advantage",
              value: formatCurrency(report.verdict.utility_adjusted_advantage_cents),
              caption: "Adjusted for the fact that losses feel worse than equivalent gains.",
            },
          ]}
        />
        {warnings.length > 0 && <WarningList warnings={warnings} />}
        <NarrativeStack
          title="The numbers explained"
          paragraphs={[report.narratives.offer_comparison, report.narratives.break_even_summary]}
        />
        <NarrativeStack
          title="Things to consider"
          paragraphs={[report.narratives.hidden_costs_summary, report.narratives.risk_summary]}
        />
        <section id="explore-job" className="explore-block">
          <SectionHeader
            title="Full analysis"
            description="Hidden costs, year-by-year comparison, and sensitivity to each assumption."
          />
          <ChartCard
            title="Cumulative value over time"
            description="The spread shows how much the switch gains or loses after the first-year friction lands."
          >
            <DualLineChart
              rows={report.yearly_comparison.map((row) => ({
                year: row.year,
                rent_net_worth_cents: row.offer_a_cumulative_value_cents,
                buy_net_worth_cents: row.offer_b_cumulative_value_cents,
                difference_cents: row.offer_b_minus_offer_a_cents,
              }))}
              series={[
                {
                  label: report.offers.offer_a_label,
                  color: "var(--accent)",
                  values: report.yearly_comparison.map((row) => row.offer_a_cumulative_value_cents),
                },
                {
                  label: report.offers.offer_b_label,
                  color: "var(--accent-soft-strong)",
                  values: report.yearly_comparison.map((row) => row.offer_b_cumulative_value_cents),
                },
              ]}
              labels={report.yearly_comparison.map((row) => `Y${row.year}`)}
              markerMonth={report.verdict.break_even_month}
              markerLabel={formatMonthLabel(report.verdict.break_even_month)}
            />
          </ChartCard>
          <SplitCard
            left={
              <ComparisonList
                title="Offer inputs"
                leftTitle={report.offers.offer_a_label}
                rightTitle={report.offers.offer_b_label}
                leftRows={report.offers.offer_a_summary}
                rightRows={report.offers.offer_b_summary}
              />
            }
            right={
              <InfoList
                title="Year-one costs to switch"
                rows={[
                  { label: "Relocation", value: formatCurrency(-report.hidden_costs.offer_b.relocation_cost_cents) },
                  { label: "Cost-of-living change", value: formatCurrency(-report.hidden_costs.offer_b.annual_cost_of_living_delta_cents) },
                  { label: "Commute cost", value: formatCurrency(-report.hidden_costs.offer_b.annual_commute_cost_cents) },
                  { label: "After-tax sign-on bonus", value: formatCurrency(report.hidden_costs.offer_b.after_tax_sign_on_bonus_cents) },
                  { label: "Net year-one switch impact", value: formatCurrency(-report.hidden_costs.offer_b_minus_offer_a_first_year_friction_cents), strong: true },
                ]}
              />
            }
          />
          <SensitivitySection
            title="How sensitive is this?"
            description={`Most sensitive assumption: ${report.sensitivity.most_sensitive_label}.`}
            rows={report.sensitivity.rows.map((row) => ({
              label: row.label,
              primary: row.probability_offer_b_wins_label,
              secondary: row.break_even_label,
              delta: row.probability_shift_points === 0 ? "—" : `${row.probability_shift_points.toFixed(0)} pts`,
            }))}
          />
        </section>
      </ResultPage>
    );
  }

  function renderRetirementResult(report: RetirementSurvivalReport) {
    return (
      <ResultPage
        title="Retirement survival"
        onEdit={() => setPhase("retirement-survival", "input")}
        onOpenAudit={() => openAuditSheet("Where these numbers come from", report.audit_trail)}
        disclaimer={retirementReportEnvelope?.disclaimer ?? "Not financial advice."}
        actions={
          <StickyActions
            onExplore={() => document.getElementById("explore-retirement")?.scrollIntoView({ behavior: "smooth" })}
            onPrint={handleOpenRetirementPrintPdf}
            onDownloadPdf={handleDownloadRetirementPdf}
            isGeneratingPdf={isGeneratingPdf}
          />
        }
      >
        {report.verdict.probability_portfolio_survives < 0.8 && (
          <InlineNotice tone="warning">
            At current spending, the model shows a meaningful chance of running out of money before the end of the horizon. See the spending analysis below.
          </InlineNotice>
        )}
        <VerdictCard
          eyebrow="Your result"
          title={report.narratives.summary}
          supporting="How this model sees the odds that your portfolio lasts."
        />
        <ProbabilityBar
          leftLabel="Runs short"
          rightLabel="Portfolio lasts"
          rightProbability={report.verdict.probability_portfolio_survives}
          leftDetail={`P10 · ${formatCurrency(report.wealth_at_horizon.p10_terminal_wealth_cents)}`}
          centerDetail={`Median · ${formatCurrency(report.wealth_at_horizon.median_terminal_wealth_cents)}`}
          rightDetail={`P90 · ${formatCurrency(report.wealth_at_horizon.p90_terminal_wealth_cents)}`}
        />
        <KeyNumberGrid
          items={[
            {
              label: "Survival probability",
              value: formatPercent(report.verdict.probability_portfolio_survives),
              caption: `Chance the portfolio lasts ${report.verdict.horizon_years} years.`,
            },
            {
              label: "High-confidence spending rate",
              value: formatPercent(report.verdict.safe_withdrawal_rate_95, 2),
              caption: "Modeled 95% safe withdrawal rate.",
            },
            {
              label: "Base-case depletion",
              value: report.verdict.deterministic_depletion_year === null ? "Does not deplete" : `Year ${report.verdict.deterministic_depletion_year}`,
              caption: "Deterministic path only, not a guarantee.",
            },
          ]}
        />
        {report.warnings.length > 0 && <WarningList warnings={report.warnings} />}
        <NarrativeStack
          title="The numbers explained"
          paragraphs={[report.narratives.survival_verdict, report.narratives.withdrawal_rate_summary]}
        />
        <NarrativeStack
          title="Things to consider"
          paragraphs={[report.narratives.wealth_range_summary, report.narratives.risk_summary]}
        />
        <section id="explore-retirement" className="explore-block">
          <SectionHeader
            title="Full analysis"
            description="The fan chart below shows how wide the range of retirement outcomes can get."
          />
          <ChartCard
            title="Portfolio path by year"
            description="The shaded band spans the 10th to 90th percentile of simulated outcomes."
          >
            <FanChart rows={report.yearly_projection} />
          </ChartCard>
          <SplitCard
            left={
              <InfoList
                title="Withdrawal analysis"
                rows={[
                  { label: "Net annual withdrawal", value: formatCurrency(report.withdrawal_analysis.net_annual_withdrawal_cents) },
                  { label: "Current withdrawal rate", value: formatPercent(report.withdrawal_analysis.current_withdrawal_rate, 2) },
                  { label: "95% safe rate", value: formatPercent(report.withdrawal_analysis.safe_withdrawal_rate_95, 2) },
                  { label: "Safe annual spending", value: formatCurrency(report.withdrawal_analysis.safe_withdrawal_annual_cents) },
                  { label: "Gap", value: formatCurrency(report.withdrawal_analysis.safe_withdrawal_gap_cents), strong: true },
                ]}
              />
            }
            right={
              <InfoList
                title="Inputs and assumptions"
                rows={[...report.inputs_summary.slice(0, 4), ...report.assumptions_summary].map((row) => ({
                  label: row.label,
                  value: row.value,
                }))}
              />
            }
          />
        </section>
      </ResultPage>
    );
  }

  function renderCollegeResult(report: CollegeVsRetirementReport) {
    return (
      <ResultPage
        title="College vs retirement"
        onEdit={() => setPhase("college-vs-retirement", "input")}
        onOpenAudit={() => openAuditSheet("Where these numbers come from", report.audit_trail)}
        disclaimer={collegeReportEnvelope?.disclaimer ?? "Not financial advice."}
        actions={
          <StickyActions
            onExplore={() => document.getElementById("explore-college")?.scrollIntoView({ behavior: "smooth" })}
            onPrint={handleOpenCollegePrintPdf}
            onDownloadPdf={handleDownloadCollegePdf}
            isGeneratingPdf={isGeneratingPdf}
          />
        }
      >
        <VerdictCard
          eyebrow="Your result"
          title={report.narratives.summary}
          supporting="How this model sees the tradeoff between student debt and retirement compounding."
        />
        <ProbabilityBar
          leftLabel="College first"
          rightLabel="Retirement first"
          rightProbability={report.verdict.probability_retirement_first_wins}
          leftDetail={`P10 · ${formatCurrency(report.retirement_outcomes.p10_terminal_advantage_cents)}`}
          centerDetail={`Tradeoff · ${formatCurrency(report.verdict.end_of_horizon_advantage_cents)}`}
          rightDetail={`P90 · ${formatCurrency(report.retirement_outcomes.p90_terminal_advantage_cents)}`}
        />
        <KeyNumberGrid
          items={[
            {
              label: "Break-even year",
              value: formatYearLabel(report.verdict.break_even_year),
              caption: "When retirement-first overtakes college-first, if it does.",
            },
            {
              label: "Retirement-first win probability",
              value: formatPercent(report.verdict.probability_retirement_first_wins),
              caption: "Share of simulated futures where retirement-first leads.",
            },
            {
              label: "Risk-adjusted advantage",
              value: formatCurrency(report.verdict.utility_adjusted_advantage_cents),
              caption: "Tradeoff adjusted for how losses feel compared with gains.",
            },
          ]}
        />
        {report.warnings.length > 0 && <WarningList warnings={report.warnings} />}
        <NarrativeStack
          title="The numbers explained"
          paragraphs={[report.narratives.allocation_verdict, report.narratives.loan_impact_summary]}
        />
        <NarrativeStack
          title="Things to consider"
          paragraphs={[report.narratives.retirement_outcome_summary, report.narratives.risk_summary]}
        />
        <section id="explore-college" className="explore-block">
          <SectionHeader
            title="Full analysis"
            description="Both goals stay visible at the same time so the tradeoff stays honest."
          />
          <TwoColumnOutcomeCard
            leftTitle="College first"
            rightTitle="Retirement first"
            rows={[
              {
                label: "Student loans taken",
                leftValue: formatCurrency(report.funding_analysis.college_first_total_loan_cents),
                rightValue: formatCurrency(report.funding_analysis.retirement_first_total_loan_cents),
              },
              {
                label: "Retirement at horizon",
                leftValue: formatCurrency(report.retirement_outcomes.college_first_terminal_retirement_cents),
                rightValue: formatCurrency(report.retirement_outcomes.retirement_first_terminal_retirement_cents),
              },
              {
                label: "College fully funded?",
                leftValue: report.funding_analysis.college_first_total_loan_cents === 0 ? "Yes" : "No",
                rightValue: report.funding_analysis.retirement_first_total_loan_cents === 0 ? "Yes" : "No",
              },
            ]}
          />
          <ChartCard
            title="Net worth path over time"
            description="Retirement-first versus college-first across the full planning horizon."
          >
            <DualLineChart
              rows={report.yearly_comparison.map((row) => ({
                year: row.year,
                rent_net_worth_cents: row.college_first_net_worth_cents,
                buy_net_worth_cents: row.retirement_first_net_worth_cents,
                difference_cents: row.retirement_first_minus_college_first_cents,
              }))}
              series={[
                {
                  label: "College first",
                  color: "var(--accent)",
                  values: report.yearly_comparison.map((row) => row.college_first_net_worth_cents),
                },
                {
                  label: "Retirement first",
                  color: "var(--accent-soft-strong)",
                  values: report.yearly_comparison.map((row) => row.retirement_first_net_worth_cents),
                },
              ]}
              labels={report.yearly_comparison.map((row) => `Y${row.year}`)}
              markerMonth={report.verdict.break_even_year === null ? null : report.verdict.break_even_year * 12}
              markerLabel={formatYearLabel(report.verdict.break_even_year)}
            />
          </ChartCard>
        </section>
      </ResultPage>
    );
  }

  function renderResultPhase() {
    if (!activeLiveModule) {
      return renderInputPhase();
    }
    if (activeLiveModule === "rent-vs-buy" && rentReportEnvelope) {
      return renderRentVsBuyResult(rentReportEnvelope.report);
    }
    if (activeLiveModule === "job-offer" && jobOfferReportEnvelope) {
      return renderJobOfferResult(jobOfferReportEnvelope.report);
    }
    if (activeLiveModule === "retirement-survival" && retirementReportEnvelope) {
      return renderRetirementResult(retirementReportEnvelope.report);
    }
    if (activeLiveModule === "college-vs-retirement" && collegeReportEnvelope) {
      return renderCollegeResult(collegeReportEnvelope.report);
    }
    return renderInputPhase();
  }

  function renderModuleNavigation(compact = false) {
    return (
      <nav
        className={`module-list${compact ? " module-list--compact" : ""}`}
        aria-label="Family finance tools"
      >
        {modules.map((module) => (
          <button
            key={module.id}
            type="button"
            className={`module-card${module.id === activeModule ? " module-card--active" : ""}${
              compact ? " module-card--compact" : ""
            }`}
            onClick={() => {
              setActiveModule(module.id);
              setErrorMessage(null);
              setSaveMessage(null);
            }}
          >
            <span className="module-card__status">{module.status === "live" ? "Live" : "Queued"}</span>
            <strong>{module.label}</strong>
            <span>{module.description}</span>
          </button>
        ))}
      </nav>
    );
  }

  return (
    <div className={`app-shell${isEmbedMode ? " app-shell--embed" : ""}`}>
      {!isEmbedMode && (
        <aside className="sidebar">
          <div className="brand">
            <span className="section-kicker">Family Financial Compass</span>
            <h1>Clarity for the biggest family decisions.</h1>
            <p>
              Each tool is a decision workspace: guided inputs first, then a result you can trust,
              then the numbers underneath it.
            </p>
          </div>
          {renderModuleNavigation()}
        </aside>
      )}

      <main className={`workspace${isEmbedMode ? " workspace--embed" : ""}`}>
        {isEmbedMode && renderModuleNavigation(true)}
        <header className={`workspace-header${isEmbedMode ? " workspace-header--embed" : ""}`}>
          <div>
            <span className="section-kicker">
              {activeMeta.status === "live" ? "Decision workspace" : "Queued"}
            </span>
            <h2>{activeMeta.label}</h2>
          </div>
          <p>{activeMeta.description}</p>
        </header>
        {isLoading ? renderLoadingPhase() : activePhase === "input" ? renderInputPhase() : renderResultPhase()}
      </main>

      <AuditSheet
        title={auditSheet?.title ?? ""}
        rows={auditSheet?.rows ?? []}
        open={auditSheet !== null}
        onClose={() => setAuditSheet(null)}
      />
    </div>
  );
}

function PhaseRail({
  currentPhase,
  step,
  steps,
}: {
  currentPhase: ModulePhase;
  step: number;
  steps: string[];
}) {
  return (
    <div className="phase-rail">
      <div className={`phase-chip${currentPhase === "input" ? " phase-chip--active" : " phase-chip--complete"}`}>
        1. Input
      </div>
      <div className={`phase-chip${currentPhase === "result" ? " phase-chip--active" : ""}`}>2. Result</div>
      <div className={`phase-chip${currentPhase === "result" ? " phase-chip--active" : ""}`}>3. Explore</div>
      {currentPhase === "input" && steps.length > 0 && (
        <span className="step-caption">
          Step {step + 1} of {steps.length} · {steps[step]}
        </span>
      )}
    </div>
  );
}

function ResultPage({
  title,
  onEdit,
  onOpenAudit,
  disclaimer,
  actions,
  children,
}: {
  title: string;
  onEdit: () => void;
  onOpenAudit: () => void;
  disclaimer: string;
  actions: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="result-page">
      <div className="result-page__header">
        <div>
          <span className="section-kicker">Decision result</span>
          <h2>{title}</h2>
        </div>
        <div className="result-page__header-actions">
          <button type="button" className="button button--secondary" onClick={onEdit}>
            Edit inputs
          </button>
          <button type="button" className="button button--secondary" onClick={onOpenAudit}>
            Where these numbers come from
          </button>
        </div>
      </div>
      {children}
      <footer className="disclaimer-footnote">{disclaimer}</footer>
      {actions}
    </div>
  );
}

function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="section-header">
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

function VerdictCard({
  eyebrow,
  title,
  supporting,
}: {
  eyebrow: string;
  title: string;
  supporting: string;
}) {
  return (
    <section className="verdict-card">
      <span className="section-kicker">{eyebrow}</span>
      <h3>{title}</h3>
      <p>{supporting}</p>
    </section>
  );
}

function ProbabilityBar({
  leftLabel,
  rightLabel,
  rightProbability,
  leftDetail,
  centerDetail,
  rightDetail,
}: {
  leftLabel: string;
  rightLabel: string;
  rightProbability: number;
  leftDetail: string;
  centerDetail: string;
  rightDetail: string;
}) {
  const leftProbability = Math.max(0, 1 - rightProbability);
  return (
    <section className="probability-card">
      <div className="probability-card__labels">
        <span>{leftLabel}</span>
        <span>{rightLabel}</span>
      </div>
      <div className="probability-bar">
        <div className="probability-bar__left" style={{ width: `${leftProbability * 100}%` }} />
        <div className="probability-bar__right" style={{ width: `${rightProbability * 100}%` }} />
      </div>
      <div className="probability-card__numbers">
        <strong>{formatPercent(leftProbability)}</strong>
        <strong>{formatPercent(rightProbability)}</strong>
      </div>
      <div className="probability-card__details">
        <div>
          <span>P10 outcome</span>
          <strong>{leftDetail}</strong>
        </div>
        <div>
          <span>Middle outcome</span>
          <strong>{centerDetail}</strong>
        </div>
        <div>
          <span>P90 outcome</span>
          <strong>{rightDetail}</strong>
        </div>
      </div>
    </section>
  );
}

function KeyNumberGrid({
  items,
}: {
  items: Array<{ label: string; value: string; caption: string }>;
}) {
  return (
    <section className="key-grid">
      {items.map((item) => (
        <article key={item.label} className="key-card">
          <span>{item.label}</span>
          <strong>{item.value}</strong>
          <p>{item.caption}</p>
        </article>
      ))}
    </section>
  );
}

function WarningList({ warnings }: { warnings: string[] }) {
  return (
    <section className="warning-stack">
      {warnings.map((warning) => (
        <article key={warning} className="warning-card">
          <strong>Warning</strong>
          <p>{warning}</p>
        </article>
      ))}
    </section>
  );
}

function NarrativeStack({
  title,
  paragraphs,
}: {
  title: string;
  paragraphs: string[];
}) {
  return (
    <section className="narrative-block">
      <h3>{title}</h3>
      {paragraphs.map((paragraph) => (
        <p key={paragraph}>{paragraph}</p>
      ))}
    </section>
  );
}

function ChartCard({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="chart-card">
      <div className="chart-card__header">
        <h4>{title}</h4>
        <p>{description}</p>
      </div>
      <div className="chart-scroll">{children}</div>
    </section>
  );
}

function DualLineChart({
  rows,
  series,
  labels,
  markerMonth,
  markerLabel,
}: {
  rows: ReportYearRow[];
  series: Array<{ label: string; color: string; values: number[] }>;
  labels: string[];
  markerMonth: number | null;
  markerLabel: string;
}) {
  const width = 720;
  const height = 320;
  const allValues = series.flatMap((entry) => entry.values);
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const pointSets = series.map((entry) => normalizePoints(entry.values, width, height, min, max));
  const markerX =
    markerMonth === null || rows.length === 0
      ? null
      : Math.max(0, Math.min(width, ((markerMonth / 12 - 1) / Math.max(rows.length - 1, 1)) * width));

  return (
    <div className="chart-frame">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Trend chart">
        {pointSets.length >= 2 && (
          <path d={buildBandPath(pointSets[0], pointSets[1])} fill="rgba(36, 71, 55, 0.08)" />
        )}
        {pointSets.map((points, index) => (
          <path
            key={series[index].label}
            d={buildLinePath(points)}
            fill="none"
            stroke={series[index].color}
            strokeWidth="4"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ))}
        {markerX !== null && (
          <>
            <line x1={markerX} y1={0} x2={markerX} y2={height} stroke="rgba(23,34,29,0.3)" strokeDasharray="8 8" />
            <text x={markerX + 8} y={18} fontSize="14" fill="#5f6f67">
              {markerLabel}
            </text>
          </>
        )}
      </svg>
      <div className="chart-axis">
        <span>{formatCompactCurrency(min)}</span>
        <span>{formatCompactCurrency(max)}</span>
      </div>
      <div className="chart-legend">
        {series.map((entry) => (
          <span key={entry.label}>
            <i style={{ background: entry.color }} />
            {entry.label}
          </span>
        ))}
      </div>
      <div className="chart-labels">
        {labels.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>
    </div>
  );
}

function SplitCard({
  left,
  right,
}: {
  left: ReactNode;
  right: ReactNode;
}) {
  return <div className="split-grid">{left}{right}</div>;
}

function FanChart({
  rows,
}: {
  rows: RetirementSurvivalReport["yearly_projection"];
}) {
  const width = 720;
  const height = 320;
  const allValues = rows.flatMap((row) => [
    row.p10_portfolio_cents,
    row.p90_portfolio_cents,
    row.median_portfolio_cents,
    row.deterministic_portfolio_cents,
  ]);
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const p10 = normalizePoints(rows.map((row) => row.p10_portfolio_cents), width, height, min, max);
  const p90 = normalizePoints(rows.map((row) => row.p90_portfolio_cents), width, height, min, max);
  const median = normalizePoints(rows.map((row) => row.median_portfolio_cents), width, height, min, max);
  const deterministic = normalizePoints(
    rows.map((row) => row.deterministic_portfolio_cents),
    width,
    height,
    min,
    max,
  );

  return (
    <div className="chart-frame">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Retirement fan chart">
        <path d={buildBandPath(p10, p90)} fill="rgba(36, 71, 55, 0.12)" />
        <path d={buildLinePath(median)} fill="none" stroke="var(--accent)" strokeWidth="4" />
        <path d={buildLinePath(deterministic)} fill="none" stroke="var(--accent-soft-strong)" strokeWidth="3" />
      </svg>
      <div className="chart-axis">
        <span>{formatCompactCurrency(min)}</span>
        <span>{formatCompactCurrency(max)}</span>
      </div>
      <div className="chart-legend">
        <span><i style={{ background: "var(--accent)" }} />Median</span>
        <span><i style={{ background: "var(--accent-soft-strong)" }} />Deterministic</span>
        <span><i style={{ background: "rgba(36, 71, 55, 0.12)" }} />P10–P90 band</span>
      </div>
      <div className="chart-labels">
        {rows.map((row) => (
          <span key={row.year}>Y{row.year}</span>
        ))}
      </div>
    </div>
  );
}

function InfoList({
  title,
  rows,
}: {
  title: string;
  rows: Array<{ label: string; value: string; strong?: boolean }>;
}) {
  return (
    <section className="info-card">
      <h4>{title}</h4>
      <div className="info-list">
        {rows.map((row) => (
          <div key={row.label} className="info-list__row">
            <span>{row.label}</span>
            <strong className={row.strong ? "strong" : ""}>{row.value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function ComparisonList({
  title,
  leftTitle,
  rightTitle,
  leftRows,
  rightRows,
}: {
  title: string;
  leftTitle: string;
  rightTitle: string;
  leftRows: ReportInputsSummaryRow[];
  rightRows: ReportInputsSummaryRow[];
}) {
  return (
    <section className="info-card">
      <h4>{title}</h4>
      <div className="compare-table">
        <div className="compare-table__header" />
        <div className="compare-table__header">{leftTitle}</div>
        <div className="compare-table__header">{rightTitle}</div>
        {leftRows.map((row, index) => (
          <div key={row.label} className="compare-table__cells">
            <span>{row.label}</span>
            <strong>{row.value}</strong>
            <strong>{rightRows[index]?.value ?? "—"}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function TwoColumnOutcomeCard({
  leftTitle,
  rightTitle,
  rows,
}: {
  leftTitle: string;
  rightTitle: string;
  rows: Array<{ label: string; leftValue: string; rightValue: string }>;
}) {
  return (
    <section className="info-card">
      <h4>Tradeoff at a glance</h4>
      <div className="compare-table">
        <div className="compare-table__header" />
        <div className="compare-table__header">{leftTitle}</div>
        <div className="compare-table__header">{rightTitle}</div>
        {rows.map((row) => (
          <div key={row.label} className="compare-table__cells">
            <span>{row.label}</span>
            <strong>{row.leftValue}</strong>
            <strong>{row.rightValue}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function SensitivitySection({
  title,
  description,
  rows,
}: {
  title: string;
  description: string;
  rows: Array<{ label: string; primary: string; secondary: string; delta: string }>;
}) {
  return (
    <section className="info-card">
      <div className="chart-card__header">
        <h4>{title}</h4>
        <p>{description}</p>
      </div>
      <div className="sensitivity-list">
        {rows.map((row) => (
          <details key={row.label} className="sensitivity-item">
            <summary>
              <span>{row.label}</span>
              <strong>{row.primary}</strong>
            </summary>
            <div className="sensitivity-item__body">
              <span>Break-even: {row.secondary}</span>
              <span>Change: {row.delta}</span>
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}

function StickyActions({
  onExplore,
  onPrint,
  onSave,
  onDownloadPdf,
  isSaving = false,
  isGeneratingPdf = false,
  saveLabel,
}: {
  onExplore: () => void;
  onPrint: () => void;
  onSave?: () => void;
  onDownloadPdf?: () => void;
  isSaving?: boolean;
  isGeneratingPdf?: boolean;
  saveLabel?: string | null;
}) {
  return (
    <div className="sticky-actions">
      <button type="button" className="button button--secondary" onClick={onExplore}>
        See full analysis
      </button>
      <button type="button" className="button button--secondary" onClick={onPrint}>
        Open printable PDF
      </button>
      {onSave && (
        <button type="button" className="button button--secondary" onClick={onSave} disabled={isSaving}>
          {isSaving ? "Saving..." : "Save analysis"}
        </button>
      )}
      {onDownloadPdf && (
        <button type="button" className="button button--primary" onClick={onDownloadPdf} disabled={isGeneratingPdf}>
          {isGeneratingPdf ? "Building PDF..." : "Download PDF"}
        </button>
      )}
      {saveLabel && <span className="sticky-actions__note">{saveLabel}</span>}
    </div>
  );
}

function AuditSheet({
  title,
  rows,
  open,
  onClose,
}: {
  title: string;
  rows: ReportAuditTrailRow[];
  open: boolean;
  onClose: () => void;
}) {
  if (!open) {
    return null;
  }
  return (
    <div className="audit-sheet-backdrop" onClick={onClose}>
      <div className="audit-sheet" onClick={(event) => event.stopPropagation()}>
        <div className="audit-sheet__header">
          <div>
            <span className="section-kicker">Audit trail</span>
            <h3>{title}</h3>
          </div>
          <button type="button" className="button button--secondary" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="audit-sheet__body">
          {rows.map((row) => (
            <article key={`${row.parameter ?? row.label}-${row.source}`} className="audit-row">
              <div className="audit-row__top">
                <strong>{row.label}</strong>
                <span>{row.value === null ? "—" : String(row.value)}</span>
              </div>
              <p>Source: {row.source} · Updated {formatDate(row.last_updated)}</p>
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}

function FieldGroup({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="field-group">
      <div className="field-group__header">
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      <div className="field-group__body">{children}</div>
    </section>
  );
}

function BaseField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}

function CurrencyField({
  label,
  value,
  onChange,
  suffix,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  suffix?: string;
  hint?: string;
}) {
  return (
    <BaseField label={label} hint={hint}>
      <div className="input-shell">
        <small>$</small>
        <input type="number" inputMode="decimal" value={value} onChange={(event) => onChange(event.target.value)} />
        {suffix && <small>{suffix}</small>}
      </div>
    </BaseField>
  );
}

function PercentField({
  label,
  value,
  onChange,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
}) {
  return (
    <BaseField label={label} hint={hint}>
      <div className="input-shell">
        <input type="number" inputMode="decimal" value={value} onChange={(event) => onChange(event.target.value)} />
        <small>%</small>
      </div>
    </BaseField>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <BaseField label={label}>
      <div className="input-shell">
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
    </BaseField>
  );
}

function SegmentedField({
  label,
  value,
  onChange,
  options,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  hint?: string;
}) {
  return (
    <BaseField label={label} hint={hint}>
      <div className="segmented-field">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`segmented-field__option${option.value === value ? " segmented-field__option--active" : ""}`}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </BaseField>
  );
}

function SliderField({
  label,
  value,
  onChange,
  min,
  max,
  step,
  display,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  min: number;
  max: number;
  step: number;
  display: string;
}) {
  return (
    <BaseField label={label}>
      <div className="slider-field">
        <div className="slider-field__top">
          <strong>{display}</strong>
        </div>
        <input type="range" min={min} max={max} step={step} value={value} onChange={(event) => onChange(event.target.value)} />
      </div>
    </BaseField>
  );
}

function PresetField({
  label,
  value,
  onChange,
  presets,
  suffix,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  presets: Array<{ label: string; value: string }>;
  suffix?: string;
}) {
  return (
    <BaseField label={label}>
      <div className="preset-row">
        {presets.map((preset) => (
          <button
            key={preset.value}
            type="button"
            className={`preset-chip${preset.value === value ? " preset-chip--active" : ""}`}
            onClick={() => onChange(preset.value)}
          >
            {preset.label}
          </button>
        ))}
      </div>
      <div className="input-shell">
        <input type="number" inputMode="decimal" value={value} onChange={(event) => onChange(event.target.value)} />
        {suffix && <small>{suffix}</small>}
      </div>
    </BaseField>
  );
}

function OfferFields({
  title,
  form,
  onChange,
}: {
  title: string;
  form: JobOfferFormSideState;
  onChange: (next: JobOfferFormSideState) => void;
}) {
  return (
    <FieldGroup title={title} description="Keep the numbers concrete. The model will handle the uncertainty later.">
      <BaseField label="Role label">
        <div className="input-shell">
          <input type="text" value={form.label} onChange={(event) => onChange({ ...form, label: event.target.value })} />
        </div>
      </BaseField>
      <CurrencyField label="Base salary" value={form.baseSalary} onChange={(value) => onChange({ ...form, baseSalary: value })} />
      <CurrencyField label="Target bonus" value={form.targetBonus} onChange={(value) => onChange({ ...form, targetBonus: value })} />
      <CurrencyField label="Annual equity vesting" value={form.annualEquityVesting} onChange={(value) => onChange({ ...form, annualEquityVesting: value })} />
      <CurrencyField label="Sign-on bonus" value={form.signOnBonus} onChange={(value) => onChange({ ...form, signOnBonus: value })} />
      <CurrencyField label="Relocation cost" value={form.relocationCost} onChange={(value) => onChange({ ...form, relocationCost: value })} />
      <CurrencyField
        label="Annual cost-of-living delta"
        value={form.annualCostOfLivingDelta}
        onChange={(value) => onChange({ ...form, annualCostOfLivingDelta: value })}
        hint="Use a negative number if the new city is cheaper."
      />
      <CurrencyField label="Annual commute cost" value={form.annualCommuteCost} onChange={(value) => onChange({ ...form, annualCommuteCost: value })} />
      <PercentField label="Annual compensation growth" value={form.annualCompGrowthRate} onChange={(value) => onChange({ ...form, annualCompGrowthRate: value })} />
    </FieldGroup>
  );
}

function WizardActions({
  canGoBack,
  onBack,
  onNext,
  submitLabel,
  isSubmitting,
}: {
  canGoBack: boolean;
  onBack: () => void;
  onNext?: () => void;
  submitLabel: string;
  isSubmitting: boolean;
}) {
  return (
    <div className="wizard-actions">
      <button type="button" className="button button--secondary" onClick={onBack} disabled={!canGoBack}>
        Back
      </button>
      {onNext ? (
        <button type="button" className="button button--primary" onClick={onNext}>
          Next
        </button>
      ) : (
        <button type="submit" className="button button--primary" disabled={isSubmitting}>
          {isSubmitting ? "Running..." : submitLabel}
        </button>
      )}
    </div>
  );
}

function InlineNotice({
  tone,
  children,
}: {
  tone: "warning" | "muted";
  children: ReactNode;
}) {
  return <div className={`inline-notice inline-notice--${tone}`}>{children}</div>;
}
