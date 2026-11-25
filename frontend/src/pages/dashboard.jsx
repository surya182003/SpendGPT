import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { uploadReceipt } from "../services/api";
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

//sample data for charts replace with real data from backend when available
const weeklyExpenses = [
  { name: "Food", value: 40 },
  { name: "Transport", value: 20 },
  { name: "Entertainment", value: 15 },
  { name: "Other", value: 25 },
];

const monthlyExpenses = [
  { month: "Jan", amount: 320 },
  { month: "Feb", amount: 280 },
  { month: "Mar", amount: 350 },
  { month: "Apr", amount: 300 },
];

const COLORS = ["#8884d8", "#82ca9d", "#ffc658", "#ff8042"];
const buttonStyle = {
  padding: "10px 16px",
  borderRadius: "6px",
  fontSize: "14px",
  cursor: "pointer",
};
const purpleButton = { ...buttonStyle, background: "#8884d8", color: "white", border: "1px solid #8884d8" };
const darkButton = { ...buttonStyle, background: "#151518", color: "#F2F1ED", border: "1px solid #232328" };

function Dashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  // the profile page can open the dashboard with the chat box already open
  const [showChat, setShowChat] = useState(location.state?.openChat === true);
  const [chatMessage, setChatMessage] = useState("");
  const [receiptImage, setReceiptImage] = useState(null);

  const [receiptFile, setReceiptFile] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [message, setMessage] = useState("");
  const [messageIsError, setMessageIsError] = useState(false);

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
      if (receipt.requires_review) {
        text = text + " (please double-check it)";
      }
      showMessage(text, false);
    } catch (err) {
      showMessage(err.message, true);
    }
    setProcessing(false);
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
          <h3>Weekly Expenses</h3>
          <ResponsiveContainer width="100%" height={340}>
            <PieChart>
              <Pie
                data={weeklyExpenses}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={120}
                label={{ fill: "#F2F1ED" }}
              >
                {weeklyExpenses.map((entry, index) => (
                  <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: "#0A0A0C", border: "1px solid #232328", color: "#F2F1ED" }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div style={{ flex: "1", minWidth: "320px", background: "#151518", borderRadius: "10px", padding: "16px" }}>
          <h3>Monthly Expenses</h3>
          <ResponsiveContainer width="100%" height={340}>
            <BarChart data={monthlyExpenses}>
              <XAxis dataKey="month" tick={{ fill: "#8B8B93" }} />
              <YAxis tick={{ fill: "#8B8B93" }} />
              <Tooltip contentStyle={{ background: "#0A0A0C", border: "1px solid #232328", color: "#F2F1ED" }} />
              <Bar dataKey="amount" fill="#8884d8" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

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

      {showChat && (
        <div
          style={{
            position: "fixed",
            bottom: "80px",
            left: "20px",
            width: "280px",
            background: "#151518",
            border: "1px solid #232328",
            borderRadius: "8px",
            padding: "12px",
            boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
            zIndex: 1000,
          }}
        >
          <p style={{ marginTop: 0, fontWeight: "bold", color: "#F2F1ED" }}>Ask the AI</p>
          <textarea
            value={chatMessage}
            onChange={(e) => setChatMessage(e.target.value)}
            placeholder="Ask about your spending..."
            style={{
              width: "100%",
              height: "80px",
              background: "#0A0A0C",
              border: "1px solid #232328",
              borderRadius: "6px",
              color: "#F2F1ED",
              padding: "8px",
            }}
          />
          <br />
        
          <button onClick={() => setChatMessage("")} style={{ marginTop: "8px" }}>
            Send
          </button>
        </div>
      )}
    </div>
  );
}

export default Dashboard;