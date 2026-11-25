import { useEffect, useState } from "react";
import { getAIStatus } from "../../services/ai.js";
import { colors } from "./aiStyles.js";

const REASONS = {
  disabled: "AI is turned off in the backend settings",
  connection: "LM Studio is not running",
  timeout: "LM Studio did not answer in time",
  model_unavailable: "no model is loaded in LM Studio",
  invalid_response: "LM Studio gave an unexpected answer",
};

// Small pill that says whether the local AI model is available.
// Insights still work without it (they use summaries built from your figures).
function AIStatusBadge() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getAIStatus()
      .then((data) => !cancelled && setStatus(data))
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, []);

  let dot = colors.muted;
  let text = "Checking local AI…";
  let title = "";
  if (error) {
    dot = colors.red;
    text = "AI status unavailable";
    title = error;
  } else if (status && status.available) {
    dot = colors.green;
    text = "Local AI online";
    title = status.models && status.models.length ? "Model: " + (status.configured_model || status.models[0]) : "";
  } else if (status) {
    dot = colors.yellow;
    text = "Local AI offline – using summaries";
    title = REASONS[status.reason] || "";
  }

  return (
    <span
      title={title}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "8px",
        padding: "4px 10px",
        borderRadius: "999px",
        border: "1px solid " + colors.border,
        background: colors.card,
        color: colors.muted,
        fontSize: "12px",
      }}
    >
      <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: dot }} />
      {text}
    </span>
  );
}

export default AIStatusBadge;
