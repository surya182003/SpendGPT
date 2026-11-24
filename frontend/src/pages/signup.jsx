import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { registerUser } from "../services/api";

function Signup() {
  const navigate = useNavigate();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();

    if (firstName === "" || lastName === "" || email === "" || password === "") {
      setError("Please fill in all the fields");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    setError("");
    setLoading(true);
    try {
      // the backend makes the account and gives back the new user (with the user id)
      const user = await registerUser(firstName, lastName, email, password);
      // log the new user in straight away
      sessionStorage.setItem("email", user.email);
      sessionStorage.setItem("userId", user.user_id);
      navigate("/dashboard");
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  }

  // the boxes on the form, so we do not have to write the same code four times
  const fields = [
    { label: "First name", type: "text", placeholder: "Your first name", value: firstName, setValue: setFirstName },
    { label: "Last name", type: "text", placeholder: "Your last name", value: lastName, setValue: setLastName },
    { label: "Email", type: "email", placeholder: "you@example.com", value: email, setValue: setEmail },
    { label: "Password", type: "password", placeholder: "At least 8 characters", value: password, setValue: setPassword },
  ];

  return (
    <div
      style={{
        width: "100%",
        minHeight: "100vh",
        background: "#0A0A0C",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "40px 20px",
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          width: "100%",
          maxWidth: "360px",
          background: "#151518",
          borderRadius: "12px",
          padding: "32px",
        }}
      >
        <p style={{ color: "#8B8B93", fontSize: "12px", marginBottom: "6px" }}>GET STARTED</p>
        <h2 style={{ color: "#F2F1ED", margin: "0 0 6px" }}>Create your account</h2>
        <p style={{ color: "#8B8B93", fontSize: "13px", marginBottom: "26px" }}>
          Enter your details to join SpendGPT.
        </p>

        {fields.map((field) => (
          <div key={field.label} style={{ marginBottom: "16px" }}>
            <label style={{ color: "#8B8B93", fontSize: "13px" }}>{field.label}</label>
            <input
              type={field.type}
              placeholder={field.placeholder}
              value={field.value}
              onChange={(e) => field.setValue(e.target.value)}
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
        ))}

        {error && <p style={{ color: "#FF5C5C", fontSize: "13px", marginBottom: "12px" }}>{error}</p>}

        <button
          type="submit"
          disabled={loading}
          style={{
            width: "100%",
            padding: "12px",
            background: "#8884d8",
            color: "white",
            border: "none",
            borderRadius: "8px",
            fontWeight: "bold",
            cursor: "pointer",
            opacity: loading ? 0.6 : 1,
          }}
        >
          {loading ? "Creating account..." : "Create account →"}
        </button>

        <p style={{ textAlign: "center", color: "#8B8B93", fontSize: "13px", marginTop: "18px" }}>
          Already have an account?{" "}
          <button
            type="button"
            onClick={() => navigate("/")}
            style={{
              background: "none",
              border: "none",
              padding: 0,
              color: "#8884d8",
              fontSize: "13px",
              cursor: "pointer",
            }}
          >
            Log in
          </button>
        </p>
      </form>
    </div>
  );
}

export default Signup;
