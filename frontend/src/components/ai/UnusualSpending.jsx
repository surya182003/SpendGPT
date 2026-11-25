import { useCallback, useEffect, useState } from "react";
import { formatMoney, getAlerts, markAlertRead, scanUnusualSpending } from "../../services/ai.js";
import { card, colors, mutedText, secondaryButton } from "./aiStyles.js";

const SEVERITY_COLORS = { high: colors.red, medium: colors.orange, low: colors.yellow };
const MAX_SHOWN = 5;

// Unusual spending found by the AI check, plus the user's unread notifications
// (stored in the alerts table, including budget alerts).
function UnusualSpending({ userId }) {
  const [scan, setScan] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      // the scan saves any new findings as alerts, so load the alerts afterwards
      const result = await scanUnusualSpending(userId);
      setScan(result);
      setAlerts(await getAlerts(userId, true));
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleMarkRead(alertId) {
    try {
      await markAlertRead(userId, alertId);
      setAlerts((current) => current.filter((a) => a.alert_id !== alertId));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={card}>
      <h3 style={{ marginTop: 0 }}>Unusual Spending</h3>

      {loading && <p style={mutedText}>Checking your recent transactions…</p>}

      {!loading && error && (
        <div>
          <p style={{ color: colors.red }}>{error}</p>
          <button onClick={load} style={secondaryButton}>Try again</button>
        </div>
      )}

      {!loading && !error && scan && (
        <div>
          {scan.flags.length === 0 ? (
            <p style={mutedText}>
              Nothing unusual in your last 90 days
              {scan.history_status === "insufficient" ? " (there isn't enough history to compare yet)" : ""}.
            </p>
          ) : (
            scan.flags.slice(0, MAX_SHOWN).map((flag, index) => (
              <div key={index} style={{ display: "flex", gap: "10px", marginBottom: "12px" }}>
                <span style={{ width: "8px", minWidth: "8px", height: "8px", borderRadius: "50%", marginTop: "6px",
                  background: SEVERITY_COLORS[flag.severity] }} />
                <div>
                  <div style={{ fontSize: "14px", fontWeight: "bold" }}>{flag.message}</div>
                  <div style={{ ...mutedText, fontSize: "13px" }}>{flag.explanation}</div>
                  {flag.transaction_date && (
                    <div style={{ ...mutedText, fontSize: "12px" }}>
                      {flag.transaction_date}
                      {flag.typical_amount !== null && " · usually " + formatMoney(flag.typical_amount)}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
          {scan.flags.length > MAX_SHOWN && (
            <p style={{ ...mutedText, fontSize: "12px" }}>+ {scan.flags.length - MAX_SHOWN} more</p>
          )}
          {scan.notes.map((note) => (
            <p key={note} style={{ ...mutedText, fontSize: "12px", margin: "4px 0" }}>{note}</p>
          ))}

          <h4 style={{ margin: "16px 0 8px" }}>Notifications {alerts.length > 0 && "(" + alerts.length + " unread)"}</h4>
          {alerts.length === 0 && <p style={mutedText}>You're all caught up.</p>}
          {alerts.slice(0, MAX_SHOWN).map((alert) => (
            <div key={alert.alert_id} style={{ display: "flex", justifyContent: "space-between", gap: "10px",
              alignItems: "flex-start", padding: "8px 0", borderTop: "1px solid " + colors.border }}>
              <span style={{ fontSize: "13px" }}>{alert.message}</span>
              <button onClick={() => handleMarkRead(alert.alert_id)}
                style={{ ...secondaryButton, padding: "4px 8px", fontSize: "12px", whiteSpace: "nowrap" }}>
                Mark read
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default UnusualSpending;
