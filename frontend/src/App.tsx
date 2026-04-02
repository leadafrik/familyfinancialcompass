import { startTransition, useEffect, useState } from "react";
import type { Dispatch, FormEvent, SetStateAction } from "react";

import { analyzeRentVsBuy, listScenarios, saveRentVsBuyScenario } from "./api";
import type {
  AnalysisEnvelope,
  CreateScenarioPayload,
  FilingStatus,
  FormState,
  ScenarioEnvelope,
  YearlyComparisonRow,
} from "./types";

type ModuleId =
  | "rent-vs-buy"
  | "retirement-survival"
  | "job-offer"
  | "college-vs-retirement"
  | "debt-payoff-vs-invest";

type NumericFieldName =
  | "targetHomePrice"
  | "downPayment"
  | "expectedYearsInHome"
  | "monthlyRent"
  | "annualIncome"
  | "currentSavings"
  | "monthlySavings"
  | "appreciationRate"
  | "investmentReturnRate"
  | "marginalTaxRate";

type SelectFieldName = "loanTermYears" | "marketRegion" | "filingStatus";

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
    description: "Live now. Inputs, simulation, and saved scenarios are wired end to end.",
  },
  {
    id: "retirement-survival",
    label: "Retirement Survival",
    status: "next",
    description: "Next engine. Sequence-of-returns survival and safe withdrawal planning.",
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

function dollarsToCents(value: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return Math.round(parsed * 100);
}

function percentToRate(value: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return parsed / 100;
}

function formatCurrency(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function formatPercent(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatMonth(month: number | null): string {
  if (month === null) {
    return "No break-even inside horizon";
  }
  return `Month ${month}`;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function buildPayload(form: FormState) {
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

function buildScenarioPayload(form: FormState, userId: string): CreateScenarioPayload {
  return {
    input: buildPayload(form),
    simulation_seed: 7,
    user_id: userId,
    idempotency_key: crypto.randomUUID(),
  };
}

function verdict(probability: number): string {
  if (probability >= 0.65) {
    return "Buying wins in most modeled paths.";
  }
  if (probability <= 0.35) {
    return "Renting protects capital in most modeled paths.";
  }
  return "This decision is close. Treat the downside carefully.";
}

function App() {
  const [activeModule, setActiveModule] = useState<ModuleId>("rent-vs-buy");
  const [form, setForm] = useState<FormState>(defaultFormState);
  const [analysisEnvelope, setAnalysisEnvelope] = useState<AnalysisEnvelope | null>(null);
  const [savedScenarios, setSavedScenarios] = useState<ScenarioEnvelope[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null);
  const [userId, setUserId] = useState("");
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    const storedUserId = window.localStorage.getItem("ffc-user-id");
    if (storedUserId) {
      setUserId(storedUserId);
      return;
    }

    const generatedUserId = `ffc-${crypto.randomUUID()}`;
    window.localStorage.setItem("ffc-user-id", generatedUserId);
    setUserId(generatedUserId);
  }, []);

  useEffect(() => {
    if (!userId) {
      return;
    }

    void listScenarios(userId)
      .then((response) => {
        startTransition(() => {
          setSavedScenarios(response.items);
        });
      })
      .catch(() => {
        setSaveError("Saved scenarios could not be loaded.");
      });
  }, [userId]);

  const selectedScenario = savedScenarios.find((scenario) => scenario.scenario_id === selectedScenarioId) ?? null;
  const activeAnalysis = selectedScenario?.analysis ?? analysisEnvelope?.analysis ?? null;
  const activeModelVersion = selectedScenario?.model_version ?? analysisEnvelope?.model_version ?? null;
  const costBreakdown = activeAnalysis?.deterministic.first_year_cost_breakdown ?? null;
  const yearlyRows = activeAnalysis?.deterministic.yearly_rows ?? [];

  async function handleAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAnalysisError(null);
    setIsAnalyzing(true);
    setSelectedScenarioId(null);

    try {
      const response = await analyzeRentVsBuy({
        input: buildPayload(form),
        simulation_seed: 7,
      });
      startTransition(() => {
        setAnalysisEnvelope(response);
      });
    } catch (error: unknown) {
      setAnalysisError(error instanceof Error ? error.message : "Analysis failed.");
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function handleSaveScenario() {
    if (!userId) {
      setSaveError("User identity is not ready yet.");
      return;
    }

    setSaveError(null);
    setIsSaving(true);

    try {
      const response = await saveRentVsBuyScenario(buildScenarioPayload(form, userId));
      startTransition(() => {
        setSavedScenarios((current) => [response, ...current.filter((item) => item.scenario_id !== response.scenario_id)]);
        setSelectedScenarioId(response.scenario_id);
        setAnalysisEnvelope(null);
      });
    } catch (error: unknown) {
      setSaveError(error instanceof Error ? error.message : "Save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  const activeModuleMeta = modules.find((module) => module.id === activeModule)!;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__eyebrow">Family Financial Compass</span>
          <h1>Decision Engines</h1>
          <p>One engine at a time. Inputs on demand. Math first.</p>
        </div>

        <nav className="module-nav" aria-label="Decision engines">
          {modules.map((module) => (
            <button
              key={module.id}
              type="button"
              className={`module-nav__item${module.id === activeModule ? " module-nav__item--active" : ""}`}
              onClick={() => setActiveModule(module.id)}
            >
              <strong>{module.label}</strong>
              <span>{module.status}</span>
            </button>
          ))}
        </nav>

        {activeModule === "rent-vs-buy" ? (
          <section className="sidebar-card">
            <h2>Recent saved</h2>
            {savedScenarios.length === 0 ? <p>No saved scenarios yet.</p> : null}
            {savedScenarios.slice(0, 4).map((scenario) => (
              <button
                key={scenario.scenario_id}
                type="button"
                className={`saved-item${scenario.scenario_id === selectedScenarioId ? " saved-item--active" : ""}`}
                onClick={() => {
                  setSelectedScenarioId(scenario.scenario_id);
                  setAnalysisEnvelope(null);
                }}
              >
                <strong>{formatDate(scenario.created_at)}</strong>
                <span>{formatPercent(scenario.analysis.monte_carlo.probability_buy_beats_rent)} buy-win probability</span>
              </button>
            ))}
          </section>
        ) : (
          <section className="sidebar-card">
            <h2>Next up</h2>
            <p>{activeModuleMeta.description}</p>
          </section>
        )}
      </aside>

      <main className="main-pane">
        <header className="main-header">
          <div>
            <span className="main-header__eyebrow">{activeModuleMeta.status === "live" ? "Live engine" : "Planned engine"}</span>
            <h2>{activeModuleMeta.label}</h2>
          </div>
          <p>{activeModuleMeta.description}</p>
        </header>

        {activeModule === "rent-vs-buy" ? (
          <div className="rent-layout">
            <section className="panel">
              <div className="panel__header">
                <div>
                  <span className="panel__eyebrow">Inputs</span>
                  <h3>Run the model</h3>
                </div>
                <p>Only the inputs that materially move the result are exposed here. Everything else stays on sensible engine defaults.</p>
              </div>

              <form className="form-grid" onSubmit={handleAnalyze}>
                <Field label="Home price" name="targetHomePrice" value={form.targetHomePrice} onChange={setForm} suffix="USD" />
                <Field label="Down payment" name="downPayment" value={form.downPayment} onChange={setForm} suffix="USD" />
                <Field label="Years in home" name="expectedYearsInHome" value={form.expectedYearsInHome} onChange={setForm} suffix="years" />
                <Field label="Monthly rent" name="monthlyRent" value={form.monthlyRent} onChange={setForm} suffix="USD" />
                <Field label="Current savings" name="currentSavings" value={form.currentSavings} onChange={setForm} suffix="USD" />
                <Field label="Monthly savings" name="monthlySavings" value={form.monthlySavings} onChange={setForm} suffix="USD" />
                <Field label="Annual income" name="annualIncome" value={form.annualIncome} onChange={setForm} suffix="USD" />
                <SelectField
                  label="Loan term"
                  name="loanTermYears"
                  value={form.loanTermYears}
                  onChange={setForm}
                  options={[
                    { value: "30", label: "30 years" },
                    { value: "15", label: "15 years" },
                  ]}
                />
                <Field label="Home appreciation" name="appreciationRate" value={form.appreciationRate} onChange={setForm} suffix="%" />
                <Field label="Investment return" name="investmentReturnRate" value={form.investmentReturnRate} onChange={setForm} suffix="%" />
                <Field label="Marginal tax rate" name="marginalTaxRate" value={form.marginalTaxRate} onChange={setForm} suffix="%" />
                <SelectField
                  label="Market region"
                  name="marketRegion"
                  value={form.marketRegion}
                  onChange={setForm}
                  options={[
                    { value: "national", label: "National" },
                    { value: "coastal_high_cost", label: "Coastal high cost" },
                    { value: "midwest_stable", label: "Midwest stable" },
                    { value: "sunbelt_growth", label: "Sunbelt growth" },
                  ]}
                />
                <SelectField
                  label="Filing status"
                  name="filingStatus"
                  value={form.filingStatus}
                  onChange={setForm}
                  options={[
                    { value: "married_filing_jointly", label: "Married filing jointly" },
                    { value: "single", label: "Single" },
                  ]}
                />

                <div className="form-actions">
                  <button type="submit" className="button button--primary" disabled={isAnalyzing}>
                    {isAnalyzing ? "Running..." : "Run analysis"}
                  </button>
                  <button type="button" className="button button--secondary" onClick={handleSaveScenario} disabled={isSaving}>
                    {isSaving ? "Saving..." : "Save scenario"}
                  </button>
                </div>
                {analysisError ? <p className="message message--error">{analysisError}</p> : null}
                {saveError ? <p className="message message--error">{saveError}</p> : null}
              </form>
            </section>

            <section className="panel">
              <div className="panel__header">
                <div>
                  <span className="panel__eyebrow">Output</span>
                  <h3>{activeAnalysis ? verdict(activeAnalysis.monte_carlo.probability_buy_beats_rent) : "Run the model to see the result."}</h3>
                </div>
                {activeModelVersion ? <p>Model version {activeModelVersion}</p> : <p>The output view stays quiet until there is a real run to display.</p>}
              </div>

              {activeAnalysis ? (
                <>
                  <div className="summary-grid">
                    <SummaryCard
                      label="Probability buying wins"
                      value={formatPercent(activeAnalysis.monte_carlo.probability_buy_beats_rent)}
                    />
                    <SummaryCard
                      label="Utility-adjusted median"
                      value={formatCurrency(activeAnalysis.monte_carlo.utility_adjusted_p50_advantage_cents)}
                    />
                    <SummaryCard
                      label="Break-even"
                      value={`${formatMonth(activeAnalysis.monte_carlo.break_even_ci_80[0])} to ${formatMonth(activeAnalysis.monte_carlo.break_even_ci_80[1])}`}
                    />
                    <SummaryCard
                      label="Downside case"
                      value={formatCurrency(activeAnalysis.monte_carlo.p10_terminal_advantage_cents)}
                    />
                  </div>

                  <div className="detail-stack">
                    <DetailCard title="Distribution">
                      <ResultRow label="Downside" value={formatCurrency(activeAnalysis.monte_carlo.p10_terminal_advantage_cents)} />
                      <ResultRow label="Median" value={formatCurrency(activeAnalysis.monte_carlo.median_terminal_advantage_cents)} />
                      <ResultRow label="Upside" value={formatCurrency(activeAnalysis.monte_carlo.p90_terminal_advantage_cents)} />
                    </DetailCard>

                    <DetailCard title="First-year buyer costs">
                      <ResultRow label="Principal + interest" value={formatCurrency(costBreakdown?.principal_and_interest_cents ?? 0)} />
                      <ResultRow label="Property tax" value={formatCurrency(costBreakdown?.property_tax_cents ?? 0)} />
                      <ResultRow label="Insurance" value={formatCurrency(costBreakdown?.insurance_cents ?? 0)} />
                      <ResultRow label="Maintenance" value={formatCurrency(costBreakdown?.maintenance_cents ?? 0)} />
                      <ResultRow label="Liquidity premium" value={formatCurrency(costBreakdown?.liquidity_premium_cents ?? 0)} />
                    </DetailCard>
                  </div>

                  {activeAnalysis.warnings.length > 0 ? (
                    <div className="notice">
                      {activeAnalysis.warnings.map((warning) => (
                        <p key={warning}>{warning}</p>
                      ))}
                    </div>
                  ) : null}

                  <div className="table-card">
                    <div className="table-card__header">
                      <h4>Yearly path</h4>
                    </div>
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Year</th>
                            <th>Buy minus rent</th>
                            <th>Home equity</th>
                            <th>Buy liquid</th>
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
                </>
              ) : (
                <div className="empty-state">
                  <p>Pick the inputs, run the engine, then read the result.</p>
                </div>
              )}
            </section>
          </div>
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
              <p>This stays intentionally empty until the engine exists. Next build should be Retirement Survival.</p>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

interface FieldProps {
  label: string;
  name: NumericFieldName;
  value: string;
  onChange: Dispatch<SetStateAction<FormState>>;
  suffix?: string;
}

function Field({ label, name, value, onChange, suffix }: FieldProps) {
  return (
    <label className="field">
      <span>{label}</span>
      <div className="field__input">
        <input
          type="number"
          step="any"
          value={value}
          onChange={(event) => onChange((current) => ({ ...current, [name]: event.target.value }))}
        />
        {suffix ? <small>{suffix}</small> : null}
      </div>
    </label>
  );
}

interface SelectFieldProps {
  label: string;
  name: SelectFieldName;
  value: string;
  onChange: Dispatch<SetStateAction<FormState>>;
  options: Array<{ value: string; label: string }>;
}

function SelectField({ label, name, value, onChange, options }: SelectFieldProps) {
  return (
    <label className="field">
      <span>{label}</span>
      <div className="field__input">
        <select value={value} onChange={(event) => onChange((current) => ({ ...current, [name]: event.target.value as FormState[SelectFieldName] }))}>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
    </label>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="summary-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DetailCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="detail-card">
      <h4>{title}</h4>
      {children}
    </div>
  );
}

function ResultRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="result-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function YearRow({ row }: { row: YearlyComparisonRow }) {
  return (
    <tr>
      <td>{row.year}</td>
      <td>{formatCurrency(row.buy_minus_rent_cents)}</td>
      <td>{formatCurrency(row.home_equity_cents)}</td>
      <td>{formatCurrency(row.buy_liquid_portfolio_cents)}</td>
    </tr>
  );
}

export default App;
