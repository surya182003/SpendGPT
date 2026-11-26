import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CATEGORIES, getBudget, saveBudget, getBudgetTotal } from "../services/budget";

function Budget() {
  const navigate = useNavigate();
  const userId = sessionStorage.getItem("userId");

  // start with the amounts already saved (empty boxes if there is no budget yet)
  const [amounts, setAmounts] = useState(() => {
    const saved = getBudget(userId) || {};
    const start = {};
    for (const name of CATEGORIES) {
      start[name] = saved[name] ?? "";
    }
    return start;
  });
  const [error, setError] = useState("");

  // if nobody is logged in, go back to the login page
  useEffect(() => {
    if (!userId) {
      navigate("/");
    }
  }, [userId, navigate]);

  function handleChange(name, value) {
    setAmounts({ ...amounts, [name]: value });
    setError("");
  }

  function handleSave() {
    const budget = {};
    for (const name of CATEGORIES) {
      const amount = Number(amounts[name] || 0);
      if (isNaN(amount) || amount < 0) {
        setError("Please enter a number of 0 or more for " + name);
        return;
      }
      budget[name] = amount;
    }
    saveBudget(userId, budget);
    navigate("/profile");
  }

  // the total of everything typed so far
  const typed = {};
  for (const name of CATEGORIES) {
    typed[name] = Number(amounts[name]) || 0;
  }
  const total = getBudgetTotal(typed);

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

        {CATEGORIES.map((name) => (
          <div
            key={name}
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
            <label htmlFor={"budget-" + name} style={{ fontSize: "15px" }}>
              {name}
            </label>
            <div>
              <span style={{ color: "#8B8B93", marginRight: "6px" }}>€</span>
              <input
                id={"budget-" + name}
                type="number"
                min="0"
                placeholder="0"
                value={amounts[name]}
                onChange={(e) => handleChange(name, e.target.value)}
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
          style={{
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
          Save budget
        </button>
      </div>
    </div>
  );
}

export default Budget;
