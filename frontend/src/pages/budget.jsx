import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getCategories, getMonthBudgets, saveMonthBudget } from "../services/budget";

function Budget() {
  const navigate = useNavigate();
  const userId = sessionStorage.getItem("userId");

  const [categories, setCategories] = useState([]);
  // the budgets already saved in the database for this month, by category_id
  const [saved, setSaved] = useState({});
  // what is typed in each box, by category_id
  const [amounts, setAmounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // if nobody is logged in, go back to the login page
  // otherwise load the categories and the budgets saved for this month
  useEffect(() => {
    if (!userId) {
      navigate("/");
      return;
    }

    async function loadBudget() {
      try {
        const categoryList = await getCategories();
        const budgets = await getMonthBudgets(userId);

        const savedByCategory = {};
        const start = {};
        for (const budget of budgets) {
          if (budget.category_id !== null) {
            savedByCategory[budget.category_id] = budget;
          }
        }
        for (const category of categoryList) {
          const budget = savedByCategory[category.category_id];
          start[category.category_id] = budget ? String(Number(budget.amount_limit)) : "";
        }

        setCategories(categoryList);
        setSaved(savedByCategory);
        setAmounts(start);
      } catch (err) {
        setError(err.message);
      }
      setLoading(false);
    }

    loadBudget();
  }, [userId, navigate]);

  function handleChange(categoryId, value) {
    setAmounts({ ...amounts, [categoryId]: value });
    setError("");
  }

  async function handleSave() {
    // check everything first so nothing is half saved because of a typo
    for (const category of categories) {
      const amount = Number(amounts[category.category_id] || 0);
      if (isNaN(amount) || amount < 0) {
        setError("Please enter a number of 0 or more for " + category.category_name);
        return;
      }
    }

    setSaving(true);
    setError("");
    try {
      for (const category of categories) {
        const existing = saved[category.category_id] || null;
        const amount = Number(amounts[category.category_id] || 0);
        const before = existing ? Number(existing.amount_limit) : 0;

        // only send the ones that changed
        if (amount !== before) {
          await saveMonthBudget(userId, category.category_id, amount, existing);
        }
      }
      navigate("/profile");
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  // the total of everything typed so far
  let total = 0;
  for (const category of categories) {
    total = total + (Number(amounts[category.category_id]) || 0);
  }

  if (!userId) {
    return null;
  }

  return (
    <div
      style={{
        width: "100%",
        minHeight: "100vh",
        boxSizing: "border-box",
        display: "flex",
        justifyContent: "center",
        padding: "28px 20px 48px",
        background: "radial-gradient(ellipse at 50% 0%, #241f4a 0%, #0a0a10 55%, #050507 100%)",
        color: "#F2F1ED",
      }}
    >
      <div style={{ width: "100%", maxWidth: "460px" }}>
        {/* top bar */}
                {/* back arrow, fixed to the top-left corner of the screen */}
        <button
          onClick={() => navigate("/profile")}
          style={{
            position: "fixed",
            top: "20px",
            left: "20px",
            width: "42px",
            height: "42px",
            borderRadius: "14px",
            border: "none",
            background: "#151518",
            boxShadow: "6px 6px 14px #060608, -4px -4px 12px #1d1d22",
            color: "#cfcfd6",
            fontSize: "22px",
            cursor: "pointer",
          }}
        >
          ‹
        </button>

        <h2 style={{ margin: 0, textAlign: "center" }}>Create budget</h2>

        <p style={{ color: "#8B8B93", marginTop: "22px" }}>
          How much do you want to spend each month on:
        </p>

        {loading && <p style={{ color: "#8B8B93" }}>Loading…</p>}

        {!loading && categories.length === 0 && !error && (
          <p style={{ color: "#8B8B93" }}>There are no categories yet. Run the seed script in the backend first.</p>
        )}

        {categories.map((category) => (
          <div
            key={category.category_id}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginTop: "10px",
              padding: "12px 16px",
              borderRadius: "18px",
              background: "#131316",
              boxShadow: "5px 5px 12px #060608, -3px -3px 10px #1b1b20",
            }}
          >
            <label htmlFor={"budget-" + category.category_id} style={{ fontSize: "15px" }}>
              {category.category_name}
            </label>
            <div>
              <span style={{ color: "#8B8B93", marginRight: "6px" }}>€</span>
              <input
                id={"budget-" + category.category_id}
                type="number"
                min="0"
                placeholder="0"
                value={amounts[category.category_id] ?? ""}
                onChange={(e) => handleChange(category.category_id, e.target.value)}
                style={{
                  width: "90px",
                  padding: "8px",
                  borderRadius: "8px",
                  border: "1px solid #232328",
                  background: "#0A0A0C",
                  color: "#F2F1ED",
                  fontSize: "15px",
                  textAlign: "right",
                }}
              />
            </div>
          </div>
        ))}

        <p style={{ textAlign: "right", margin: "16px 4px 0" }}>
          <span style={{ color: "#8B8B93" }}>Total per month: </span>
          <b>€{total.toFixed(2)}</b>
        </p>

        {error && <p style={{ color: "#FF5C5C" }}>{error}</p>}

        <button
          onClick={handleSave}
          disabled={loading || saving || categories.length === 0}
          style={{
            opacity: loading || saving ? 0.6 : 1,
            width: "100%",
            marginTop: "16px",
            padding: "14px",
            borderRadius: "18px",
            border: "none",
            background: "#8884d8",
            color: "white",
            fontWeight: "bold",
            fontSize: "15px",
            cursor: "pointer",
          }}
        >
          {saving ? "Saving..." : "Save budget"}
        </button>
      </div>
    </div>
  );
}

export default Budget;
