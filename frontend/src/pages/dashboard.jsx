import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { addManualExpense, getCategories, uploadReceipt } from "../services/api";
import { categoryChartData, formatMoney, getInsights, monthlyChartData } from "../services/ai.js";
import AdvisorChat from "../components/ai/AdvisorChat";
import AIStatusBadge from "../components/ai/AIStatusBadge";
import CategoryPredictor from "../components/ai/CategoryPredictor";
import InsightsPanel from "../components/ai/InsightsPanel";
import UnusualSpending from "../components/ai/UnusualSpending";
import { CHART_COLORS } from "../components/ai/aiStyles.js";
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

// the charts use the real figures from the AI insights endpoint
const COLORS = CHART_COLORS;
const buttonStyle = {
  padding: "10px 16px",
  borderRadius: "6px",
  fontSize: "14px",
  cursor: "pointer",
};
const purpleButton = { ...buttonStyle, background: "#8884d8", color: "white", border: "1px solid #8884d8" };
const darkButton = { ...buttonStyle, background: "#151518", color: "#F2F1ED", border: "1px solid #232328" };


// boxes and labels of the manual expense form
const inputStyle = {
  width: "100%",
  boxSizing: "border-box",
  marginTop: "6px",
  padding: "10px",
  borderRadius: "6px",
  border: "1px solid #232328",
  background: "#0A0A0C",
  color: "#F2F1ED",
  fontSize: "14px",
  colorScheme: "dark",
};
const labelStyle = { display: "block", marginTop: "14px", fontSize: "13px", color: "#8B8B93" };

// today's date as YYYY-MM-DD, the format the date box uses
function todayString() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return now.getFullYear() + "-" + month + "-" + day;
}
function Dashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  // the profile page can open the dashboard with the chat box already open
  const [showChat, setShowChat] = useState(location.state?.openChat === true);
  const userId = sessionStorage.getItem("userId");

  // AI insights (also used for the two charts)
  const [insights, setInsights] = useState(null);
  const [insightsLoading, setInsightsLoading] = useState(Boolean(userId));
  const [insightsError, setInsightsError] = useState("");

  const loadInsights = useCallback(async () => {
    if (!userId) {
      return;
    }
    setInsightsLoading(true);
    setInsightsError("");
    try {
      setInsights(await getInsights(userId));
    } catch (err) {
      setInsightsError(err.message);
    }
    setInsightsLoading(false);
  }, [userId]);

  useEffect(() => {
    loadInsights();
  }, [loadInsights]);

  const categoryData = categoryChartData(insights);
  const monthlyData = monthlyChartData(insights);
  const [receiptImage, setReceiptImage] = useState(null);

  const [receiptFile, setReceiptFile] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [message, setMessage] = useState("");
  const [messageIsError, setMessageIsError] = useState(false);

  
  // the manual expense form (the dropdown above Scan a Receipt)
  const [showManual, setShowManual] = useState(false);
  const [categories, setCategories] = useState([]);
  const [expenseName, setExpenseName] = useState("");
  const [expenseAmount, setExpenseAmount] = useState("");
  const [expenseCategory, setExpenseCategory] = useState("");
  const [expenseDate, setExpenseDate] = useState(todayString());
  const [expenseRecurring, setExpenseRecurring] = useState(false);
  const [savingExpense, setSavingExpense] = useState(false);
  const [expenseMessage, setExpenseMessage] = useState("");
  const [expenseIsError, setExpenseIsError] = useState(false);

  // get the category names for the dropdown
  useEffect(() => {
    getCategories()
      .then(setCategories)
      .catch(() => setCategories([]));
  }, []);

  function handleReceiptSelect(e) {
    const file = e.target.files[0];
    e.target.value = ""; // so the same file can be picked again later
    if (file) {
      setReceiptFile(file);
      setReceiptImage(URL.createObjectURL(file));
      setMessage("");
    }
  }

  // hides the picture and the buttons, so the dashboard looks normal again
  function handleReceiptRemove() {
    setReceiptImage(null);
    setReceiptFile(null);
  }

  // shows a short message under the Scan Receipt button for a few seconds
  function showMessage(text, isError) {
    setMessage(text);
    setMessageIsError(isError);
    setTimeout(() => setMessage(""), 8000);
  }

  async function handleProcessReceipt() {
    const userId = sessionStorage.getItem("userId");
    if (!userId) {
      navigate("/");
      return;
    }

    setProcessing(true);
    setMessage("");
    try {
      const receipt = await uploadReceipt(userId, receiptFile);
      handleReceiptRemove();
      let text = "Receipt saved: " + receipt.merchant_name + " · €" + receipt.total_amount.toFixed(2);
      if (receipt.category_name) {
        text = text + " · Category: " + receipt.category_name;
      }
      if (receipt.requires_review) {
        text = text + " (please double-check it)";
      }
      showMessage(text, false);
      loadInsights(); // the new receipt changes the totals
    } catch (err) {
      showMessage(err.message, true);
    }
    setProcessing(false);
  }

    // shows a short message under the manual expense form for a few seconds
  function showExpenseMessage(text, isError) {
    setExpenseMessage(text);
    setExpenseIsError(isError);
    setTimeout(() => setExpenseMessage(""), 8000);
  }

  async function handleSaveExpense(e) {
    e.preventDefault();
    if (!userId) {
      navigate("/");
      return;
    }

    // keep two decimals, like 12.5 or 12.50
    const amount = Math.round(Number(expenseAmount) * 100) / 100;
    if (expenseName.trim() === "" || !(amount > 0) || expenseDate === "") {
      showExpenseMessage("Please fill in what it was for, the amount and the date", true);
      return;
    }

    setSavingExpense(true);
    setExpenseMessage("");
    try {
      const saved = await addManualExpense(userId, {
        merchant_name: expenseName.trim(),
        amount: amount,
        transaction_date: expenseDate,
        category_id: expenseCategory === "" ? null : Number(expenseCategory),
        is_recurring: expenseRecurring,
      });

      // the backend picks a category when none was chosen
      let text = "Expense saved: " + saved.merchant_name + " · €" + Number(saved.amount).toFixed(2);
      const category = categories.find((c) => c.category_id === saved.category_id);
      if (category) {
        text = text + " · Category: " + category.category_name;
      }
      showExpenseMessage(text, false);

      // empty the form for the next expense
      setExpenseName("");
      setExpenseAmount("");
      setExpenseCategory("");
      setExpenseDate(todayString());
      setExpenseRecurring(false);
      loadInsights(); // the new expense changes the totals
    } catch (err) {
      showExpenseMessage(err.message, true);
    }
    setSavingExpense(false);
  }

  return (
    <div
      style={{
        width: "100%",
        minHeight: "100vh",
        boxSizing: "border-box",
        padding: "30px 5%",
        position: "relative",
        background: "#0A0A0C",
        color: "#F2F1ED",
      }}
    >
      <button
        onClick={() => navigate("/profile")}
        style={{
          position: "absolute",
          top: "20px",
          right: "5%",
          width: "40px",
          height: "40px",
          borderRadius: "50%",
          background: "#151518",
          border: "1px solid #232328",
          color: "#F2F1ED",
          cursor: "pointer",
          fontSize: "18px",
        }}
      >
        👤
      </button>

      <h2>Dashboard</h2>
      <p style={{ color: "#8B8B93" }}>Welcome! You are logged in.</p>
      {userId && <AIStatusBadge />}


      <div
        style={{
          border: "2px dashed #232328",
          borderRadius: "10px",
          padding: "20px",
          marginTop: "30px",
          background: "#151518",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>✍️ Add an expense manually</h3>
          <button onClick={() => setShowManual(!showManual)} style={darkButton}>
            {showManual ? "Close ▴" : "Open ▾"}
          </button>
        </div>

        {showManual && (
          <form onSubmit={handleSaveExpense} style={{ maxWidth: "420px", margin: "0 auto" }}>
            <label style={labelStyle}>
               Merchant / what was it for? 
              <input
                type="text"
                maxLength={100}
                value={expenseName}
                onChange={(e) => setExpenseName(e.target.value)}
                placeholder=" e.g. Rent, Groceries, Clothing"
                style={inputStyle}
              />
            </label>

            <label style={labelStyle}>
              Amount (€)
              <input
                type="number"
                min="0.01"
                step="0.01"
                value={expenseAmount}
                onChange={(e) => setExpenseAmount(e.target.value)}
                placeholder="0.00"
                style={inputStyle}
              />
            </label>

            <label style={labelStyle}>
              Category
              <select
                value={expenseCategory}
                onChange={(e) => setExpenseCategory(e.target.value)}
                style={inputStyle}
              >
                <option value="">Choose for me automatically</option>
                {categories.map((c) => (
                  <option key={c.category_id} value={c.category_id}>
                    {c.category_name}
                  </option>
                ))}
              </select>
            </label>

            <label style={labelStyle}>
              Date
              <input
                type="date"
                value={expenseDate}
                onChange={(e) => setExpenseDate(e.target.value)}
                style={inputStyle}
              />
            </label>

            <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
              <input
                type="checkbox"
                checked={expenseRecurring}
                onChange={(e) => setExpenseRecurring(e.target.checked)}
              />
              This repeats every month
            </label>

            <button
              type="submit"
              disabled={savingExpense}
              style={{ ...purpleButton, width: "100%", marginTop: "18px", opacity: savingExpense ? 0.6 : 1 }}
            >
              {savingExpense ? "Saving..." : "Save expense"}
            </button>
          </form>
        )}

        {expenseMessage && (
          <p style={{ marginTop: "16px", textAlign: "center", color: expenseIsError ? "#FF5C5C" : "#82ca9d" }}>
            {expenseMessage}
          </p>
        )}
      </div>

      <div
        style={{
          border: "2px dashed #232328",
          borderRadius: "10px",
          padding: "20px",
          textAlign: "center",
          marginTop: "30px",
          background: "#151518",
        }}
      >
        <h3 style={{ marginTop: 0 }}>Scan a Receipt</h3>

        {receiptImage ? (
          <div>
            <img
              src={receiptImage}
              alt="Scanned receipt"
              style={{ maxWidth: "200px", maxHeight: "200px", borderRadius: "6px" }}
            />
            <br />
            <div style={{ marginTop: "12px", display: "flex", gap: "10px", justifyContent: "center" }}>
              <button
                onClick={handleProcessReceipt}
                disabled={processing}
                style={{ ...purpleButton, opacity: processing ? 0.6 : 1 }}
              >
                {processing ? "Processing..." : "Process receipt"}
              </button>
              <button
                onClick={handleReceiptRemove}
                disabled={processing}
                style={{ ...darkButton, opacity: processing ? 0.6 : 1 }}
              >
                Remove
              </button>
            </div>
          </div>
        ) : (
          <p style={{ color: "#8B8B93" }}>
            Take a photo of your receipt or upload one to add it automatically
          </p>
        )}

        <div style={{ marginTop: "12px" }}>
          <label
            style={{
              background: "#8884d8",
              color: "white",
              padding: "10px 16px",
              borderRadius: "6px",
              cursor: "pointer",
              display: "inline-block",
            }}
          >
            📷 Scan Receipt
            <input
              type="file"
              accept="image/*"
              capture="environment"
              onChange={handleReceiptSelect}
              style={{ display: "none" }}
            />
          </label>
        </div>

        {message && (
          <p style={{ marginTop: "16px", color: messageIsError ? "#FF5C5C" : "#82ca9d" }}>
            {message}
          </p>
        )}
      </div>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "20px",
          marginTop: "30px",
          width: "100%",
        }}
      >
        <div style={{ flex: "1", minWidth: "320px", background: "#151518", borderRadius: "10px", padding: "16px" }}>
          <h3>Spending by Category</h3>
          {categoryData.length === 0 && (
            <p style={{ color: "#8B8B93" }}>{insightsLoading ? "Loading…" : "No spending to show yet."}</p>
          )}
          {categoryData.length > 0 && (
          <ResponsiveContainer width="100%" height={340}>
            <PieChart>
              <Pie
                data={categoryData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={120}
                label={{ fill: "#F2F1ED" }}
              >
                {categoryData.map((entry, index) => (
                  <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value) => formatMoney(value, insights.currency)}
                contentStyle={{ background: "#0A0A0C", border: "1px solid #232328", color: "#F2F1ED" }}
              />
            </PieChart>
          </ResponsiveContainer>
          )}
        </div>

        <div style={{ flex: "1", minWidth: "320px", background: "#151518", borderRadius: "10px", padding: "16px" }}>
          <h3>Monthly Spending</h3>
          {monthlyData.length === 0 && (
            <p style={{ color: "#8B8B93" }}>{insightsLoading ? "Loading…" : "No spending to show yet."}</p>
          )}
          {monthlyData.length > 0 && (
          <ResponsiveContainer width="100%" height={340}>
            <BarChart data={monthlyData}>
              <XAxis dataKey="month" tick={{ fill: "#8B8B93" }} />
              <YAxis tick={{ fill: "#8B8B93" }} />
              <Tooltip
                labelFormatter={(_month, rows) => (rows && rows[0] ? rows[0].payload.label : "")}
                formatter={(value) => formatMoney(value, insights.currency)}
                contentStyle={{ background: "#0A0A0C", border: "1px solid #232328", color: "#F2F1ED" }}
              />
              <Bar dataKey="amount" fill="#8884d8" />
            </BarChart>
          </ResponsiveContainer>
          )}
        </div>
      </div>

      {userId ? (
        <div style={{ marginTop: "30px", display: "flex", flexDirection: "column", gap: "20px" }}>
          <InsightsPanel insights={insights} loading={insightsLoading} error={insightsError} onRetry={loadInsights} />
          <div style={{ display: "flex", flexWrap: "wrap", gap: "20px" }}>
            <div style={{ flex: "1", minWidth: "320px" }}>
              <UnusualSpending userId={userId} />
            </div>
            <div style={{ flex: "1", minWidth: "320px" }}>
              <CategoryPredictor userId={userId} />
            </div>
          </div>
        </div>
      ) : (
        <p style={{ color: "#8B8B93", marginTop: "30px" }}>Log in to see your AI insights.</p>
      )}

      <button
        onClick={() => setShowChat(!showChat)}
        style={{
          position: "fixed",
          bottom: "20px",
          left: "20px",
          width: "50px",
          height: "50px",
          borderRadius: "50%",
          background: "#8884d8",
          color: "white",
          border: "none",
          cursor: "pointer",
          fontSize: "20px",
        }}
      >
        💬
      </button>

      {showChat && userId && <AdvisorChat userId={userId} onClose={() => setShowChat(false)} />}
    </div>
  );
}

export default Dashboard;