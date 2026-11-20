import { useState } from "react";
import { useNavigate } from "react-router-dom";

function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  function handleSubmit(e) {
    e.preventDefault();

    if (email === "" || password === "") {
      setError("Please fill in both fields");
      return;
    }

    setError("");
    navigate("/dashboard");
  }

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        width: "100%",
        minHeight: "100vh",
        background: "#0A0A0C",
        fontFamily: "sans-serif",
      }}
    >
      {/* Left side - app image */}
      <div
        style={{
          flex: "1",
          minWidth: "320px",
          padding: "60px 60px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div
            style={{
              width: "32px",
              height: "32px",
              borderRadius: "9px",
              background: "#8884d8",
              color: "white",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: "bold",
            }}
          >
            S
          </div>
          <span style={{ color: "#F2F1ED", fontWeight: "bold", fontSize: "16px" }}>
            SpendGPT
          </span>
        </div>

        <div>
          <p
            style={{
              color: "#8884d8",
              fontSize: "13px",
              letterSpacing: "1px",
              marginBottom: "14px",
            }}
          >
            YOUR FINANCE COPILOT
          </p>
          <h1
            style={{
              color: "#F2F1ED",
              fontSize: "40px",
              lineHeight: "1.2",
              margin: "0 0 16px",
            }}
          >
            Make every euro make sense.
          </h1>
          <p style={{ color: "#8B8B93", fontSize: "15px", maxWidth: "360px" }}>
            Get a clearer picture of your spending and make confident choices
            with your money.
          </p>
        </div>

        <p style={{ color: "#8B8B93", fontSize: "12px" }}>
          A little more clarity, every day.
        </p>
      </div>

      {/* Right side - login form */}
      <div
        style={{
          flex: "1",
          minWidth: "320px",
          background: "#151518",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "40px 20px",
        }}
      >
        <form onSubmit={handleSubmit} style={{ width: "100%", maxWidth: "320px" }}>
          <p style={{ color: "#8B8B93", fontSize: "12px", marginBottom: "6px" }}>
            WELCOME BACK
          </p>
          <h2 style={{ color: "#F2F1ED", margin: "0 0 6px" }}>
            Log in to SpendGPT
          </h2>
          <p style={{ color: "#8B8B93", fontSize: "13px", marginBottom: "26px" }}>
            Enter your details to continue.
          </p>

          <div style={{ marginBottom: "16px" }}>
            <label style={{ color: "#8B8B93", fontSize: "13px" }}>Email</label>
            <input
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{
                width: "100%",
                marginTop: "6px",
                padding: "10px",
                background: "#0A0A0C",
                border: "1px solid #232328",
                borderRadius: "8px",
                color: "#F2F1ED",
              }}
            />
          </div>

          <div style={{ marginBottom: "20px" }}>
            <label style={{ color: "#8B8B93", fontSize: "13px" }}>Password</label>
            <input
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{
                width: "100%",
                marginTop: "6px",
                padding: "10px",
                background: "#0A0A0C",
                border: "1px solid #232328",
                borderRadius: "8px",
                color: "#F2F1ED",
              }}
            />
          </div>

          {error && (
            <p style={{ color: "#FF5C5C", fontSize: "13px", marginBottom: "12px" }}>
              {error}
            </p>
          )}

          <button
            type="submit"
            style={{
              width: "100%",
              padding: "12px",
              background: "#8884d8",
              color: "white",
              border: "none",
              borderRadius: "8px",
              fontWeight: "bold",
              cursor: "pointer",
            }}
          >
            Log in →
          </button>

          <p
            style={{
              textAlign: "center",
              color: "#8B8B93",
              fontSize: "13px",
              marginTop: "18px",
            }}
          >
            New to SpendGPT?{" "}
            <span style={{ color: "#8884d8" }}>Create account</span>
          </p>
        </form>
      </div>
    </div>
  );
}

export default Login;
