// The budget is kept in the browser for now (there is no budget API in the backend yet).
// Each user gets their own saved budget, for example { Food: 200, Transport: 50, ... }

// the categories you can set a budget for (the same ones as the dashboard charts)
export const CATEGORIES = ["Food", "Transport", "Entertainment", "Other"];

// gives back the saved budget of this user, or null if they have not made one yet
export function getBudget(userId) {
  const saved = localStorage.getItem("budget_" + userId);
  if (saved) {
    return JSON.parse(saved);
  }
  return null;
}

export function saveBudget(userId, budget) {
  localStorage.setItem("budget_" + userId, JSON.stringify(budget));
}

// adds up all the categories
export function getBudgetTotal(budget) {
  let total = 0;
  for (const name of CATEGORIES) {
    total = total + (budget[name] || 0);
  }
  return total;
}
