// Calls to the FastAPI AI endpoints (/api/ai/...).
// The browser never talks to LM Studio directly: the backend does that and
// sends back answers that are built from the user's own figures.

import { request } from "./api.js";

const JSON_HEADERS = { "Content-Type": "application/json" };

// Is the local AI model (LM Studio) reachable? -> { available, reason, models, configured_model }
export async function getAIStatus() {
  return request("/api/ai/status");
}

// Spending figures + a plain-language explanation for one user.
// explanation = { text, source: "llm" | "fallback", reason }
export async function getInsights(userId, months = 6, explain = true) {
  const query = "?months=" + months + "&explain=" + (explain ? "true" : "false");
  return request("/api/ai/users/" + userId + "/insights" + query);
}

// Ask the AI advisor. history = [{ role: "user" | "assistant", content }]
// -> { answer, source: "llm" | "fallback", reason }
export async function askAdvisor(userId, question, history = [], months = 6) {
  return request("/api/ai/users/" + userId + "/chat", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ question: question, history: history, months: months }),
  });
}

// Checks recent transactions for unusual spending and saves new alerts.
// -> { flags, transactions_analysed, history_status, notes, alerts_created }
export async function scanUnusualSpending(userId) {
  return request("/api/ai/users/" + userId + "/anomalies/scan", { method: "POST" });
}

// The user's saved alerts (newest first)
export async function getAlerts(userId, unreadOnly = false) {
  return request("/api/ai/users/" + userId + "/alerts?unread_only=" + (unreadOnly ? "true" : "false"));
}

export async function markAlertRead(userId, alertId) {
  return request("/api/ai/users/" + userId + "/alerts/" + alertId + "/read", { method: "PATCH" });
}

// Suggests a category for a merchant name. Nothing is saved.
// -> { category_id, category_name, confidence, source, reason }
export async function predictCategory(userId, merchantName, useLlm = false) {
  return request("/api/ai/categorize", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ merchant_name: merchantName, user_id: Number(userId), use_llm: useLlm }),
  });
}

// ---- helpers for showing the data (no network, so they are easy to test) ----

const SYMBOLS = { EUR: "€", GBP: "£", USD: "$" };

export function formatMoney(value, currency = "EUR") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "–";
  }
  const amount = Number(value).toLocaleString("en-IE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const symbol = SYMBOLS[currency];
  return symbol ? symbol + amount : amount + " " + currency;
}

// Pie chart rows: [{ name, value }] for every category with spending
export function categoryChartData(insights) {
  if (!insights || !insights.categories) {
    return [];
  }
  return insights.categories
    .filter((c) => c.total > 0)
    .map((c) => ({ name: c.category_name, value: c.total, share: c.share_pct }));
}

// Bar chart rows: [{ month: "Nov", amount, complete }] in date order
export function monthlyChartData(insights) {
  if (!insights || !insights.monthly || !insights.monthly.months) {
    return [];
  }
  return insights.monthly.months.map((m) => ({
    month: m.label.split(" ")[0].slice(0, 3),
    label: m.label,
    amount: m.total,
    complete: m.complete,
  }));
}

// Only the budgets running today, the ones that need attention first
export function activeBudgets(insights) {
  if (!insights || !insights.budgets) {
    return [];
  }
  return insights.budgets.filter((b) => b.is_active);
}

export const BUDGET_STATUS = {
  over: { label: "Over budget", color: "#FF5C5C" },
  at_risk: { label: "At risk", color: "#ffc658" },
  on_track: { label: "On track", color: "#82ca9d" },
};

export const CATEGORY_SOURCE = {
  history: "from your earlier transactions",
  rule: "matched a known merchant",
  ml: "predicted by the ML model",
  llm: "suggested by the local AI",
  default: "no confident match",
};

// Short line shown under AI text so users know where it came from
export function sourceLabel(source, reason) {
  if (source === "llm") {
    return "Written by the local AI model from your figures";
  }
  if (reason === "no_data") {
    return "Summary";
  }
  if (reason === "unverified_figures") {
    return "Summary from your figures (the AI answer could not be checked)";
  }
  return "Summary from your figures (local AI is offline)";
}

// The last few chat turns in the shape the backend expects
export function chatHistory(messages, maxTurns = 10) {
  return messages
    .filter((m) => (m.role === "user" || m.role === "assistant") && m.content)
    .slice(-maxTurns)
    .map((m) => ({ role: m.role, content: m.content }));
}
