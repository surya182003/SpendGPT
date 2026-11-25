import { activeBudgets, BUDGET_STATUS, formatMoney, sourceLabel } from "../../services/ai.js";
import { card, colors, mutedText, secondaryButton } from "./aiStyles.js";

const PRIORITY_COLORS = { high: colors.red, medium: colors.yellow, low: colors.green };

function Stat({ label, value, hint }) {
  return (
    <div style={{ ...card, flex: "1", minWidth: "150px", padding: "12px 14px" }}>
      <div style={mutedText}>{label}</div>
      <div style={{ fontSize: "22px", fontWeight: "bold", marginTop: "4px" }}>{value}</div>
      {hint && <div style={{ ...mutedText, fontSize: "12px", marginTop: "2px" }}>{hint}</div>}
    </div>
  );
}

function ProgressBar({ percent, color }) {
  return (
    <div style={{ height: "8px", background: colors.page, borderRadius: "4px", overflow: "hidden" }}>
      <div style={{ width: Math.min(percent, 100) + "%", height: "100%", background: color }} />
    </div>
  );
}

// AI summary, key figures, category breakdown, budget use and recommendations.
// Every number comes from the /insights response; nothing is hardcoded.
function InsightsPanel({ insights, loading, error, onRetry }) {
  if (loading) {
    return (
      <div style={card}>
        <h3 style={{ marginTop: 0 }}>AI Spending Insights</h3>
        <p style={mutedText}>Analysing your spending…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={card}>
        <h3 style={{ marginTop: 0 }}>AI Spending Insights</h3>
        <p style={{ color: colors.red }}>{error}</p>
        <button onClick={onRetry} style={secondaryButton}>Try again</button>
      </div>
    );
  }

  if (!insights) {
    return null;
  }

  const money = (value) => formatMoney(value, insights.currency);
  const explanation = insights.explanation;

  if (insights.history_status === "empty") {
    return (
      <div style={card}>
        <h3 style={{ marginTop: 0 }}>AI Spending Insights</h3>
        <p>{explanation ? explanation.text : "No transactions yet."}</p>
        <p style={mutedText}>Scan a receipt or add transactions and your insights will appear here.</p>
      </div>
    );
  }

  const monthly = insights.monthly;
  const budgets = activeBudgets(insights);

  return (
    <div style={card}>
      <h3 style={{ marginTop: 0 }}>AI Spending Insights</h3>

      {explanation && (
        <div style={{ borderLeft: "3px solid " + colors.accent, paddingLeft: "12px", marginBottom: "16px" }}>
          <p style={{ margin: "0 0 6px", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{explanation.text}</p>
          <span style={{ ...mutedText, fontSize: "12px" }}>{sourceLabel(explanation.source, explanation.reason)}</span>
        </div>
      )}

      <div style={{ display: "flex", flexWrap: "wrap", gap: "12px" }}>
        <Stat
          label="This month so far"
          value={money(monthly.current_month_spent)}
          hint={monthly.current_month_projected ? "On course for " + money(monthly.current_month_projected) : null}
        />
        <Stat label="Average per month" value={money(insights.average_monthly_spend)}
          hint={"Last " + insights.months_covered.toFixed(1) + " months"} />
        <Stat
          label="Left after spending"
          value={insights.net === null ? "–" : money(insights.net)}
          hint={insights.savings_rate_pct === null ? "Set your income to see this" : insights.savings_rate_pct.toFixed(0) + "% of income"}
        />
        <Stat
          label="Trend"
          value={monthly.trend === "not_enough_data" ? "–" : monthly.trend.charAt(0).toUpperCase() + monthly.trend.slice(1)}
          hint={monthly.trend_change_pct === null ? "Needs 2 full months" : (monthly.trend_change_pct > 0 ? "+" : "") + monthly.trend_change_pct.toFixed(0) + "% vs earlier months"}
        />
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "20px", marginTop: "20px" }}>
        <div style={{ flex: "1", minWidth: "280px" }}>
          <h4 style={{ margin: "0 0 10px" }}>Spending by category</h4>
          {insights.categories.length === 0 && <p style={mutedText}>No categorised spending yet.</p>}
          {insights.categories.map((c) => (
            <div key={c.category_name} style={{ marginBottom: "10px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "14px", marginBottom: "4px" }}>
                <span>
                  {c.category_name}
                  {c.spend_type === "discretionary" && <span style={{ ...mutedText, fontSize: "11px" }}> · non-essential</span>}
                </span>
                <span>{money(c.total)} <span style={mutedText}>({c.share_pct.toFixed(0)}%)</span></span>
              </div>
              <ProgressBar percent={c.share_pct} color={colors.accent} />
            </div>
          ))}
        </div>

        <div style={{ flex: "1", minWidth: "280px" }}>
          <h4 style={{ margin: "0 0 10px" }}>Budgets this period</h4>
          {budgets.length === 0 && <p style={mutedText}>No active budgets. Set one to get warnings before you overspend.</p>}
          {budgets.map((b) => {
            const status = BUDGET_STATUS[b.status];
            return (
              <div key={b.budget_id} style={{ marginBottom: "12px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "14px", marginBottom: "4px" }}>
                  <span>{b.category_name}</span>
                  <span style={{ color: status.color }}>{status.label}</span>
                </div>
                <ProgressBar percent={b.used_pct} color={status.color} />
                <div style={{ ...mutedText, fontSize: "12px", marginTop: "4px" }}>
                  {money(b.spent)} of {money(b.amount_limit)} ({b.used_pct.toFixed(0)}%)
                  {b.projected !== null && " · on course for " + money(b.projected)}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {insights.recommendations.length > 0 && (
        <div style={{ marginTop: "20px" }}>
          <h4 style={{ margin: "0 0 10px" }}>Recommendations</h4>
          {insights.recommendations.map((r, index) => (
            <div key={index} style={{ display: "flex", gap: "10px", marginBottom: "10px" }}>
              <span style={{ width: "8px", minWidth: "8px", height: "8px", borderRadius: "50%", marginTop: "6px",
                background: PRIORITY_COLORS[r.priority] }} />
              <div>
                <div style={{ fontWeight: "bold", fontSize: "14px" }}>{r.title}</div>
                <div style={{ ...mutedText, fontSize: "13px" }}>{r.detail}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {insights.notes.length > 0 && (
        <ul style={{ ...mutedText, fontSize: "12px", margin: "12px 0 0", paddingLeft: "18px" }}>
          {insights.notes.map((note) => <li key={note}>{note}</li>)}
        </ul>
      )}
    </div>
  );
}

export default InsightsPanel;
