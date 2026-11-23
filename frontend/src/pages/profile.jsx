import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getUserReceipts } from "../services/api";
import { getBudget, getBudgetTotal } from "../services/budget";

function Profile() {
  const navigate = useNavigate();
  const email = sessionStorage.getItem("email");
  const userId = sessionStorage.getItem("userId");
  const [weekTotal, setWeekTotal] = useState(null);

  // the budget this user made on the budget page (null if they have not made one)
  const budget = getBudget(userId);

  // if nobody is logged in, go back to the login page
  // otherwise add up what was spent in the last 7 days
  useEffect(() => {
    if (!email) {
      navigate("/");
      return;
    }

    getUserReceipts(userId)
      .then((receipts) => {
        const weekAgo = new Date();
        weekAgo.setDate(weekAgo.getDate() - 7);

        let total = 0;
        for (const receipt of receipts) {
          if (new Date(receipt.transaction_date) >= weekAgo) {
            total = total + receipt.total_amount;
          }
        }
        setWeekTotal(total);
      })
      .catch(() => setWeekTotal(null));
  }, [email, userId, navigate]);

  function handleLogout() {
    sessionStorage.clear();
    navigate("/");
  }

  if (!email) {
    return null;
  }

  const menuItems = [
    {
      icon: "💰",
      title: budget ? "Edit budget" : "Create budget",
      subtitle: "Food, transport, entertainment and other",
      onClick: () => navigate("/budget"),
    },
    {
      icon: "🧾",
      title: "Receipts",
      subtitle: "Scan and review OCR results",
      onClick: () => navigate("/dashboard"),
    },
    {
      icon: "✨",
      title: "AI advisor",
      subtitle: "Runs locally on Ollama",
      onClick: () => navigate("/dashboard", { state: { openChat: true } }),
    },
  ];

  const tileStyle = {
    flex: "1",
    borderRadius: "20px",
    background: "#121215",
    boxShadow: "inset 3px 3px 8px #060608, inset -2px -2px 6px #1b1b20",
    padding: "14px",
  };
  const tileLabelStyle = { fontSize: "11px", letterSpacing: "1.2px", color: "#8B8B93" };
  const tileValueStyle = { fontSize: "22px", fontWeight: "bold", margin: "4px 0 0" };

  return (
    <div
      style={{
        width: "100%",
        minHeight: "100vh",
        boxSizing: "border-box",
        position: "relative",
        display: "flex",
        justifyContent: "center",
        padding: "28px 20px 48px",
        background: "radial-gradient(ellipse at 50% 0%, #241f4a 0%, #0a0a10 55%, #050507 100%)",
        color: "#F2F1ED",
      }}
    >
      <div style={{ width: "100%", maxWidth: "460px" }}>
        {/* back arrow */}
        <button
          onClick={() => navigate("/dashboard")}
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

        <h2 style={{ margin: 0, textAlign: "center" }}>Profile</h2>

        {/* avatar and email */}
        <div style={{ textAlign: "center", marginTop: "22px" }}>
          <div
            style={{
              width: "124px",
              height: "124px",
              borderRadius: "50%",
              padding: "4px",
              margin: "0 auto",
              boxSizing: "border-box",
              background: "conic-gradient(from 200deg, #8884d8, #b9b6ff, #5b57b8, #8884d8)",
              boxShadow: "0 0 40px rgba(136,132,216,0.35)",
            }}
          >
            <div
              style={{
                width: "100%",
                height: "100%",
                borderRadius: "50%",
                border: "5px solid #0A0A0C",
                boxSizing: "border-box",
                background: "radial-gradient(circle at 30% 25%, #2b2a3f, #121218)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "52px",
                fontWeight: "bold",
                color: "#d9d7ff",
              }}
            >
              {email[0].toUpperCase()}
            </div>
          </div>

          <h3 style={{ fontSize: "22px", margin: "18px 0 0", wordBreak: "break-all" }}>{email}</h3>
          <span
            style={{
              display: "inline-block",
              marginTop: "10px",
              fontSize: "12px",
              letterSpacing: "1.5px",
              color: "#b9b6ff",
              background: "rgba(136,132,216,0.14)",
              border: "1px solid rgba(136,132,216,0.35)",
              padding: "6px 14px",
              borderRadius: "20px",
            }}
          >
            SPENDGPT MEMBER
          </span>
        </div>

        {/* quick stats */}
        <div style={{ display: "flex", gap: "12px", marginTop: "22px" }}>
          <div style={tileStyle}>
            <span style={tileLabelStyle}>THIS WEEK</span>
            <p style={tileValueStyle}>{weekTotal === null ? "—" : "€" + weekTotal.toFixed(2)}</p>
          </div>
          <div style={tileStyle}>
            <span style={tileLabelStyle}>MONTHLY BUDGET</span>
            <p style={tileValueStyle}>{budget ? "€" + getBudgetTotal(budget).toFixed(2) : "Not set"}</p>
          </div>
        </div>

        {/* menu */}
        <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "16px" }}>
          {menuItems.map((item) => (
            <button
              key={item.title}
              onClick={item.onClick}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "14px",
                width: "100%",
                textAlign: "left",
                border: "none",
                borderRadius: "18px",
                background: "#131316",
                boxShadow: "5px 5px 12px #060608, -3px -3px 10px #1b1b20",
                padding: "12px 14px",
                color: "#F2F1ED",
                cursor: "pointer",
                font: "inherit",
              }}
            >
              <span
                style={{
                  width: "38px",
                  height: "38px",
                  borderRadius: "12px",
                  background: "rgba(136,132,216,0.14)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "18px",
                }}
              >
                {item.icon}
              </span>
              <span style={{ flex: "1" }}>
                <span style={{ display: "block", fontSize: "15px" }}>{item.title}</span>
                <span style={{ display: "block", fontSize: "12px", color: "#8B8B93" }}>{item.subtitle}</span>
              </span>
              <span style={{ color: "#55555d", fontSize: "20px" }}>›</span>
            </button>
          ))}
        </div>

        <button
          onClick={handleLogout}
          style={{
            width: "100%",
            marginTop: "14px",
            padding: "14px",
            borderRadius: "18px",
            border: "1px solid rgba(255,92,92,0.45)",
            background: "transparent",
            color: "#ff7a7a",
            fontWeight: "bold",
            fontSize: "15px",
            cursor: "pointer",
          }}
        >
          Log out
        </button>
      </div>
    </div>
  );
}

export default Profile;
