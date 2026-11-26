// Budget calls to the FastAPI backend. Budgets are saved in the database now (budgets table).
// A budget here is one row per category for the current month, for example
// { budget_id: 3, category_id: 1, amount_limit: "200.00", start_date: "2026-11-01", end_date: "2026-11-30" }

import { request } from "./api.js";

// turns a Date into "YYYY-MM-DD" using the local date (toISOString can be a day off)
function toDateString(day) {
  const month = String(day.getMonth() + 1).padStart(2, "0");
  const date = String(day.getDate()).padStart(2, "0");
  return day.getFullYear() + "-" + month + "-" + date;
}

// first and last day of this month, the period every budget on the budget page uses
export function getThisMonth() {
  const today = new Date();
  const first = new Date(today.getFullYear(), today.getMonth(), 1);
  const last = new Date(today.getFullYear(), today.getMonth() + 1, 0);
  return { start: toDateString(first), end: toDateString(last) };
}

// all the spending categories from the database: [{ category_id, category_name, spend_type }]
export async function getCategories() {
  return request("/api/categories/");
}

// the budgets of this user that are running today
export async function getMonthBudgets(userId) {
  const budgets = await request("/api/budgets/user/" + userId);
  const today = toDateString(new Date());

  const current = [];
  for (const budget of budgets) {
    if (budget.start_date <= today && budget.end_date >= today) {
      current.push(budget);
    }
  }
  return current;
}

// Saves the budget of one category for this month.
// existing is the budget already saved for that category (or null if there is none)
// an amount of 0 means the user cleared it, so the saved one gets deleted
export async function saveMonthBudget(userId, categoryId, amount, existing) {
  if (amount <= 0) {
    if (existing) {
      await request("/api/budgets/" + existing.budget_id + "?user_id=" + userId, { method: "DELETE" });
    }
    return;
  }

  // when editing, keep the dates the budget already had
  const month = getThisMonth();
  const body = {
    category_id: categoryId,
    amount_limit: amount,
    start_date: existing ? existing.start_date : month.start,
    end_date: existing ? existing.end_date : month.end,
  };

  if (existing) {
    await request("/api/budgets/" + existing.budget_id + "?user_id=" + userId, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } else {
    await request("/api/budgets/?user_id=" + userId, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }
}

// adds up the limits of all the budgets
export function getBudgetTotal(budgets) {
  let total = 0;
  for (const budget of budgets) {
    total = total + Number(budget.amount_limit);
  }
  return total;
}
