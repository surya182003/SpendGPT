// Tests for the AI API client. Run with: npm test
// Uses Node's built-in test runner and a fake fetch, so no backend or LM Studio is needed.
import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import {
  activeBudgets,
  askAdvisor,
  categoryChartData,
  chatHistory,
  formatMoney,
  getAIStatus,
  getAlerts,
  getInsights,
  markAlertRead,
  monthlyChartData,
  predictCategory,
  scanUnusualSpending,
  sourceLabel,
} from "./ai.js";

let calls;
let nextResponse;

beforeEach(() => {
  calls = [];
  nextResponse = { status: 200, body: {} };
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (nextResponse.networkError) {
      throw new TypeError("Failed to fetch");
    }
    return {
      ok: nextResponse.status < 400,
      status: nextResponse.status,
      json: async () => nextResponse.body,
    };
  };
});

afterEach(() => {
  delete globalThis.fetch;
});

const BASE = "http://localhost:8000";

// ---- requests go to FastAPI, never to LM Studio ----
test("status is read from the backend, not LM Studio", async () => {
  nextResponse.body = { available: false, reason: "connection", models: [], configured_model: null };
  const status = await getAIStatus();
  assert.equal(calls[0].url, BASE + "/api/ai/status");
  assert.equal(status.reason, "connection");
  assert.ok(!calls.some((c) => c.url.includes("1234")));
});

test("insights are requested for the logged-in user", async () => {
  await getInsights("7");
  assert.equal(calls[0].url, BASE + "/api/ai/users/7/insights?months=6&explain=true");
  await getInsights(7, 3, false);
  assert.equal(calls[1].url, BASE + "/api/ai/users/7/insights?months=3&explain=false");
});

test("advisor question and history are posted as JSON", async () => {
  nextResponse.body = { answer: "You spent €10.00.", source: "llm", reason: null };
  const history = [{ role: "user", content: "hi" }, { role: "assistant", content: "hello" }];
  const reply = await askAdvisor(3, "Where am I spending most?", history);

  assert.equal(calls[0].url, BASE + "/api/ai/users/3/chat");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0].options.body), { question: "Where am I spending most?", history, months: 6 });
  assert.equal(reply.answer, "You spent €10.00.");
});

test("unusual spending scan, alerts and mark-as-read", async () => {
  await scanUnusualSpending(4);
  await getAlerts(4, true);
  await markAlertRead(4, 12);
  assert.deepEqual(calls.map((c) => [c.options.method || "GET", c.url]), [
    ["POST", BASE + "/api/ai/users/4/anomalies/scan"],
    ["GET", BASE + "/api/ai/users/4/alerts?unread_only=true"],
    ["PATCH", BASE + "/api/ai/users/4/alerts/12/read"],
  ]);
});

test("category prediction sends the merchant and a numeric user id", async () => {
  nextResponse.body = { category_id: 1, category_name: "Groceries", confidence: 0.95, source: "rule", reason: "x" };
  const result = await predictCategory("5", "Tesco", false);
  assert.deepEqual(JSON.parse(calls[0].options.body), { merchant_name: "Tesco", user_id: 5, use_llm: false });
  assert.equal(result.category_name, "Groceries");
});

// ---- errors reuse the team's request() messages ----
test("backend error detail is shown to the user", async () => {
  nextResponse = { status: 404, body: { detail: "User not found" } };
  await assert.rejects(getInsights(999), { message: "User not found" });
});

test("validation errors show the first message", async () => {
  nextResponse = { status: 422, body: { detail: [{ msg: "String should have at least 1 character" }] } };
  await assert.rejects(askAdvisor(1, ""), { message: "String should have at least 1 character" });
});

test("backend not running gives a clear message", async () => {
  nextResponse = { networkError: true };
  await assert.rejects(getAIStatus(), { message: "Could not reach the server. Is the backend running?" });
});

// ---- display helpers ----
const insights = {
  currency: "EUR",
  categories: [
    { category_name: "Groceries", total: 268.92, share_pct: 41.2 },
    { category_name: "Rent", total: 0, share_pct: 0 },
  ],
  monthly: { months: [{ label: "October 2026", total: 300.5, complete: true }, { label: "November 2026", total: 112.14, complete: false }] },
  budgets: [{ budget_id: 1, is_active: true }, { budget_id: 2, is_active: false }],
};

test("chart data comes from the API response", () => {
  assert.deepEqual(categoryChartData(insights), [{ name: "Groceries", value: 268.92, share: 41.2 }]);
  assert.deepEqual(monthlyChartData(insights).map((m) => [m.month, m.amount, m.complete]), [
    ["Oct", 300.5, true],
    ["Nov", 112.14, false],
  ]);
  assert.deepEqual(activeBudgets(insights).map((b) => b.budget_id), [1]);
});

test("empty or missing insights give empty charts", () => {
  assert.deepEqual(categoryChartData(null), []);
  assert.deepEqual(monthlyChartData({}), []);
  assert.deepEqual(activeBudgets(undefined), []);
});

test("money formatting", () => {
  assert.equal(formatMoney(1234.5), "€1,234.50");
  assert.equal(formatMoney(3, "USD"), "$3.00");
  assert.equal(formatMoney(3, "CHF"), "3.00 CHF");
  assert.equal(formatMoney(null), "–");
});

test("source labels say where AI text came from", () => {
  assert.match(sourceLabel("llm", null), /local AI model/);
  assert.match(sourceLabel("fallback", "connection"), /offline/);
  assert.match(sourceLabel("fallback", "unverified_figures"), /could not be checked/);
});

test("chat history keeps only the last turns in the backend's shape", () => {
  const messages = [
    { role: "user", content: "a" },
    { role: "assistant", content: "b", source: "llm", reason: null },
    { role: "user", content: "" },
    { role: "user", content: "c" },
  ];
  assert.deepEqual(chatHistory(messages, 2), [
    { role: "assistant", content: "b" },
    { role: "user", content: "c" },
  ]);
});
