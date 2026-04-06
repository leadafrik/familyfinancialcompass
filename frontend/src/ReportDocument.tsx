import { Document, Page, StyleSheet, Text, View } from "@react-pdf/renderer";

import type {
  CollegeVsRetirementReport,
  JobOfferReport,
  RentVsBuyReport,
  ReportAuditTrailRow,
  ReportInputsSummaryRow,
  ReportSensitivityRow,
  ReportYearRow,
  RetirementSurvivalReport,
} from "./types";

const styles = StyleSheet.create({
  page: {
    paddingTop: 34,
    paddingBottom: 42,
    paddingHorizontal: 34,
    fontSize: 10,
    fontFamily: "Helvetica",
    color: "#17221d",
    backgroundColor: "#fbf8f2",
  },
  overline: {
    fontSize: 9,
    textTransform: "uppercase",
    letterSpacing: 1.1,
    color: "#506259",
    marginBottom: 4,
  },
  title: {
    fontSize: 22,
    fontFamily: "Helvetica-Bold",
    marginBottom: 8,
  },
  subtitle: {
    color: "#5f6f67",
    lineHeight: 1.45,
    marginBottom: 12,
  },
  metaLine: {
    color: "#5f6f67",
    marginBottom: 12,
  },
  paragraph: {
    lineHeight: 1.45,
    marginBottom: 10,
  },
  disclaimer: {
    borderWidth: 1,
    borderColor: "#d9d4ca",
    backgroundColor: "#f2ede3",
    padding: 12,
    lineHeight: 1.45,
    marginBottom: 16,
  },
  verdictBox: {
    borderWidth: 1,
    borderColor: "#274737",
    backgroundColor: "#edf4ef",
    borderRadius: 8,
    padding: 14,
    marginBottom: 14,
  },
  verdictHeadline: {
    fontSize: 18,
    fontFamily: "Helvetica-Bold",
    color: "#274737",
    marginBottom: 6,
  },
  metricRow: {
    flexDirection: "row",
    marginTop: 8,
  },
  metricBlock: {
    width: "50%",
  },
  metricLabel: {
    color: "#5f6f67",
    marginBottom: 2,
  },
  metricValue: {
    fontSize: 14,
    fontFamily: "Helvetica-Bold",
  },
  metricGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    marginTop: 10,
  },
  metricCard: {
    width: "48%",
    borderWidth: 1,
    borderColor: "#d2ddd5",
    borderRadius: 8,
    padding: 10,
    backgroundColor: "#f7fbf7",
    marginBottom: 10,
  },
  metricCardLabel: {
    color: "#506259",
    fontSize: 9,
    textTransform: "uppercase",
    marginBottom: 4,
  },
  metricCardValue: {
    fontFamily: "Helvetica-Bold",
    fontSize: 15,
    marginBottom: 4,
  },
  metricCardNote: {
    color: "#5f6f67",
    fontSize: 9,
    lineHeight: 1.35,
  },
  twoColumn: {
    flexDirection: "row",
  },
  column: {
    width: "50%",
  },
  columnSpacer: {
    width: 12,
  },
  sectionCard: {
    borderWidth: 1,
    borderColor: "#d9d4ca",
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
    backgroundColor: "#fffdf9",
  },
  sectionTitle: {
    fontSize: 12,
    fontFamily: "Helvetica-Bold",
    marginBottom: 8,
  },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: "#ede7dd",
  },
  rowLast: {
    borderBottomWidth: 0,
  },
  table: {
    borderWidth: 1,
    borderColor: "#d9d4ca",
    borderRadius: 8,
    overflow: "hidden",
  },
  tableHeader: {
    flexDirection: "row",
    backgroundColor: "#f1ebdf",
    borderBottomWidth: 1,
    borderBottomColor: "#d9d4ca",
  },
  tableRow: {
    flexDirection: "row",
    borderBottomWidth: 1,
    borderBottomColor: "#ede7dd",
  },
  cell: {
    paddingVertical: 7,
    paddingHorizontal: 8,
  },
  headerCellText: {
    fontFamily: "Helvetica-Bold",
    fontSize: 9,
    textTransform: "uppercase",
    color: "#506259",
  },
  bodyCellText: {
    fontSize: 9,
  },
  callout: {
    marginTop: 12,
    padding: 10,
    borderLeftWidth: 3,
    borderLeftColor: "#274737",
    backgroundColor: "#f4f8f4",
  },
  compactCallout: {
    marginTop: 8,
    padding: 10,
    borderLeftWidth: 3,
    borderLeftColor: "#274737",
    backgroundColor: "#f4f8f4",
    marginBottom: 12,
  },
  boxGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
  },
  infoBox: {
    width: "48%",
    borderWidth: 1,
    borderColor: "#d9d4ca",
    borderRadius: 8,
    padding: 12,
    backgroundColor: "#fffdf9",
    marginBottom: 12,
  },
  bullet: {
    marginBottom: 6,
    lineHeight: 1.4,
  },
  tableIntro: {
    color: "#5f6f67",
    marginBottom: 10,
    lineHeight: 1.4,
  },
  footer: {
    position: "absolute",
    bottom: 18,
    left: 34,
    right: 34,
    flexDirection: "row",
    justifyContent: "space-between",
    color: "#7a857f",
    fontSize: 8,
  },
});

function formatCurrency(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const absolute = Math.abs(cents);
  return `${sign}$${(absolute / 100).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

function formatPercent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

function formatDateLabel(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function formatRetirementYear(year: number | null): string {
  return year === null ? "Not depleted" : `Year ${year}`;
}

function retirementHeadline(report: RetirementSurvivalReport): string {
  if (report.verdict.probability_portfolio_survives >= 0.9 && report.withdrawal_analysis.withdrawal_rate_gap >= 0) {
    return "The current plan clears the horizon with a wide modeled cushion.";
  }
  if (report.verdict.probability_portfolio_survives >= 0.75) {
    return "The current plan reaches the horizon in most futures, but the margin is tight.";
  }
  if (report.verdict.probability_portfolio_survives >= 0.5) {
    return "The current plan works in some futures, but depletion risk is meaningful.";
  }
  return "The current plan shows high depletion risk under the modeled assumptions.";
}

function retirementProjectionMilestones(report: RetirementSurvivalReport) {
  const milestoneYears = new Set<number>([1, 5, 10, 15, 20, 25, report.verdict.horizon_years]);
  if (report.verdict.conditional_median_depletion_year !== null) {
    milestoneYears.add(report.verdict.conditional_median_depletion_year);
  }
  return report.yearly_projection.filter((row) => milestoneYears.has(row.year));
}

function Row({ label, value, last = false }: { label: string; value: string; last?: boolean }) {
  return (
    <View style={last ? [styles.row, styles.rowLast] : styles.row}>
      <Text>{label}</Text>
      <Text>{value}</Text>
    </View>
  );
}

function KeyValueList({ rows }: { rows: ReportInputsSummaryRow[] }) {
  return (
    <View style={styles.sectionCard}>
      {rows.map((row, index) => (
        <Row key={`${row.label}-${index}`} label={row.label} value={row.value} last={index === rows.length - 1} />
      ))}
    </View>
  );
}

function YearlyTable({ rows }: { rows: ReportYearRow[] }) {
  return (
    <View style={styles.table}>
      <View style={styles.tableHeader}>
        <View style={[styles.cell, { width: "14%" }]}><Text style={styles.headerCellText}>Year</Text></View>
        <View style={[styles.cell, { width: "28.6%" }]}><Text style={styles.headerCellText}>Renting</Text></View>
        <View style={[styles.cell, { width: "28.6%" }]}><Text style={styles.headerCellText}>Buying</Text></View>
        <View style={[styles.cell, { width: "28.8%" }]}><Text style={styles.headerCellText}>Difference</Text></View>
      </View>
      {rows.map((row, index) => (
        <View key={row.year} style={index === rows.length - 1 ? [styles.tableRow, styles.rowLast] : styles.tableRow}>
          <View style={[styles.cell, { width: "14%" }]}><Text style={styles.bodyCellText}>{row.year}</Text></View>
          <View style={[styles.cell, { width: "28.6%" }]}><Text style={styles.bodyCellText}>{formatCurrency(row.rent_net_worth_cents)}</Text></View>
          <View style={[styles.cell, { width: "28.6%" }]}><Text style={styles.bodyCellText}>{formatCurrency(row.buy_net_worth_cents)}</Text></View>
          <View style={[styles.cell, { width: "28.8%" }]}><Text style={styles.bodyCellText}>{formatCurrency(row.difference_cents)}</Text></View>
        </View>
      ))}
    </View>
  );
}

function SensitivityTable({ rows }: { rows: ReportSensitivityRow[] }) {
  return (
    <View style={styles.table}>
      <View style={styles.tableHeader}>
        <View style={[styles.cell, { width: "50%" }]}><Text style={styles.headerCellText}>Scenario</Text></View>
        <View style={[styles.cell, { width: "22%" }]}><Text style={styles.headerCellText}>Break-even</Text></View>
        <View style={[styles.cell, { width: "28%" }]}><Text style={styles.headerCellText}>Prob. buy wins</Text></View>
      </View>
      {rows.map((row, index) => (
        <View key={row.label} style={index === rows.length - 1 ? [styles.tableRow, styles.rowLast] : styles.tableRow}>
          <View style={[styles.cell, { width: "50%" }]}><Text style={styles.bodyCellText}>{row.label}</Text></View>
          <View style={[styles.cell, { width: "22%" }]}><Text style={styles.bodyCellText}>{row.break_even_label}</Text></View>
          <View style={[styles.cell, { width: "28%" }]}><Text style={styles.bodyCellText}>{row.probability_buy_beats_rent_label}</Text></View>
        </View>
      ))}
    </View>
  );
}

function AuditTable({ rows }: { rows: ReportAuditTrailRow[] }) {
  return (
    <View style={styles.table}>
      <View style={styles.tableHeader}>
        <View style={[styles.cell, { width: "26%" }]}><Text style={styles.headerCellText}>Assumption</Text></View>
        <View style={[styles.cell, { width: "14%" }]}><Text style={styles.headerCellText}>Value</Text></View>
        <View style={[styles.cell, { width: "40%" }]}><Text style={styles.headerCellText}>Source</Text></View>
        <View style={[styles.cell, { width: "20%" }]}><Text style={styles.headerCellText}>Date</Text></View>
      </View>
      {rows.map((row, index) => (
        <View key={`${row.label}-${index}`} wrap={false} style={index === rows.length - 1 ? [styles.tableRow, styles.rowLast] : styles.tableRow}>
          <View style={[styles.cell, { width: "26%" }]}><Text style={styles.bodyCellText}>{row.label}</Text></View>
          <View style={[styles.cell, { width: "14%" }]}><Text style={styles.bodyCellText}>{row.value === null ? "-" : String(row.value)}</Text></View>
          <View style={[styles.cell, { width: "40%" }]}><Text style={styles.bodyCellText}>{row.source}</Text></View>
          <View style={[styles.cell, { width: "20%" }]}><Text style={styles.bodyCellText}>{row.last_updated ?? "-"}</Text></View>
        </View>
      ))}
    </View>
  );
}

function RetirementProjectionTable({ report }: { report: RetirementSurvivalReport }) {
  const rows = retirementProjectionMilestones(report);
  return (
    <View style={styles.table}>
      <View style={styles.tableHeader}>
        <View style={[styles.cell, { width: "12%" }]}><Text style={styles.headerCellText}>Year</Text></View>
        <View style={[styles.cell, { width: "22%" }]}><Text style={styles.headerCellText}>Deterministic</Text></View>
        <View style={[styles.cell, { width: "22%" }]}><Text style={styles.headerCellText}>Median</Text></View>
        <View style={[styles.cell, { width: "28%" }]}><Text style={styles.headerCellText}>P10 to P90</Text></View>
        <View style={[styles.cell, { width: "16%" }]}><Text style={styles.headerCellText}>Depleted by then</Text></View>
      </View>
      {rows.map((row, index) => (
        <View key={row.year} wrap={false} style={index === rows.length - 1 ? [styles.tableRow, styles.rowLast] : styles.tableRow}>
          <View style={[styles.cell, { width: "12%" }]}><Text style={styles.bodyCellText}>{row.year}</Text></View>
          <View style={[styles.cell, { width: "22%" }]}><Text style={styles.bodyCellText}>{formatCurrency(row.deterministic_portfolio_cents)}</Text></View>
          <View style={[styles.cell, { width: "22%" }]}><Text style={styles.bodyCellText}>{formatCurrency(row.median_portfolio_cents)}</Text></View>
          <View style={[styles.cell, { width: "28%" }]}><Text style={styles.bodyCellText}>{`${formatCurrency(row.p10_portfolio_cents)} to ${formatCurrency(row.p90_portfolio_cents)}`}</Text></View>
          <View style={[styles.cell, { width: "16%" }]}><Text style={styles.bodyCellText}>{formatPercent(row.cumulative_depletion_probability)}</Text></View>
        </View>
      ))}
    </View>
  );
}

function Footer() {
  return (
    <View style={styles.footer} fixed>
      <Text>Family Financial Compass</Text>
      <Text render={({ pageNumber, totalPages }) => `Page ${pageNumber} of ${totalPages}`} />
    </View>
  );
}

export function RentVsBuyReportDocument({ report }: { report: RentVsBuyReport }) {
  return (
    <Document title="Family Financial Compass Report">
      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Rent vs Buy Report</Text>
        <Text style={styles.title}>The Verdict</Text>
        <Text style={styles.subtitle}>
          This report presents the economics of the decision descriptively. The household still makes the decision.
        </Text>
        <Text style={styles.disclaimer}>{report.disclaimer}</Text>
        <View style={styles.verdictBox}>
          <Text style={styles.verdictHeadline}>{report.verdict.headline}</Text>
          <Text style={styles.paragraph}>
            {report.verdict.winner_label} leads over the next {report.verdict.horizon_years.toFixed(1)} years in the deterministic path.
          </Text>
          <View style={styles.metricRow}>
            <View style={styles.metricBlock}>
              <Text style={styles.metricLabel}>Break-even</Text>
              <Text style={styles.metricValue}>{report.verdict.break_even_month === null ? "No break-even" : `Month ${report.verdict.break_even_month}`}</Text>
            </View>
            <View style={styles.metricBlock}>
              <Text style={styles.metricLabel}>Buying wins across simulations</Text>
              <Text style={styles.metricValue}>{formatPercent(report.verdict.probability_buy_beats_rent)}</Text>
            </View>
          </View>
        </View>
        <Text style={styles.paragraph}>{report.narratives.verdict_driver}</Text>
        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>Across simulated futures</Text>
          <Row label="Buying outperforms renting" value={formatPercent(report.verdict.probability_buy_beats_rent)} />
          <Row label="Downside outcome" value={formatCurrency(report.verdict.p10_terminal_advantage_cents)} />
          <Row label="Upside outcome" value={formatCurrency(report.verdict.p90_terminal_advantage_cents)} last />
        </View>
        <Footer />
      </Page>

      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Page 2</Text>
        <Text style={styles.title}>Your Numbers at a Glance</Text>
        <View style={styles.twoColumn}>
          <View style={styles.column}>
            <Text style={styles.sectionTitle}>What you told us</Text>
            <KeyValueList rows={report.inputs_summary} />
          </View>
          <View style={styles.columnSpacer} />
          <View style={styles.column}>
            <Text style={styles.sectionTitle}>What we assumed</Text>
            <KeyValueList rows={report.assumptions_summary} />
          </View>
        </View>
        <Text style={styles.paragraph}>
          All assumptions are sourced from public data. The audit trail below shows the source and date attached to each system-sourced value.
        </Text>
        <AuditTable rows={report.audit_trail} />
        <Footer />
      </Page>

      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Page 3</Text>
        <Text style={styles.title}>Projected Net Worth</Text>
        <Text style={styles.paragraph}>{report.narratives.net_worth_summary}</Text>
        <YearlyTable rows={report.yearly_net_worth} />
        <View style={styles.callout}>
          <Text>{report.verdict.break_even_month === null ? "The paths do not cross inside the chosen horizon." : `The modeled break-even point occurs at month ${report.verdict.break_even_month}.`}</Text>
        </View>
        <Footer />
      </Page>

      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Page 4</Text>
        <Text style={styles.title}>What Buying Actually Costs</Text>
        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>Year one buyer costs</Text>
          <Row label="Mortgage payment (P+I)" value={formatCurrency(report.year_one_costs.principal_and_interest_cents)} />
          <Row label="Property taxes" value={formatCurrency(report.year_one_costs.property_tax_cents)} />
          <Row label="Home insurance" value={formatCurrency(report.year_one_costs.insurance_cents)} />
          <Row label="Maintenance" value={formatCurrency(report.year_one_costs.maintenance_cents)} />
          <Row label="PMI" value={formatCurrency(report.year_one_costs.pmi_cents)} />
          <Row label="Liquidity premium" value={formatCurrency(report.year_one_costs.liquidity_premium_cents)} />
          <Row label="Gross cost" value={formatCurrency(report.year_one_costs.gross_annual_cents)} />
          <Row label="Mortgage interest tax saving" value={formatCurrency(report.year_one_costs.mortgage_interest_tax_saving_cents)} />
          <Row label="True buyer cost" value={formatCurrency(report.year_one_costs.true_annual_cents)} />
          <Row label="Current rent" value={formatCurrency(report.year_one_costs.current_rent_annual_cents)} />
          <Row label="Year one cash difference" value={formatCurrency(report.year_one_costs.cash_difference_annual_cents)} last />
        </View>
        <Footer />
      </Page>

      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Page 5</Text>
        <Text style={styles.title}>Hidden Factors</Text>
        <View style={styles.boxGrid}>
          <View style={styles.infoBox}>
            <Text style={styles.sectionTitle}>Equity Building</Text>
            <Text style={styles.paragraph}>
              By the end of the modeled horizon, estimated equity after selling costs and capital gains tax is {formatCurrency(report.hidden_factors.equity_after_sale_horizon_cents)}.
            </Text>
          </View>
          <View style={styles.infoBox}>
            <Text style={styles.sectionTitle}>Opportunity Cost</Text>
            <Text style={styles.paragraph}>
              The down payment plus buyer closing costs totals {formatCurrency(report.hidden_factors.initial_purchase_cash_cents)}.
            </Text>
            <Text style={styles.paragraph}>
              Invested instead at the modeled net return, that starting capital grows to {formatCurrency(report.hidden_factors.opportunity_cost_future_value_cents)} by the end of the horizon.
            </Text>
          </View>
          <View style={styles.infoBox}>
            <Text style={styles.sectionTitle}>Tax Considerations</Text>
            <Text style={styles.paragraph}>
              The year-one housing tax saving in the actual scenario is {formatCurrency(report.hidden_factors.actual_tax_saving_year_one_cents)}.
            </Text>
            <Text style={styles.paragraph}>
              If the household itemized housing deductions in year one, the modeled saving would be {formatCurrency(report.hidden_factors.hypothetical_itemized_year_one_cents)}.
            </Text>
          </View>
          <View style={styles.infoBox}>
            <Text style={styles.sectionTitle}>Capital Gains at Sale</Text>
            <Text style={styles.paragraph}>
              Estimated gain at sale is {formatCurrency(report.hidden_factors.capital_gains.estimated_gain_cents)}. The modeled primary-residence exclusion is {formatCurrency(report.hidden_factors.capital_gains.exclusion_cents)}.
            </Text>
            <Text style={styles.paragraph}>
              Capital gains tax owed at sale is {formatCurrency(report.hidden_factors.capital_gains.capital_gains_tax_cents)}.
            </Text>
          </View>
        </View>
        <Footer />
      </Page>

      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Page 6</Text>
        <Text style={styles.title}>Sensitivity Analysis</Text>
        <Text style={styles.paragraph}>{report.narratives.sensitivity_summary}</Text>
        <SensitivityTable rows={report.sensitivity.rows} />
        <View style={styles.callout}>
          <Text>
            Most sensitive assumption: {report.sensitivity.most_sensitive_label} ({report.sensitivity.largest_probability_shift_points.toFixed(0)} percentage-point probability shift).
          </Text>
        </View>
        <Footer />
      </Page>

      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Page 7</Text>
        <Text style={styles.title}>Three Questions Before Deciding</Text>
        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>1. Is the timeline long enough?</Text>
          <Text style={styles.paragraph}>{report.narratives.question_timeline}</Text>
        </View>
        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>2. Is the liquidity buffer still healthy?</Text>
          <Text style={styles.paragraph}>{report.narratives.question_liquidity}</Text>
        </View>
        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>3. What risk sits outside the base case?</Text>
          <Text style={styles.paragraph}>{report.narratives.question_risk}</Text>
        </View>
        <Footer />
      </Page>

      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Page 8</Text>
        <Text style={styles.title}>Summary and Next Steps</Text>
        <Text style={styles.paragraph}>{report.narratives.summary}</Text>
        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>Next steps</Text>
          <Text style={styles.bullet}>- Re-run the report if your time horizon, down payment, or market assumptions change.</Text>
          <Text style={styles.bullet}>- Review the sensitivity page before treating a close result as settled.</Text>
          <Text style={styles.bullet}>- Compare the downside case with your savings buffer before making a final decision.</Text>
          <Text style={styles.bullet}>- Consult a qualified financial advisor before acting on a major purchase decision.</Text>
        </View>
        <View style={styles.callout}>
          <Text>Report narrative source: {report.narrative_source === "groq" ? "Groq" : "Template fallback"}.</Text>
        </View>
        <Footer />
      </Page>
    </Document>
  );
}

export function RetirementSurvivalReportDocument({
  report,
}: {
  report: RetirementSurvivalReport;
}) {
  return (
    <Document title="Family Financial Compass Retirement Report">
      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Retirement Survival Report</Text>
        <Text style={styles.title}>Retirement Plan Snapshot</Text>
        <Text style={styles.subtitle}>
          A descriptive view of how the current spending plan behaves across the modeled retirement horizon.
        </Text>
        <Text style={styles.metaLine}>Generated {formatDateLabel(report.generated_at)} for a {report.verdict.horizon_years}-year retirement horizon.</Text>
        <Text style={styles.disclaimer}>{report.disclaimer}</Text>
        <View style={styles.verdictBox}>
          <Text style={styles.verdictHeadline}>{retirementHeadline(report)}</Text>
          <Text style={styles.paragraph}>{report.narratives.summary}</Text>
          <View style={styles.metricGrid}>
            <View style={styles.metricCard}>
              <Text style={styles.metricCardLabel}>Plan survival</Text>
              <Text style={styles.metricCardValue}>{formatPercent(report.verdict.probability_portfolio_survives)}</Text>
              <Text style={styles.metricCardNote}>Share of modeled futures that stay above zero through year {report.verdict.horizon_years}.</Text>
            </View>
            <View style={styles.metricCard}>
              <Text style={styles.metricCardLabel}>Net withdrawal rate</Text>
              <Text style={styles.metricCardValue}>{formatPercent(report.withdrawal_analysis.current_withdrawal_rate, 2)}</Text>
              <Text style={styles.metricCardNote}>Based on current net withdrawals of {formatCurrency(report.withdrawal_analysis.net_annual_withdrawal_cents)} a year.</Text>
            </View>
            <View style={styles.metricCard}>
              <Text style={styles.metricCardLabel}>95% safe rate</Text>
              <Text style={styles.metricCardValue}>{formatPercent(report.verdict.safe_withdrawal_rate_95, 2)}</Text>
              <Text style={styles.metricCardNote}>Modeled safe annual draw: {formatCurrency(report.withdrawal_analysis.safe_withdrawal_annual_cents)}.</Text>
            </View>
            <View style={styles.metricCard}>
              <Text style={styles.metricCardLabel}>Deterministic path</Text>
              <Text style={styles.metricCardValue}>{formatRetirementYear(report.verdict.deterministic_depletion_year)}</Text>
              <Text style={styles.metricCardNote}>The single-path projection without randomized return sequences.</Text>
            </View>
          </View>
        </View>
        <Text style={styles.paragraph}>{report.narratives.survival_verdict}</Text>
        <Text style={styles.paragraph}>{report.narratives.withdrawal_rate_summary}</Text>
        <View style={styles.twoColumn}>
          <View style={styles.column}>
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Terminal wealth range</Text>
              <Row label="Downside (P10)" value={formatCurrency(report.wealth_at_horizon.p10_terminal_wealth_cents)} />
              <Row label="Median (P50)" value={formatCurrency(report.wealth_at_horizon.median_terminal_wealth_cents)} />
              <Row label="Upside (P90)" value={formatCurrency(report.wealth_at_horizon.p90_terminal_wealth_cents)} last />
            </View>
          </View>
          <View style={styles.columnSpacer} />
          <View style={styles.column}>
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Withdrawal pressure</Text>
              <Row label="Net planned draw" value={formatCurrency(report.withdrawal_analysis.net_annual_withdrawal_cents)} />
              <Row label="Modeled safe draw" value={formatCurrency(report.withdrawal_analysis.safe_withdrawal_annual_cents)} />
              <Row label="Annual gap" value={formatCurrency(report.withdrawal_analysis.safe_withdrawal_gap_cents)} />
              <Row label="Rate gap" value={formatPercent(report.withdrawal_analysis.withdrawal_rate_gap, 2)} last />
            </View>
          </View>
        </View>
        <Footer />
      </Page>

      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Plan Diagnostics</Text>
        <Text style={styles.title}>Inputs and Pressure Points</Text>
        <View style={styles.twoColumn}>
          <View style={styles.column}>
            <Text style={styles.sectionTitle}>Inputs</Text>
            <KeyValueList rows={report.inputs_summary} />
          </View>
          <View style={styles.columnSpacer} />
          <View style={styles.column}>
            <Text style={styles.sectionTitle}>Assumptions</Text>
            <KeyValueList rows={report.assumptions_summary} />
          </View>
        </View>
        <View style={styles.boxGrid}>
          <View style={styles.infoBox}>
            <Text style={styles.sectionTitle}>Conditional median depletion</Text>
            <Text style={styles.paragraph}>
              {report.verdict.conditional_median_depletion_year === null
                ? "Fewer than half of modeled paths deplete before the end of the horizon."
                : `Among the paths that do deplete, the median depletion point is year ${report.verdict.conditional_median_depletion_year}.`}
            </Text>
          </View>
          <View style={styles.infoBox}>
            <Text style={styles.sectionTitle}>Deterministic terminal wealth</Text>
            <Text style={styles.paragraph}>
              The non-randomized path ends with {formatCurrency(report.wealth_at_horizon.deterministic_terminal_wealth_cents)} at the horizon.
            </Text>
          </View>
          <View style={styles.infoBox}>
            <Text style={styles.sectionTitle}>Median terminal wealth</Text>
            <Text style={styles.paragraph}>
              Across the modeled range, the midpoint outcome ends with {formatCurrency(report.wealth_at_horizon.median_terminal_wealth_cents)}.
            </Text>
          </View>
          <View style={styles.infoBox}>
            <Text style={styles.sectionTitle}>Range width</Text>
            <Text style={styles.paragraph}>
              The distance between the downside and upside terminal outcomes is {formatCurrency(report.wealth_at_horizon.p90_terminal_wealth_cents - report.wealth_at_horizon.p10_terminal_wealth_cents)}.
            </Text>
          </View>
        </View>
        <View style={styles.compactCallout}>
          <Text>{report.narratives.wealth_range_summary}</Text>
        </View>
        <View style={styles.compactCallout}>
          <Text>{report.narratives.risk_summary}</Text>
        </View>
        {report.warnings.length > 0 && (
          <View style={styles.sectionCard}>
            <Text style={styles.sectionTitle}>Warnings the model flagged</Text>
            {report.warnings.map((warning) => (
              <Text key={warning} style={styles.bullet}>- {warning}</Text>
            ))}
          </View>
        )}
        <Footer />
      </Page>

      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Portfolio Path</Text>
        <Text style={styles.title}>How the Portfolio Changes Over Time</Text>
        <Text style={styles.tableIntro}>
          The table below shows selected checkpoints from the yearly simulation output. The depletion column is cumulative: it shows the share of modeled paths that have already fallen to zero by that year.
        </Text>
        <RetirementProjectionTable report={report} />
        <View style={styles.callout}>
          <Text>
            By year {report.verdict.horizon_years}, cumulative depletion reaches {formatPercent(1 - report.verdict.probability_portfolio_survives)}.
            {" "}The deterministic path {report.verdict.deterministic_depletion_year === null ? "does not exhaust the portfolio inside the modeled horizon." : `reaches zero in year ${report.verdict.deterministic_depletion_year}.`}
          </Text>
        </View>
        <Footer />
      </Page>

      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Assumptions</Text>
        <Text style={styles.title}>Audit Trail and Model Setup</Text>
        <Text style={styles.tableIntro}>
          This section is intentionally narrow. It lists only the retirement-specific assumptions and calibration settings that materially move this simulation, along with their sources and refresh dates.
        </Text>
        <AuditTable rows={report.audit_trail} />
        <Footer />
      </Page>
    </Document>
  );
}

export function JobOfferReportDocument({ report }: { report: JobOfferReport }) {
  return (
    <Document title="Family Financial Compass Job Offer Report">
      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Job Offer Report</Text>
        <Text style={styles.title}>The Verdict</Text>
        <Text style={styles.subtitle}>
          This report compares the economics of the two offers descriptively. It does not tell the household what to do.
        </Text>
        <Text style={styles.disclaimer}>{report.disclaimer}</Text>
        <View style={styles.verdictBox}>
          <Text style={styles.verdictHeadline}>{report.narratives.summary}</Text>
          <View style={styles.metricRow}>
            <View style={styles.metricBlock}>
              <Text style={styles.metricLabel}>Break-even</Text>
              <Text style={styles.metricValue}>{report.verdict.break_even_month === null ? "No break-even" : `Month ${report.verdict.break_even_month}`}</Text>
            </View>
            <View style={styles.metricBlock}>
              <Text style={styles.metricLabel}>Offer B wins</Text>
              <Text style={styles.metricValue}>{formatPercent(report.verdict.probability_offer_b_wins)}</Text>
            </View>
          </View>
        </View>
        <Text style={styles.paragraph}>{report.narratives.offer_comparison}</Text>
        <Text style={styles.paragraph}>{report.narratives.break_even_summary}</Text>
        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>Risk-adjusted view</Text>
          <Row label="Deterministic advantage" value={formatCurrency(report.verdict.end_of_horizon_advantage_cents)} />
          <Row label="Utility-adjusted advantage" value={formatCurrency(report.verdict.utility_adjusted_advantage_cents)} />
          <Row label="Downside case" value={formatCurrency(report.risk.p10_terminal_advantage_cents)} />
          <Row label="Upside case" value={formatCurrency(report.risk.p90_terminal_advantage_cents)} last />
        </View>
        <Footer />
      </Page>

      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Page 2</Text>
        <Text style={styles.title}>Offer Comparison and Costs</Text>
        <View style={styles.twoColumn}>
          <View style={styles.column}>
            <Text style={styles.sectionTitle}>{report.offers.offer_a_label}</Text>
            <KeyValueList rows={report.offers.offer_a_summary} />
          </View>
          <View style={styles.columnSpacer} />
          <View style={styles.column}>
            <Text style={styles.sectionTitle}>{report.offers.offer_b_label}</Text>
            <KeyValueList rows={report.offers.offer_b_summary} />
          </View>
        </View>
        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>Year-one switch friction</Text>
          <Row label="Relocation cost" value={formatCurrency(report.hidden_costs.offer_b.relocation_cost_cents)} />
          <Row label="Cost-of-living change" value={formatCurrency(report.hidden_costs.offer_b.annual_cost_of_living_delta_cents)} />
          <Row label="Commute cost" value={formatCurrency(report.hidden_costs.offer_b.annual_commute_cost_cents)} />
          <Row label="After-tax sign-on bonus" value={formatCurrency(report.hidden_costs.offer_b.after_tax_sign_on_bonus_cents)} />
          <Row label="Net first-year switch impact" value={formatCurrency(report.hidden_costs.offer_b_minus_offer_a_first_year_friction_cents)} last />
        </View>
        <AuditTable rows={report.audit_trail} />
        <Footer />
      </Page>
    </Document>
  );
}

export function CollegeVsRetirementReportDocument({
  report,
}: {
  report: CollegeVsRetirementReport;
}) {
  return (
    <Document title="Family Financial Compass College vs Retirement Report">
      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>College vs Retirement Report</Text>
        <Text style={styles.title}>The Tradeoff</Text>
        <Text style={styles.subtitle}>
          This report shows what prioritizing one family goal costs the other under the modeled assumptions.
        </Text>
        <Text style={styles.disclaimer}>{report.disclaimer}</Text>
        <View style={styles.verdictBox}>
          <Text style={styles.verdictHeadline}>{report.narratives.summary}</Text>
          <View style={styles.metricRow}>
            <View style={styles.metricBlock}>
              <Text style={styles.metricLabel}>Retirement-first wins</Text>
              <Text style={styles.metricValue}>{formatPercent(report.verdict.probability_retirement_first_wins)}</Text>
            </View>
            <View style={styles.metricBlock}>
              <Text style={styles.metricLabel}>Break-even</Text>
              <Text style={styles.metricValue}>{report.verdict.break_even_year === null ? "No break-even" : `Year ${report.verdict.break_even_year}`}</Text>
            </View>
          </View>
        </View>
        <Text style={styles.paragraph}>{report.narratives.allocation_verdict}</Text>
        <Text style={styles.paragraph}>{report.narratives.loan_impact_summary}</Text>
        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>Goal tradeoff</Text>
          <Row label="College-first student debt" value={formatCurrency(report.funding_analysis.college_first_total_loan_cents)} />
          <Row label="Retirement-first student debt" value={formatCurrency(report.funding_analysis.retirement_first_total_loan_cents)} />
          <Row label="College-first retirement balance" value={formatCurrency(report.retirement_outcomes.college_first_terminal_retirement_cents)} />
          <Row label="Retirement-first retirement balance" value={formatCurrency(report.retirement_outcomes.retirement_first_terminal_retirement_cents)} last />
        </View>
        <Footer />
      </Page>

      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Page 2</Text>
        <Text style={styles.title}>Inputs and Audit Trail</Text>
        <KeyValueList rows={report.inputs_summary} />
        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>Loan burden</Text>
          <Row label="College-first annual payment" value={formatCurrency(report.funding_analysis.college_first_annual_loan_payment_cents)} />
          <Row label="Retirement-first annual payment" value={formatCurrency(report.funding_analysis.retirement_first_annual_loan_payment_cents)} />
          <Row label="College-first total interest" value={formatCurrency(report.funding_analysis.college_first_total_interest_cents)} />
          <Row label="Retirement-first total interest" value={formatCurrency(report.funding_analysis.retirement_first_total_interest_cents)} last />
        </View>
        <AuditTable rows={report.audit_trail} />
        <Footer />
      </Page>
    </Document>
  );
}
