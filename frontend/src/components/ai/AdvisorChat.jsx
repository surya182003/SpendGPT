import { useEffect, useRef, useState } from "react";
import { askAdvisor, chatHistory, sourceLabel } from "../../services/ai.js";
import { button, colors, input, mutedText } from "./aiStyles.js";

const SUGGESTIONS = [
  "Where am I spending most of my money?",
  "How much did I spend on groceries this month?",
  "Am I exceeding my monthly budget?",
  "Which spending category increased the most?",
  "How can I reduce unnecessary expenses?",
];
const MAX_LENGTH = 500;

// The AI financial advisor chat. Questions go to FastAPI, which answers using
// only this user's calculated figures (via LM Studio, or a summary if it is offline).
function AdvisorChat({ userId, onClose }) {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef(null);

  useEffect(() => {
    if (endRef.current && endRef.current.scrollIntoView) {
      endRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, sending]);

  async function send(text) {
    const trimmed = text.trim();
    if (!trimmed || sending) {
      return;
    }
    if (trimmed.length > MAX_LENGTH) {
      setError("Questions can be at most " + MAX_LENGTH + " characters.");
      return;
    }
    const history = chatHistory(messages);
    setMessages((current) => [...current, { role: "user", content: trimmed }]);
    setQuestion("");
    setError("");
    setSending(true);
    try {
      const reply = await askAdvisor(userId, trimmed, history);
      setMessages((current) => [
        ...current,
        { role: "assistant", content: reply.answer, source: reply.source, reason: reply.reason },
      ]);
    } catch (err) {
      setError(err.message);
    }
    setSending(false);
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(question);
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        bottom: "80px",
        left: "20px",
        width: "min(360px, calc(100vw - 40px))",
        maxHeight: "70vh",
        display: "flex",
        flexDirection: "column",
        background: colors.card,
        border: "1px solid " + colors.border,
        borderRadius: "8px",
        boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
        zIndex: 1000,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px",
        borderBottom: "1px solid " + colors.border }}>
        <span style={{ fontWeight: "bold" }}>AI Financial Advisor</span>
        <button onClick={onClose} aria-label="Close chat"
          style={{ background: "none", border: "none", color: colors.muted, cursor: "pointer", fontSize: "16px" }}>
          ✕
        </button>
      </div>

      <div style={{ flex: "1", overflowY: "auto", padding: "12px" }}>
        {messages.length === 0 && (
          <div>
            <p style={{ ...mutedText, marginTop: 0 }}>
              Ask about your own spending. Answers use only your figures.
            </p>
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => send(s)} disabled={sending}
                style={{ display: "block", width: "100%", textAlign: "left", marginBottom: "6px", padding: "8px",
                  background: colors.page, color: colors.text, border: "1px solid " + colors.border,
                  borderRadius: "6px", cursor: "pointer", fontSize: "13px" }}>
                {s}
              </button>
            ))}
          </div>
        )}

        {messages.map((m, index) => (
          <div key={index} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start",
            marginBottom: "10px" }}>
            <div style={{ maxWidth: "85%", padding: "8px 10px", borderRadius: "8px", fontSize: "14px", lineHeight: 1.45,
              whiteSpace: "pre-wrap",
              background: m.role === "user" ? colors.accent : colors.page,
              color: m.role === "user" ? "white" : colors.text,
              border: m.role === "user" ? "none" : "1px solid " + colors.border }}>
              {m.content}
              {m.role === "assistant" && (
                <div style={{ ...mutedText, fontSize: "11px", marginTop: "6px" }}>{sourceLabel(m.source, m.reason)}</div>
              )}
            </div>
          </div>
        ))}

        {sending && <p style={{ ...mutedText, fontSize: "13px" }}>Thinking…</p>}
        {error && <p style={{ color: colors.red, fontSize: "13px" }}>{error}</p>}
        <div ref={endRef} />
      </div>

      <div style={{ padding: "12px", borderTop: "1px solid " + colors.border }}>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          maxLength={MAX_LENGTH}
          placeholder="Ask about your spending…"
          style={{ ...input, height: "60px", resize: "none" }}
        />
        <button onClick={() => send(question)} disabled={sending || !question.trim()}
          style={{ ...button, marginTop: "8px", width: "100%", opacity: sending || !question.trim() ? 0.6 : 1 }}>
          {sending ? "Sending…" : "Send"}
        </button>
      </div>
    </div>
  );
}

export default AdvisorChat;
