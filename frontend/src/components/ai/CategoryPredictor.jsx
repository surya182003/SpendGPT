import { useState } from "react";
import { CATEGORY_SOURCE, predictCategory } from "../../services/ai.js";
import { button, card, colors, input, mutedText } from "./aiStyles.js";

// Type a merchant name and see which category the AI would give it.
// Uses rules + the ML model first; the local LLM only if you tick the box.
function CategoryPredictor({ userId }) {
  const [merchant, setMerchant] = useState("");
  const [useLlm, setUseLlm] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    const name = merchant.trim();
    if (!name) {
      setError("Enter a merchant name");
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    try {
      setResult(await predictCategory(userId, name, useLlm));
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  }

  const matched = result && result.source !== "default";

  return (
    <div style={card}>
      <h3 style={{ marginTop: 0 }}>Category Prediction</h3>
      <p style={mutedText}>See which category SpendGPT would give a merchant.</p>
      <form onSubmit={handleSubmit} style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
        <input
          value={merchant}
          onChange={(e) => setMerchant(e.target.value)}
          maxLength={100}
          placeholder="e.g. Tesco Express, Spotify, Boojum"
          style={{ ...input, flex: "1", minWidth: "180px", width: "auto" }}
        />
        <button type="submit" disabled={loading} style={{ ...button, opacity: loading ? 0.6 : 1 }}>
          {loading ? "Predicting…" : "Predict"}
        </button>
      </form>
      <label style={{ ...mutedText, display: "flex", alignItems: "center", gap: "6px", marginTop: "8px" }}>
        <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />
        Ask the local AI if unsure (slower)
      </label>

      {error && <p style={{ color: colors.red, fontSize: "13px" }}>{error}</p>}

      {result && (
        <div style={{ marginTop: "12px", padding: "10px", background: colors.page, borderRadius: "6px" }}>
          {matched ? (
            <div>
              <span style={{ fontWeight: "bold", fontSize: "16px" }}>{result.category_name}</span>
              <span style={{ ...mutedText, marginLeft: "8px" }}>{Math.round(result.confidence * 100)}% confident</span>
            </div>
          ) : (
            <div style={{ fontWeight: "bold" }}>Not sure – you can choose the category yourself</div>
          )}
          <div style={{ ...mutedText, fontSize: "12px", marginTop: "4px" }}>
            {CATEGORY_SOURCE[result.source]} · {result.reason}
          </div>
        </div>
      )}
    </div>
  );
}

export default CategoryPredictor;
