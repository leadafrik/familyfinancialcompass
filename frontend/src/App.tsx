import { startTransition, useEffect, useState } from "react";
import type { Dispatch, FormEvent, ReactNode, SetStateAction } from "react";

import {
  analyzeRetirementSurvival,
  analyzeRentVsBuy,
  buildRentVsBuyReport,
  getCurrentRentVsBuyAssumptions,
  listScenarios,
  saveRentVsBuyScenario,
} from "./api";
import type {
  AnalysisEnvelope,
  AuditTrailItem,
  AssumptionFormState,
  AssumptionOverridesPayload,
  CurrentAssumptionsEnvelope,
  CreateScenarioPayload,
  FormState,
  RetirementAnalysis,
  RetirementAnalysisEnvelope,
  RetirementFormState,
  RetirementInputPayload,
  RetirementYearProjectionRow,
  RentVsBuyInputPayload,
  ScenarioEnvelope,
  YearlyComparisonRow,
} from "./types";

// ── module definitions ────────────────────────────────────────────────────────

type ModuleId =
  | "rent-vs-buy"
  | "retirement-survival"
  | "job-offer"
  | "college-vs-retirement"
  | "debt-payoff-vs-invest";

const modules: Array<{
  id: ModuleId;
  label: string;
  status: "live" | "next" | "queued";
  description: string;
}> = [
  {
    id: "rent-vs-buy",
    label: "Rent vs Buy",
    status: "live",
    description: "Inputs, simulation, and saved scenarios wired end to end.",
  },
  {
    id: "retirement-survival",
    label: "Retirement Survival",
    status: "live",
    description: "Sequence-of-returns survival and sustainable withdrawal planning.",
  },
  {
    id: "job-offer",
    label: "Job Offer",
    status: "queued",
    description: "Cash compensation, equity uncertainty, and relocation tradeoffs.",
  },
  {
    id: "college-vs-retirement",
    label: "College vs Retirement",
    status: "queued",
    description: "Aid-aware asset tradeoffs and retirement opportunity cost.",
  },
  {
    id: "debt-payoff-vs-invest",
    label: "Debt vs Invest",
    status: "queued",
    description: "Debt spread, liquidity, and capital allocation decisions.",
  },
];

// ── default form state ────────────────────────────────────────────────────────

const defaultFormState: FormState = {
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

const defaultAssumptionFormState: AssumptionFormState = {
  mortgageRate: "6.82",
  propertyTaxRate: "1.74",
  monthlyHomeInsurance: "200",
  rentGrowthRate: "3.2",
  maintenanceRate: "1.0",
  sellerClosingRate: "7.0",
  buyerClosingRate: "3.0",
};

const defaultRetirementFormState: RetirementFormState = {
  currentPortfolio: "1500000",
  annualSpending: "80000",
  annualGuaranteedIncome: "20000",
  retirementYears: "30",
  expectedAnnualReturn: "6.0",
  riskProfile: "moderate",
  lossBehavior: "hold",
};

type AssumptionBaseline = {
  assumptionsSnapshot: Record<string, unknown>;
  auditTrail: AuditTrailItem[];
  assumptionForm: AssumptionFormState;
};

// ── helpers ───────────────────────────────────────────────────────────────────

function dollarsToCents(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
}

function percentToRate(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed / 100 : 0;
}

function rateToPercentString(value: number, digits = 2): string {
  return (value * 100).toFixed(digits);
}

function formatCurrency(cents: number): string {
  const abs = Math.abs(cents) / 100;
  const sign = cents < 0 ? "−" : "";
  return sign + "$" + abs.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function formatPercent(value: number): string {
  return (value * 100).toFixed(0) + "%";
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function centsToMonthlyDollars(cents: number): string {
  return String(Math.round(cents / 1200));
}

function buildPayload(form: FormState): RentVsBuyInputPayload {
  return {
    target_home_price_cents: dollarsToCents(form.targetHomePrice),
    down_payment_cents: dollarsToCents(form.downPayment),
    loan_term_years: Number(form.loanTermYears) as 15 | 30,
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
  if (baseline === null) {
    return candidate;
  }

  const baselineCandidate: AssumptionOverridesPayload = {
    mortgage_rate: percentToRate(baseline.assumptionForm.mortgageRate),
    property_tax_rate: percentToRate(baseline.assumptionForm.propertyTaxRate),
    annual_home_insurance_cents:
      dollarsToCents(baseline.assumptionForm.monthlyHomeInsurance) * 12,
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

function buildAnalyzeRequestPayload(
  form: FormState,
  assumptionForm: AssumptionFormState,
  baseline: AssumptionBaseline | null,
) {
  const payload: CreateScenarioPayload | {
    input: RentVsBuyInputPayload;
    simulation_seed: number;
    assumption_overrides?: AssumptionOverridesPayload;
    assumptions_snapshot?: Record<string, unknown>;
    audit_trail_snapshot?: AuditTrailItem[];
  } = {
    input: buildPayload(form),
    simulation_seed: 7,
  };
  const overrides = buildAssumptionOverrides(assumptionForm, baseline);
  if (overrides) {
    payload.assumption_overrides = overrides;
  }
  if (baseline) {
    payload.assumptions_snapshot = baseline.assumptionsSnapshot;
    payload.audit_trail_snapshot = baseline.auditTrail;
  }
  return payload;
}

function buildScenarioPayload(
  form: FormState,
  assumptionForm: AssumptionFormState,
  userId: string,
  baseline: AssumptionBaseline | null,
): CreateScenarioPayload {
  return {
    ...buildAnalyzeRequestPayload(form, assumptionForm, baseline),
    user_id: userId,
    idempotency_key: crypto.randomUUID(),
  };
}

function readSnapshotValue(
  snapshot: Record<string, unknown>,
  key: keyof RentVsBuyInputPayload,
): unknown {
  return snapshot[key] ?? null;
}

function snapshotToPayload(snapshot: Record<string, unknown>): RentVsBuyInputPayload {
  return {
    target_home_price_cents: Number(readSnapshotValue(snapshot, "target_home_price_cents") ?? 0),
    down_payment_cents: Number(readSnapshotValue(snapshot, "down_payment_cents") ?? 0),
    loan_term_years: Number(
      readSnapshotValue(snapshot, "loan_term_years") ?? 30,
    ) as 15 | 30,
    expected_years_in_home: Number(
      readSnapshotValue(snapshot, "expected_years_in_home") ?? 7,
    ),
    current_monthly_rent_cents: Number(
      readSnapshotValue(snapshot, "current_monthly_rent_cents") ?? 0,
    ),
    annual_household_income_cents: Number(
      readSnapshotValue(snapshot, "annual_household_income_cents") ?? 0,
    ),
    current_savings_cents: Number(readSnapshotValue(snapshot, "current_savings_cents") ?? 0),
    monthly_savings_cents: Number(readSnapshotValue(snapshot, "monthly_savings_cents") ?? 0),
    expected_home_appreciation_rate: Number(
      readSnapshotValue(snapshot, "expected_home_appreciation_rate") ?? 0,
    ),
    expected_investment_return_rate: Number(
      readSnapshotValue(snapshot, "expected_investment_return_rate") ?? 0,
    ),
    risk_profile: String(
      readSnapshotValue(snapshot, "risk_profile") ?? "moderate",
    ) as RentVsBuyInputPayload["risk_profile"],
    loss_behavior: String(
      readSnapshotValue(snapshot, "loss_behavior") ?? "hold",
    ) as RentVsBuyInputPayload["loss_behavior"],
    income_stability: String(
      readSnapshotValue(snapshot, "income_stability") ?? "stable",
    ) as RentVsBuyInputPayload["income_stability"],
    employment_tied_to_local_economy: Boolean(
      readSnapshotValue(snapshot, "employment_tied_to_local_economy"),
    ),
    current_housing_status: String(
      readSnapshotValue(snapshot, "current_housing_status") ?? "renting",
    ) as RentVsBuyInputPayload["current_housing_status"],
    market_region: String(readSnapshotValue(snapshot, "market_region") ?? "national"),
    marginal_tax_rate: Number(readSnapshotValue(snapshot, "marginal_tax_rate") ?? 0.24),
    itemizes_deductions: Boolean(readSnapshotValue(snapshot, "itemizes_deductions")),
    filing_status: String(
      readSnapshotValue(snapshot, "filing_status") ?? "married_filing_jointly",
    ) as RentVsBuyInputPayload["filing_status"],
  };
}

function snapshotToForm(snapshot: Record<string, unknown>): FormState {
  return {
    targetHomePrice: String(
      Number(readSnapshotValue(snapshot, "target_home_price_cents") ?? 0) / 100,
    ),
    downPayment: String(Number(readSnapshotValue(snapshot, "down_payment_cents") ?? 0) / 100),
    loanTermYears: String(
      readSnapshotValue(snapshot, "loan_term_years") ?? "30",
    ) as "15" | "30",
    expectedYearsInHome: String(readSnapshotValue(snapshot, "expected_years_in_home") ?? "7"),
    monthlyRent: String(
      Number(readSnapshotValue(snapshot, "current_monthly_rent_cents") ?? 0) / 100,
    ),
    annualIncome: String(
      Number(readSnapshotValue(snapshot, "annual_household_income_cents") ?? 0) / 100,
    ),
    currentSavings: String(
      Number(readSnapshotValue(snapshot, "current_savings_cents") ?? 0) / 100,
    ),
    monthlySavings: String(
      Number(readSnapshotValue(snapshot, "monthly_savings_cents") ?? 0) / 100,
    ),
    appreciationRate: String(
      Number(readSnapshotValue(snapshot, "expected_home_appreciation_rate") ?? 0) * 100,
    ),
    investmentReturnRate: String(
      Number(readSnapshotValue(snapshot, "expected_investment_return_rate") ?? 0) * 100,
    ),
    riskProfile: String(
      readSnapshotValue(snapshot, "risk_profile") ?? "moderate",
    ) as FormState["riskProfile"],
    lossBehavior: String(
      readSnapshotValue(snapshot, "loss_behavior") ?? "hold",
    ) as FormState["lossBehavior"],
    incomeStability: String(
      readSnapshotValue(snapshot, "income_stability") ?? "stable",
    ) as FormState["incomeStability"],
    employmentTiedToLocalEconomy: Boolean(
      readSnapshotValue(snapshot, "employment_tied_to_local_economy"),
    ),
    currentHousingStatus: String(
      readSnapshotValue(snapshot, "current_housing_status") ?? "renting",
    ) as FormState["currentHousingStatus"],
    marketRegion: String(readSnapshotValue(snapshot, "market_region") ?? "national"),
    marginalTaxRate: String(
      Number(readSnapshotValue(snapshot, "marginal_tax_rate") ?? 0.24) * 100,
    ),
    itemizesDeductions: Boolean(readSnapshotValue(snapshot, "itemizes_deductions")),
    filingStatus: String(
      readSnapshotValue(snapshot, "filing_status") ?? "married_filing_jointly",
    ) as FormState["filingStatus"],
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

function currentAssumptionsToForm(payload: CurrentAssumptionsEnvelope): AssumptionFormState {
  return snapshotToAssumptionForm(payload.assumptions as unknown as Record<string, unknown>);
}

function currentAssumptionsToBaseline(
  payload: CurrentAssumptionsEnvelope | null,
): AssumptionBaseline | null {
  if (payload === null) {
    return null;
  }
  return {
    assumptionsSnapshot: payload.assumptions as Record<string, unknown>,
    auditTrail: payload.audit_trail,
    assumptionForm: currentAssumptionsToForm(payload),
  };
}

function scenarioToBaseline(scenario: ScenarioEnvelope | null): AssumptionBaseline | null {
  if (scenario === null) {
    return null;
  }
  return {
    assumptionsSnapshot: scenario.assumptions_snapshot,
    auditTrail: scenario.analysis.audit_trail,
    assumptionForm: snapshotToAssumptionForm(scenario.assumptions_snapshot),
  };
}

// ── verdict helpers ───────────────────────────────────────────────────────────

function verdictConfig(prob: number): {
  label: string;
  headline: string;
  color: string;
  bg: string;
  border: string;
} {
  if (prob >= 0.60) {
    return {
      label: "Buying is the stronger move",
      headline: `Buying outperforms renting in ${formatPercent(prob)} of simulated futures.`,
      color: "var(--accent)",
      bg: "rgba(36, 71, 55, 0.06)",
      border: "rgba(36, 71, 55, 0.18)",
    };
  }
  if (prob <= 0.40) {
    return {
      label: "Renting is the stronger move",
      headline: `Renting outperforms buying in ${formatPercent(1 - prob)} of simulated futures.`,
      color: "var(--danger)",
      bg: "rgba(140, 47, 61, 0.06)",
      border: "rgba(140, 47, 61, 0.18)",
    };
  }
  return {
    label: "This is a close call",
    headline: `Neither option dominates — buying wins in ${formatPercent(prob)} of futures, renting in the rest.`,
    color: "var(--muted)",
    bg: "var(--surface-soft)",
    border: "rgba(23, 34, 29, 0.12)",
  };
}

// ── main app ──────────────────────────────────────────────────────────────────

function App() {
  const [activeModule, setActiveModule] = useState<ModuleId>("rent-vs-buy");
  const [form, setForm] = useState<FormState>(defaultFormState);
  const [retirementForm, setRetirementForm] = useState<RetirementFormState>(
    defaultRetirementFormState,
  );
  const [assumptionForm, setAssumptionForm] = useState<AssumptionFormState>(defaultAssumptionFormState);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showAssumptions, setShowAssumptions] = useState(false);

  const [analysisEnvelope, setAnalysisEnvelope] = useState<AnalysisEnvelope | null>(null);
  const [retirementAnalysisEnvelope, setRetirementAnalysisEnvelope] =
    useState<RetirementAnalysisEnvelope | null>(null);
  const [currentAssumptions, setCurrentAssumptions] = useState<CurrentAssumptionsEnvelope | null>(null);
  const [savedScenarios, setSavedScenarios] = useState<ScenarioEnvelope[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null);
  const [userId, setUserId] = useState("");

  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [assumptionError, setAssumptionError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);

  // ── init user id ──
  useEffect(() => {
    const stored = window.localStorage.getItem("ffc-user-id");
    if (stored) {
      setUserId(stored);
      return;
    }
    const generated = `ffc-${crypto.randomUUID()}`;
    window.localStorage.setItem("ffc-user-id", generated);
    setUserId(generated);
  }, []);

  useEffect(() => {
    void getCurrentRentVsBuyAssumptions()
      .then((payload) => {
        startTransition(() => {
          setCurrentAssumptions(payload);
          setAssumptionForm(currentAssumptionsToForm(payload));
          setForm((current) => ({
            ...current,
            appreciationRate: rateToPercentString(
              payload.assumptions.monte_carlo.annual_appreciation_mean,
              1,
            ),
          }));
        });
      })
      .catch(() => {
        setAssumptionError("Live defaults could not be refreshed. Using local fallback assumptions.");
      });
  }, []);

  // ── load saved scenarios ──
  useEffect(() => {
    if (!userId) return;
    void listScenarios(userId)
      .then((r) => {
        startTransition(() => setSavedScenarios(r.items));
      })
      .catch(() => {
        setSaveError("Saved scenarios could not be loaded.");
      });
  }, [userId]);

  const selectedScenario =
    savedScenarios.find((s) => s.scenario_id === selectedScenarioId) ?? null;
  const assumptionBaseline =
    scenarioToBaseline(selectedScenario) ?? currentAssumptionsToBaseline(currentAssumptions);
  const activeAnalysis = selectedScenario?.analysis ?? analysisEnvelope?.analysis ?? null;
  const activeRetirementAnalysis = retirementAnalysisEnvelope?.analysis ?? null;
  const activeModelVersion =
    selectedScenario?.model_version ?? analysisEnvelope?.model_version ?? null;
  const costBreakdown = activeAnalysis?.deterministic.first_year_cost_breakdown ?? null;
  const yearlyRows = activeAnalysis?.deterministic.yearly_rows ?? [];
  const hasResult = activeAnalysis !== null;

  // ── handlers ──
  async function handleAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAnalysisError(null);
    setSaveSuccess(false);
    setIsAnalyzing(true);
    try {
      const request = buildAnalyzeRequestPayload(form, assumptionForm, assumptionBaseline);
      setSelectedScenarioId(null);
      const r = await analyzeRentVsBuy(request);
      startTransition(() => setAnalysisEnvelope(r));
    } catch (e: unknown) {
      setAnalysisError(e instanceof Error ? e.message : "Analysis failed.");
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function handleRetirementAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAnalysisError(null);
    setIsAnalyzing(true);
    try {
      const response = await analyzeRetirementSurvival({
        input: buildRetirementPayload(retirementForm),
        simulation_seed: 7,
      });
      startTransition(() => setRetirementAnalysisEnvelope(response));
    } catch (e: unknown) {
      setAnalysisError(e instanceof Error ? e.message : "Analysis failed.");
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function handleSaveScenario() {
    if (!userId) return;
    setSaveError(null);
    setSaveSuccess(false);
    setIsSaving(true);
    try {
      const r = await saveRentVsBuyScenario(
        buildScenarioPayload(form, assumptionForm, userId, assumptionBaseline),
      );
      startTransition(() => {
        setSavedScenarios((cur) => [
          r,
          ...cur.filter((s) => s.scenario_id !== r.scenario_id),
        ]);
        setSelectedScenarioId(r.scenario_id);
        setAnalysisEnvelope(null);
        setSaveSuccess(true);
      });
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "Save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDownloadReport() {
    setSaveError(null);
    setIsGeneratingReport(true);
    try {
      const r = await buildRentVsBuyReport({
        input: selectedScenario
          ? snapshotToPayload(selectedScenario.inputs_snapshot)
          : buildPayload(form),
        simulation_seed: 7,
        assumption_overrides: buildAssumptionOverrides(assumptionForm, assumptionBaseline),
        assumptions_snapshot: assumptionBaseline?.assumptionsSnapshot,
        audit_trail_snapshot: assumptionBaseline?.auditTrail,
      });
      const [{ pdf }, { RentVsBuyReportDocument }] = await Promise.all([
        import("@react-pdf/renderer"),
        import("./ReportDocument"),
      ]);
      const blob = await pdf(<RentVsBuyReportDocument report={r.report} />).toBlob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `family-financial-compass-${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "Report generation failed.");
    } finally {
      setIsGeneratingReport(false);
    }
  }

  const activeModuleMeta = modules.find((m) => m.id === activeModule)!;

  return (
    <div className="app-shell">
      {/* ── SIDEBAR ── */}
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__eyebrow">Family Financial Compass</span>
          <h1>Decision Engines</h1>
          <p>One engine at a time. Inputs on demand. Math first.</p>
        </div>

        <nav className="module-nav" aria-label="Decision engines">
          {modules.map((m) => (
            <button
              key={m.id}
              type="button"
              className={`module-nav__item${m.id === activeModule ? " module-nav__item--active" : ""}`}
              onClick={() => setActiveModule(m.id)}
            >
              <strong>
                {m.label}&ensp;
                <span className={`badge badge--${m.status}`}>{m.status}</span>
              </strong>
              <span>{m.description}</span>
            </button>
          ))}
        </nav>

        {activeModule === "rent-vs-buy" && (
          <section className="sidebar-card">
            <h2>Recent saved</h2>
            {savedScenarios.length === 0 ? (
              <p>No saved scenarios yet.</p>
            ) : (
              savedScenarios.slice(0, 5).map((s) => (
                <button
                  key={s.scenario_id}
                  type="button"
                  className={`saved-item${
                    s.scenario_id === selectedScenarioId ? " saved-item--active" : ""
                  }`}
                  onClick={() => {
                    setSelectedScenarioId(s.scenario_id);
                    setAnalysisEnvelope(null);
                    setSaveSuccess(false);
                    setForm(snapshotToForm(s.inputs_snapshot));
                    setAssumptionForm(snapshotToAssumptionForm(s.assumptions_snapshot));
                  }}
                >
                  <strong>
                    {formatCurrency(
                      Number(s.inputs_snapshot.target_home_price_cents ?? 0),
                    )}{" "}
                    · {String(s.inputs_snapshot.expected_years_in_home ?? "")} yr plan
                  </strong>
                  <span>
                    {formatPercent(s.analysis.monte_carlo.probability_buy_beats_rent)} buy
                    wins · {formatDate(s.created_at)}
                  </span>
                </button>
              ))
            )}
          </section>
        )}
      </aside>

      {/* ── MAIN ── */}
      <main className="main-pane">
        <header className="main-header">
          <div>
            <span className="main-header__eyebrow">
              {activeModuleMeta.status === "live" ? "Live engine" : "Planned engine"}
            </span>
            <h2>{activeModuleMeta.label}</h2>
          </div>
          <p>{activeModuleMeta.description}</p>
        </header>

        {activeModule === "rent-vs-buy" ? (
          <div className="rent-layout">
            {/* ── INPUT PANEL ── */}
            <section className="panel">
              <div className="panel__header">
                <div>
                  <span className="panel__eyebrow">Inputs</span>
                  <h3>The numbers</h3>
                </div>
                <p>
                  Only inputs that materially move the result are shown here. Everything
                  else uses calibrated, sourced defaults.
                </p>
              </div>

              <form className="form-grid" onSubmit={handleAnalyze}>
                {/* ── The home ── */}
                <p className="form-section-label">The home</p>
                <NumField label="Home price" name="targetHomePrice" value={form.targetHomePrice} onChange={setForm} suffix="USD" />
                <NumField label="Down payment" name="downPayment" value={form.downPayment} onChange={setForm} suffix="USD" />
                <div className="form-two-col">
                  <SelectField
                    label="Loan term"
                    value={form.loanTermYears}
                    onChange={(v) => setForm((f) => ({ ...f, loanTermYears: v as "15" | "30" }))}
                    options={[
                      { value: "30", label: "30 years" },
                      { value: "15", label: "15 years" },
                    ]}
                  />
                  <NumField label="Years planned" name="expectedYearsInHome" value={form.expectedYearsInHome} onChange={setForm} suffix="yrs" />
                </div>

                {/* ── Your money ── */}
                <p className="form-section-label">Your money</p>
                <div className="form-two-col">
                  <NumField label="Current rent" name="monthlyRent" value={form.monthlyRent} onChange={setForm} suffix="USD/mo" />
                  <NumField label="Annual income" name="annualIncome" value={form.annualIncome} onChange={setForm} suffix="USD" />
                </div>
                <div className="form-two-col">
                  <NumField label="Current savings" name="currentSavings" value={form.currentSavings} onChange={setForm} suffix="USD" />
                  <NumField label="Monthly savings" name="monthlySavings" value={form.monthlySavings} onChange={setForm} suffix="USD/mo" />
                </div>

                {/* ── Market ── */}
                <p className="form-section-label">Market</p>
                <SelectField
                  label="Region"
                  value={form.marketRegion}
                  onChange={(v) => setForm((f) => ({ ...f, marketRegion: v }))}
                  options={[
                    { value: "national", label: "National" },
                    { value: "coastal_high_cost", label: "Coastal — high cost" },
                    { value: "midwest_stable", label: "Midwest — stable" },
                    { value: "sunbelt_growth", label: "Sunbelt — growth" },
                  ]}
                />
                <div className="form-two-col">
                  <NumField label="Home appreciation" name="appreciationRate" value={form.appreciationRate} onChange={setForm} suffix="%/yr" step={0.1} />
                  <NumField label="Investment return" name="investmentReturnRate" value={form.investmentReturnRate} onChange={setForm} suffix="%/yr" step={0.1} />
                </div>

                {/* ── Advanced toggle ── */}
                <button
                  type="button"
                  className="advance-toggle"
                  onClick={() => setShowAssumptions((v) => !v)}
                >
                  <span>{showAssumptions ? "▾" : "▸"}</span>
                  Model assumptions
                  {!showAssumptions && (
                    <span style={{ fontWeight: 400, opacity: 0.65 }}>
                      &ensp;(live defaults + sliders)
                    </span>
                  )}
                </button>

                {showAssumptions && (
                  <div className="assumption-card">
                    <div className="assumption-card__header">
                      <div>
                        <strong>Current defaults</strong>
                        <p>
                          {selectedScenario
                            ? "Using the saved scenario's assumption snapshot."
                            : currentAssumptions
                            ? `Loaded from ${currentAssumptions.source} as of ${formatDate(currentAssumptions.cache_date)}.`
                            : "Using local fallback defaults until the live assumption feed responds."}
                        </p>
                      </div>
                    </div>
                    {assumptionError && <p className="message message--error">{assumptionError}</p>}
                    <div className="assumption-grid">
                      <RangeField
                        label="Mortgage rate"
                        value={assumptionForm.mortgageRate}
                        min={3}
                        max={10}
                        step={0.01}
                        suffix="%"
                        onChange={(value) => setAssumptionForm((f) => ({ ...f, mortgageRate: value }))}
                      />
                      <RangeField
                        label="Rent growth"
                        value={assumptionForm.rentGrowthRate}
                        min={0}
                        max={8}
                        step={0.1}
                        suffix="%"
                        onChange={(value) => setAssumptionForm((f) => ({ ...f, rentGrowthRate: value }))}
                      />
                      <RangeField
                        label="Property tax"
                        value={assumptionForm.propertyTaxRate}
                        min={0}
                        max={4}
                        step={0.01}
                        suffix="%"
                        onChange={(value) => setAssumptionForm((f) => ({ ...f, propertyTaxRate: value }))}
                      />
                      <RangeField
                        label="Home insurance"
                        value={assumptionForm.monthlyHomeInsurance}
                        min={100}
                        max={600}
                        step={5}
                        prefix="$"
                        suffix="/mo"
                        onChange={(value) => setAssumptionForm((f) => ({ ...f, monthlyHomeInsurance: value }))}
                      />
                      <RangeField
                        label="Maintenance"
                        value={assumptionForm.maintenanceRate}
                        min={0}
                        max={3}
                        step={0.1}
                        suffix="%"
                        onChange={(value) => setAssumptionForm((f) => ({ ...f, maintenanceRate: value }))}
                      />
                      <RangeField
                        label="Buyer closing costs"
                        value={assumptionForm.buyerClosingRate}
                        min={0}
                        max={6}
                        step={0.1}
                        suffix="%"
                        onChange={(value) => setAssumptionForm((f) => ({ ...f, buyerClosingRate: value }))}
                      />
                      <RangeField
                        label="Seller closing"
                        value={assumptionForm.sellerClosingRate}
                        min={0}
                        max={10}
                        step={0.1}
                        suffix="%"
                        onChange={(value) => setAssumptionForm((f) => ({ ...f, sellerClosingRate: value }))}
                      />
                    </div>
                  </div>
                )}

                <button
                  type="button"
                  className="advance-toggle"
                  onClick={() => setShowAdvanced((v) => !v)}
                >
                  <span>{showAdvanced ? "▾" : "▸"}</span>
                  Tax &amp; profile
                  {!showAdvanced && (
                    <span style={{ fontWeight: 400, opacity: 0.65 }}>&ensp;(advanced)</span>
                  )}
                </button>

                {showAdvanced && (
                  <>
                    <p className="form-section-label">Tax profile</p>
                    <div className="form-two-col">
                      <NumField label="Marginal tax rate" name="marginalTaxRate" value={form.marginalTaxRate} onChange={setForm} suffix="%" step={1} />
                      <SelectField
                        label="Filing status"
                        value={form.filingStatus}
                        onChange={(v) =>
                          setForm((f) => ({
                            ...f,
                            filingStatus: v as FormState["filingStatus"],
                          }))
                        }
                        options={[
                          { value: "married_filing_jointly", label: "Married filing jointly" },
                          { value: "single", label: "Single" },
                        ]}
                      />
                    </div>
                    <SelectField
                      label="Itemizes deductions"
                      value={form.itemizesDeductions ? "yes" : "no"}
                      onChange={(v) =>
                        setForm((f) => ({ ...f, itemizesDeductions: v === "yes" }))
                      }
                      options={[
                        { value: "no", label: "No — takes standard deduction" },
                        { value: "yes", label: "Yes — itemizes" },
                      ]}
                    />

                    <p className="form-section-label">Behavior &amp; profile</p>
                    <div className="form-two-col">
                      <SelectField
                        label="Risk tolerance"
                        value={form.riskProfile}
                        onChange={(v) =>
                          setForm((f) => ({
                            ...f,
                            riskProfile: v as FormState["riskProfile"],
                          }))
                        }
                        options={[
                          { value: "conservative", label: "Conservative" },
                          { value: "moderate", label: "Moderate" },
                          { value: "aggressive", label: "Aggressive" },
                        ]}
                      />
                      <SelectField
                        label="If markets crash"
                        value={form.lossBehavior}
                        onChange={(v) =>
                          setForm((f) => ({
                            ...f,
                            lossBehavior: v as FormState["lossBehavior"],
                          }))
                        }
                        options={[
                          { value: "hold", label: "Hold steady" },
                          { value: "sell_to_cash", label: "Sell to cash" },
                          { value: "buy_more", label: "Buy more" },
                        ]}
                      />
                    </div>
                    <div className="form-two-col">
                      <SelectField
                        label="Income type"
                        value={form.incomeStability}
                        onChange={(v) =>
                          setForm((f) => ({
                            ...f,
                            incomeStability: v as FormState["incomeStability"],
                          }))
                        }
                        options={[
                          { value: "stable", label: "Stable — salary" },
                          { value: "variable", label: "Variable — freelance/commission" },
                        ]}
                      />
                      <SelectField
                        label="Job tied to local area"
                        value={form.employmentTiedToLocalEconomy ? "yes" : "no"}
                        onChange={(v) =>
                          setForm((f) => ({
                            ...f,
                            employmentTiedToLocalEconomy: v === "yes",
                          }))
                        }
                        options={[
                          { value: "no", label: "No" },
                          { value: "yes", label: "Yes" },
                        ]}
                      />
                    </div>
                  </>
                )}

                {/* ── Actions ── */}
                <div className="form-actions">
                  <button type="submit" className="button button--primary" disabled={isAnalyzing} style={{ flex: 1 }}>
                    {isAnalyzing ? "Running 10,000 scenarios…" : "Run analysis"}
                  </button>
                  <button
                    type="button"
                    className="button button--secondary"
                    onClick={handleSaveScenario}
                    disabled={isSaving || !hasResult}
                    title={hasResult ? "Save this scenario" : "Run the analysis first"}
                  >
                    {isSaving ? "Saving…" : "Save"}
                  </button>
                </div>

                {analysisError && <p className="message message--error">{analysisError}</p>}
                {saveError && <p className="message message--error">{saveError}</p>}
                {saveSuccess && (
                  <p className="message" style={{ color: "var(--accent)" }}>
                    Scenario saved.
                  </p>
                )}
              </form>
            </section>

            {/* ── OUTPUT PANEL ── */}
            <section className={`panel${!hasResult ? " panel--placeholder" : ""}`}>
              {!hasResult ? (
                <EmptyOutput loading={isAnalyzing} />
              ) : (
                <OutputPanel
                  activeAnalysis={activeAnalysis!}
                  activeModelVersion={activeModelVersion}
                  costBreakdown={costBreakdown}
                  yearlyRows={yearlyRows}
                  isGeneratingReport={isGeneratingReport}
                  onDownloadReport={handleDownloadReport}
                />
              )}
            </section>
          </div>
        ) : activeModule === "retirement-survival" ? (
          <RetirementLayout
            form={retirementForm}
            setForm={setRetirementForm}
            analysis={activeRetirementAnalysis}
            modelVersion={retirementAnalysisEnvelope?.model_version ?? null}
            isAnalyzing={isAnalyzing}
            analysisError={analysisError}
            onAnalyze={handleRetirementAnalyze}
          />
        ) : (
          <section className="panel panel--placeholder">
            <div className="panel__header">
              <div>
                <span className="panel__eyebrow">Not built yet</span>
                <h3>{activeModuleMeta.label}</h3>
              </div>
              <p>{activeModuleMeta.description}</p>
            </div>
            <div className="empty-state">
              <p>This engine is in the queue. Next build is Retirement Survival.</p>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

// ── output panel ──────────────────────────────────────────────────────────────

function RetirementLayout({
  form,
  setForm,
  analysis,
  modelVersion,
  isAnalyzing,
  analysisError,
  onAnalyze,
}: {
  form: RetirementFormState;
  setForm: Dispatch<SetStateAction<RetirementFormState>>;
  analysis: RetirementAnalysis | null;
  modelVersion: string | null;
  isAnalyzing: boolean;
  analysisError: string | null;
  onAnalyze: (event: FormEvent<HTMLFormElement>) => Promise<void>;
}) {
  return (
    <div className="rent-layout">
      <section className="panel">
        <div className="panel__header">
          <div>
            <span className="panel__eyebrow">Inputs</span>
            <h3>Retirement plan</h3>
          </div>
          <p>Portfolio, spending, guaranteed income, horizon, and market behavior. Nothing else.</p>
        </div>

        <form className="form-grid" onSubmit={onAnalyze}>
          <p className="form-section-label">Portfolio</p>
          <NumField label="Current portfolio" name="currentPortfolio" value={form.currentPortfolio} onChange={setForm} suffix="USD" />
          <div className="form-two-col">
            <NumField label="Annual spending" name="annualSpending" value={form.annualSpending} onChange={setForm} suffix="USD" />
            <NumField label="Guaranteed income" name="annualGuaranteedIncome" value={form.annualGuaranteedIncome} onChange={setForm} suffix="USD" />
          </div>

          <p className="form-section-label">Return assumptions</p>
          <div className="form-two-col">
            <NumField label="Retirement years" name="retirementYears" value={form.retirementYears} onChange={setForm} suffix="yrs" />
            <NumField label="Expected return" name="expectedAnnualReturn" value={form.expectedAnnualReturn} onChange={setForm} suffix="%/yr" step={0.1} />
          </div>
          <div className="form-two-col">
            <SelectField
              label="Risk tolerance"
              value={form.riskProfile}
              onChange={(value) =>
                setForm((current) => ({
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
            <SelectField
              label="If markets crash"
              value={form.lossBehavior}
              onChange={(value) =>
                setForm((current) => ({
                  ...current,
                  lossBehavior: value as RetirementFormState["lossBehavior"],
                }))
              }
              options={[
                { value: "hold", label: "Hold steady" },
                { value: "sell_to_cash", label: "Sell to cash" },
                { value: "buy_more", label: "Buy more" },
              ]}
            />
          </div>

          <div className="form-actions">
            <button type="submit" className="button button--primary" disabled={isAnalyzing} style={{ flex: 1 }}>
              {isAnalyzing ? "Running survival simulation…" : "Run analysis"}
            </button>
          </div>
          {analysisError && <p className="message message--error">{analysisError}</p>}
        </form>
      </section>

      <section className={`panel${analysis === null ? " panel--placeholder" : ""}`}>
        {analysis === null ? (
          <EmptyOutput loading={isAnalyzing} />
        ) : (
          <RetirementOutputPanel analysis={analysis} modelVersion={modelVersion} />
        )}
      </section>
    </div>
  );
}

function RetirementOutputPanel({
  analysis,
  modelVersion,
}: {
  analysis: RetirementAnalysis;
  modelVersion: string | null;
}) {
  const det = analysis.deterministic;
  const mc = analysis.monte_carlo;
  const sustainable = mc.probability_portfolio_survives >= 0.8;

  return (
    <div>
      <div className="panel__header" style={{ marginBottom: "1.2rem" }}>
        <div>
          <span className="panel__eyebrow">Output</span>
          <h3 style={{ fontFamily: "'Iowan Old Style', 'Palatino Linotype', Georgia, serif", fontSize: "1.8rem", marginTop: "0.35rem" }}>
            Retirement survival
          </h3>
        </div>
        {modelVersion && <span style={{ fontSize: "0.76rem", color: "var(--muted)" }}>v{modelVersion}</span>}
      </div>

      <div
        className="verdict-card"
        style={{
          background: sustainable ? "rgba(36, 71, 55, 0.06)" : "rgba(140, 47, 61, 0.06)",
          border: sustainable ? "1px solid rgba(36, 71, 55, 0.18)" : "1px solid rgba(140, 47, 61, 0.18)",
        }}
      >
        <p className="verdict-card__eyebrow" style={{ color: sustainable ? "var(--accent)" : "var(--danger)" }}>
          {sustainable ? "Plan is holding up" : "Plan is under strain"}
        </p>
        <p className="verdict-card__headline" style={{ fontSize: "clamp(1.25rem, 2.4vw, 1.8rem)" }}>
          Portfolio survives in {formatPercent(mc.probability_portfolio_survives)} of simulated retirement paths.
        </p>
        <p className="verdict-card__sub">
          Current withdrawal rate is {(det.current_withdrawal_rate * 100).toFixed(2)}%. The modeled 95% safe rate is {(mc.safe_withdrawal_rate_95 * 100).toFixed(2)}%.
        </p>
      </div>

      <div className="summary-grid output-section">
        <div className="summary-card">
          <span>Median ending wealth</span>
          <strong>{formatCurrency(mc.median_terminal_wealth_cents)}</strong>
        </div>
        <div className="summary-card">
          <span>Downside ending wealth</span>
          <strong style={{ color: "var(--danger)" }}>{formatCurrency(mc.p10_terminal_wealth_cents)}</strong>
        </div>
        <div className="summary-card">
          <span>Upside ending wealth</span>
          <strong style={{ color: "var(--accent)" }}>{formatCurrency(mc.p90_terminal_wealth_cents)}</strong>
        </div>
        <div className="summary-card">
          <span>Deterministic endpoint</span>
          <strong>{formatCurrency(det.terminal_wealth_cents)}</strong>
        </div>
      </div>

      <div className="detail-card output-section">
        <h4>Portfolio path by year</h4>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Yr</th>
                <th>Deterministic</th>
                <th>Median</th>
                <th>10th pct.</th>
                <th>90th pct.</th>
                <th>Deplete prob.</th>
              </tr>
            </thead>
            <tbody>
              {mc.yearly_rows.map((row) => (
                <RetirementProjectionTableRow key={row.year} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {analysis.warnings.length > 0 && (
        <div className="notice output-section">
          {analysis.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function RetirementProjectionTableRow({ row }: { row: RetirementYearProjectionRow }) {
  return (
    <tr>
      <td>{row.year}</td>
      <td>{formatCurrency(row.deterministic_portfolio_cents)}</td>
      <td>{formatCurrency(row.median_portfolio_cents)}</td>
      <td>{formatCurrency(row.p10_portfolio_cents)}</td>
      <td>{formatCurrency(row.p90_portfolio_cents)}</td>
      <td>{formatPercent(row.cumulative_depletion_probability)}</td>
    </tr>
  );
}

function EmptyOutput({ loading }: { loading: boolean }) {
  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "60vh", textAlign: "center" }}>
      <div>
        <span className="panel__eyebrow">Output</span>
        <h3 style={{
          fontFamily: "'Iowan Old Style', 'Palatino Linotype', Georgia, serif",
          fontSize: "1.8rem",
          margin: "0.35rem 0 0.75rem",
          color: "var(--ink)",
        }}>
          {loading ? "Running the model…" : "Run the model to see the result."}
        </h3>
        <p style={{ color: "var(--muted)", maxWidth: "26rem", margin: "0 auto" }}>
          {loading
            ? "Simulating 10,000 correlated economic futures. This takes a moment."
            : "Fill in the inputs on the left and press Run analysis. The output stays quiet until there is a real result to display."}
        </p>
      </div>
    </div>
  );
}

function OutputPanel({
  activeAnalysis,
  activeModelVersion,
  costBreakdown,
  yearlyRows,
  isGeneratingReport,
  onDownloadReport,
}: {
  activeAnalysis: NonNullable<AnalysisEnvelope["analysis"]>;
  activeModelVersion: string | null;
  costBreakdown: NonNullable<AnalysisEnvelope["analysis"]>["deterministic"]["first_year_cost_breakdown"] | null;
  yearlyRows: YearlyComparisonRow[];
  isGeneratingReport: boolean;
  onDownloadReport: () => void;
}) {
  const mc = activeAnalysis.monte_carlo;
  const det = activeAnalysis.deterministic;
  const prob = mc.probability_buy_beats_rent;
  const v = verdictConfig(prob);

  // Deterministic break-even
  const beMonth = det.break_even_month;
  const beYears = beMonth != null ? (beMonth / 12).toFixed(1) : null;
  const horizonYears = (det.horizon_months / 12).toFixed(0);

  // Year-one monthly costs (breakdown sums cover min(12, horizon) months)
  const firstYear = Math.min(12, det.horizon_months);
  const cbMonthly = costBreakdown
    ? {
        pi: Math.round(costBreakdown.principal_and_interest_cents / firstYear),
        tax: Math.round(costBreakdown.property_tax_cents / firstYear),
        ins: Math.round(costBreakdown.insurance_cents / firstYear),
        maint: Math.round(costBreakdown.maintenance_cents / firstYear),
        pmi: Math.round(costBreakdown.pmi_cents / firstYear),
        liq: Math.round(costBreakdown.liquidity_premium_cents / firstYear),
      }
    : null;
  const monthlyTotal = cbMonthly
    ? cbMonthly.pi + cbMonthly.tax + cbMonthly.ins + cbMonthly.maint + cbMonthly.pmi + cbMonthly.liq
    : 0;

  return (
    <div>
      {/* header */}
      <div className="panel__header" style={{ marginBottom: "1.2rem" }}>
        <div>
          <span className="panel__eyebrow">Output</span>
          <h3 style={{
            fontFamily: "'Iowan Old Style', 'Palatino Linotype', Georgia, serif",
            fontSize: "1.8rem",
            marginTop: "0.35rem",
          }}>
            The verdict
          </h3>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.4rem" }}>
          {activeModelVersion && (
            <span style={{ fontSize: "0.76rem", color: "var(--muted)" }}>v{activeModelVersion}</span>
          )}
          <button
            type="button"
            className="button button--secondary"
            onClick={onDownloadReport}
            disabled={isGeneratingReport}
            style={{ fontSize: "0.82rem", minHeight: "2.25rem", padding: "0 0.85rem" }}
          >
            {isGeneratingReport ? "Building PDF…" : "Download report"}
          </button>
        </div>
      </div>

      {/* ── VERDICT CARD ── */}
      <div
        className="verdict-card"
        style={{ background: v.bg, border: `1px solid ${v.border}` }}
      >
        <p className="verdict-card__eyebrow" style={{ color: v.color }}>{v.label}</p>
        <p className="verdict-card__headline" style={{ fontSize: "clamp(1.25rem, 2.4vw, 1.8rem)" }}>
          {v.headline}
        </p>
        <p className="verdict-card__sub">
          {beMonth != null
            ? `Break-even at month ${beMonth} (year ${beYears} of your ${horizonYears}-year plan).`
            : `No break-even within your ${horizonYears}-year horizon.`}
          {mc.break_even_ci_80[0] != null && mc.break_even_ci_80[1] != null
            ? ` 80% of scenarios break even between month ${mc.break_even_ci_80[0]} and ${mc.break_even_ci_80[1]}.`
            : ""}
        </p>
      </div>

      {/* ── KEY NUMBERS ── */}
      <div className="summary-grid output-section">
        <div className="summary-card">
          <span>Buying wins</span>
          <strong style={{ color: v.color }}>{formatPercent(prob)}</strong>
          <div className="prob-bar">
            <div
              className="prob-bar__fill"
              style={{
                width: formatPercent(prob),
                background: v.color,
              }}
            />
          </div>
        </div>
        <div className="summary-card">
          <span>Median outcome</span>
          <strong style={{
            color: mc.median_terminal_advantage_cents >= 0 ? "var(--accent)" : "var(--danger)",
          }}>
            {formatCurrency(mc.median_terminal_advantage_cents)}
          </strong>
        </div>
        <div className="summary-card">
          <span>Downside (10th pct.)</span>
          <strong style={{ color: "var(--danger)" }}>
            {formatCurrency(mc.p10_terminal_advantage_cents)}
          </strong>
        </div>
        <div className="summary-card">
          <span>Upside (90th pct.)</span>
          <strong style={{ color: "var(--accent)" }}>
            {formatCurrency(mc.p90_terminal_advantage_cents)}
          </strong>
        </div>
      </div>

      {/* ── YEAR-ONE COSTS ── */}
      {cbMonthly && (
        <div className="detail-card output-section">
          <h4>Year one — monthly cost of buying</h4>
          {([
            ["Mortgage (P+I)", cbMonthly.pi],
            ["Property tax", cbMonthly.tax],
            ["Insurance", cbMonthly.ins],
            ["Maintenance", cbMonthly.maint],
            cbMonthly.pmi > 0 ? ["PMI", cbMonthly.pmi] : null,
            ["Liquidity premium on equity", cbMonthly.liq],
          ] as Array<[string, number] | null>)
            .filter((row): row is [string, number] => row !== null)
            .map(([label, val]) => (
              <div key={label as string} className="result-row">
                <span style={{ color: "var(--muted)" }}>{label}</span>
                <span>{formatCurrency(val as number)}/mo</span>
              </div>
            ))}
          <div className="result-row result-row--total">
            <span>Total monthly housing cost</span>
            <span>{formatCurrency(monthlyTotal)}/mo</span>
          </div>
          {costBreakdown && costBreakdown.total_mortgage_interest_deduction_cents > 0 && (
            <div className="result-row result-row--credit" style={{ border: 0, paddingTop: "0.4rem" }}>
              <span>Interest deduction — full horizon est.</span>
              <span>−{formatCurrency(costBreakdown.total_mortgage_interest_deduction_cents)}</span>
            </div>
          )}
          {costBreakdown && costBreakdown.closing_costs_cents > 0 && (
            <div className="result-row" style={{ border: 0 }}>
              <span style={{ color: "var(--muted)" }}>Buyer closing costs (one-time upfront)</span>
              <span>{formatCurrency(costBreakdown.closing_costs_cents)}</span>
            </div>
          )}
        </div>
      )}

      {/* ── YEARLY NET WORTH TABLE ── */}
      {yearlyRows.length > 0 && (
        <div className="table-card output-section">
          <div className="table-card__header">
            <h4>Net worth by year — rent vs buy</h4>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Yr</th>
                  <th>Renting</th>
                  <th>Buying</th>
                  <th>Difference</th>
                </tr>
              </thead>
              <tbody>
                {yearlyRows.map((row) => (
                  <YearRow key={row.year} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── BEHAVIORAL ADJUSTMENT ── */}
      {mc.utility_adjusted_p50_advantage_cents !== mc.median_terminal_advantage_cents && (
        <div className="detail-card output-section">
          <h4>Loss-aversion adjustment (λ = 2.25)</h4>
          <div className="result-row">
            <span style={{ color: "var(--muted)" }}>Raw median outcome</span>
            <span>{formatCurrency(mc.median_terminal_advantage_cents)}</span>
          </div>
          <div className="result-row">
            <span style={{ color: "var(--muted)" }}>Behaviorally adjusted median</span>
            <span style={{
              color: mc.utility_adjusted_p50_advantage_cents < mc.median_terminal_advantage_cents
                ? "var(--danger)"
                : "var(--accent)",
            }}>
              {formatCurrency(mc.utility_adjusted_p50_advantage_cents)}
            </span>
          </div>
          <p style={{ fontSize: "0.82rem", color: "var(--muted)", margin: "0.55rem 0 0" }}>
            Losses are weighted 2.25× heavier than equivalent gains — as most households
            actually experience them. The adjusted figure is typically lower than the raw median.
          </p>
        </div>
      )}

      {/* ── WARNINGS ── */}
      {activeAnalysis.warnings.length > 0 && (
        <div className="notice output-section">
          {activeAnalysis.warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </div>
      )}
    </div>
  );
}

// ── small presentational components ──────────────────────────────────────────

function YearRow({ row }: { row: YearlyComparisonRow }) {
  const diff = row.buy_minus_rent_cents;
  const buyAhead = diff > 0;
  return (
    <tr>
      <td>{row.year}</td>
      <td>{formatCurrency(row.rent_net_worth_cents)}</td>
      <td>{formatCurrency(row.buy_net_worth_cents)}</td>
      <td style={{ color: buyAhead ? "var(--accent)" : "var(--danger)", fontWeight: 600 }}>
        {buyAhead ? "+" : ""}
        {formatCurrency(diff)}
      </td>
    </tr>
  );
}

type NumericFieldName =
  | keyof FormState
  | keyof RetirementFormState;

function NumField({
  label,
  name,
  value,
  onChange,
  suffix,
  step,
}: {
  label: string;
  name: NumericFieldName;
  value: string;
  onChange: Dispatch<SetStateAction<FormState>> | Dispatch<SetStateAction<RetirementFormState>>;
  suffix?: string;
  step?: number;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <div className="field__input">
        <input
          type="number"
          step={step ?? "any"}
          value={value}
          onChange={(e) =>
            (onChange as unknown as Dispatch<SetStateAction<Record<string, unknown>>>)
            ((current) => ({ ...current, [name]: e.target.value }))
          }
        />
        {suffix && <small>{suffix}</small>}
      </div>
    </label>
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
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <div className="field__input">
        <select value={value} onChange={(e) => onChange(e.target.value)}>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
    </label>
  );
}

function RangeField({
  label,
  value,
  min,
  max,
  step,
  onChange,
  prefix,
  suffix,
}: {
  label: string;
  value: string;
  min: number;
  max: number;
  step: number;
  onChange: (value: string) => void;
  prefix?: string;
  suffix?: string;
}) {
  return (
    <label className="range-field">
      <div className="range-field__row">
        <span>{label}</span>
        <strong>
          {prefix ?? ""}
          {value}
          {suffix ?? ""}
        </strong>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <div className="range-field__meta">
        <small>
          {prefix ?? ""}
          {min}
          {suffix ?? ""}
        </small>
        <small>
          {prefix ?? ""}
          {max}
          {suffix ?? ""}
        </small>
      </div>
    </label>
  );
}

export default App;
