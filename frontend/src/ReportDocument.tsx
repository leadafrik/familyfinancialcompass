import { Document, Page, StyleSheet, Text, View } from "@react-pdf/renderer";

import type {
  RentVsBuyReport,
  ReportAuditTrailRow,
  ReportInputsSummaryRow,
  ReportSensitivityRow,
  ReportYearRow,
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

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
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
        <View style={[styles.cell, { width: "28%" }]}><Text style={styles.headerCellText}>Assumption</Text></View>
        <View style={[styles.cell, { width: "18%" }]}><Text style={styles.headerCellText}>Value</Text></View>
        <View style={[styles.cell, { width: "34%" }]}><Text style={styles.headerCellText}>Source</Text></View>
        <View style={[styles.cell, { width: "20%" }]}><Text style={styles.headerCellText}>Date</Text></View>
      </View>
      {rows.map((row, index) => (
        <View key={`${row.label}-${index}`} style={index === rows.length - 1 ? [styles.tableRow, styles.rowLast] : styles.tableRow}>
          <View style={[styles.cell, { width: "28%" }]}><Text style={styles.bodyCellText}>{row.label}</Text></View>
          <View style={[styles.cell, { width: "18%" }]}><Text style={styles.bodyCellText}>{row.value === null ? "-" : String(row.value)}</Text></View>
          <View style={[styles.cell, { width: "34%" }]}><Text style={styles.bodyCellText}>{row.source}</Text></View>
          <View style={[styles.cell, { width: "20%" }]}><Text style={styles.bodyCellText}>{row.last_updated ?? "-"}</Text></View>
        </View>
      ))}
    </View>
  );
}

function Footer({ pageNumber }: { pageNumber: number }) {
  return (
    <View style={styles.footer} fixed>
      <Text>Family Financial Compass</Text>
      <Text>Page {pageNumber}</Text>
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
        <Footer pageNumber={1} />
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
        <Footer pageNumber={2} />
      </Page>

      <Page size="LETTER" style={styles.page}>
        <Text style={styles.overline}>Page 3</Text>
        <Text style={styles.title}>Projected Net Worth</Text>
        <Text style={styles.paragraph}>{report.narratives.net_worth_summary}</Text>
        <YearlyTable rows={report.yearly_net_worth} />
        <View style={styles.callout}>
          <Text>{report.verdict.break_even_month === null ? "The paths do not cross inside the chosen horizon." : `The modeled break-even point occurs at month ${report.verdict.break_even_month}.`}</Text>
        </View>
        <Footer pageNumber={3} />
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
        <Footer pageNumber={4} />
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
        <Footer pageNumber={5} />
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
        <Footer pageNumber={6} />
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
          {report.questions.risk.warnings.map((warning) => (
            <Text key={warning} style={styles.bullet}>- {warning}</Text>
          ))}
        </View>
        <Footer pageNumber={7} />
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
        <Footer pageNumber={8} />
      </Page>
    </Document>
  );
}
