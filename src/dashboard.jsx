import { useState } from "react";
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

// Sample data - replace with real data later
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

function Dashboard({ onLogout }) {
  const [showProfilePage, setShowProfilePage] = useState(false);
  const [showChat, setShowChat] = useState(false);
  const [chatMessage, setChatMessage] = useState("");
  const [receiptImage, setReceiptImage] = useState(null);

  function handleReceiptSelect(e) {
    const file = e.target.files[0];
    if (file) {
      setReceiptImage(URL.createObjectURL(file));
    }
  }

  // Profile page - shown instead of the dashboard when profile icon is clicked
  if (showProfilePage) {
    return (
      <div style={{ maxWidth: "400px", margin: "100px auto" }}>
        <h2>Profile</h2>
        <button onClick={() => setShowProfilePage(false)}>
          ← Back to Dashboard
        </button>
        <div style={{ marginTop: "30px" }}>
          <button onClick={onLogout}>Log Out</button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: "900px", margin: "0 auto", padding: "20px", position: "relative" }}>
      {/* Profile icon - top right */}
      <button
        onClick={() => setShowProfilePage(true)}
        style={{
          position: "absolute",
          top: "20px",
          right: "20px",
          width: "40px",
          height: "40px",
          borderRadius: "50%",
          background: "#ddd",
          border: "none",
          cursor: "pointer",
          fontSize: "18px",
        }}
      >
        👤
      </button>

      <h2>Dashboard</h2>
      <p>Welcome! You are logged in.</p>

      {/* OCR / receipt scanning section */}
      <div
        style={{
          border: "2px dashed #aaa",
          borderRadius: "10px",
          padding: "20px",
          textAlign: "center",
          marginTop: "30px",
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
            <button
              onClick={() => setReceiptImage(null)}
              style={{ marginTop: "10px" }}
            >
              Remove
            </button>
          </div>
        ) : (
          <p style={{ color: "#777" }}>
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
      </div>

      {/* Charts side by side */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "20px",
          marginTop: "30px",
        }}
      >
        <div style={{ flex: "1", minWidth: "300px" }}>
          <h3>Weekly Expenses</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={weeklyExpenses}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={100}
                label
              >
                {weeklyExpenses.map((entry, index) => (
                  <Cell
                    key={entry.name}
                    fill={COLORS[index % COLORS.length]}
                  />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div style={{ flex: "1", minWidth: "300px" }}>
          <h3>Monthly Expenses</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={monthlyExpenses}>
              <XAxis dataKey="month" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="amount" fill="#8884d8" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Chatbot button - bottom left */}
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

      {/* Chatbot textbox - floats on top of everything when open */}
      {showChat && (
        <div
          style={{
            position: "fixed",
            bottom: "80px",
            left: "20px",
            width: "280px",
            background: "white",
            border: "1px solid #ccc",
            borderRadius: "8px",
            padding: "12px",
            boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
            zIndex: 1000,
          }}
        >
          <p style={{ marginTop: 0, fontWeight: "bold" }}>Ask the AI</p>
          <textarea
            value={chatMessage}
            onChange={(e) => setChatMessage(e.target.value)}
            placeholder="Ask about your spending..."
            style={{ width: "100%", height: "80px" }}
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