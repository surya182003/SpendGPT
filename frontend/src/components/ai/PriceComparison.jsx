import { useEffect, useState } from "react";
import { comparePrices, getUserReceipts } from "../../services/api.js";
import { formatMoney } from "../../services/ai.js";
import { button, card, colors, mutedText } from "./aiStyles.js";

// "aldi" -> "Aldi", "supervalu" -> "SuperValu"
function storeName(store) {
  if (!store) {
    return "";
  }
  if (store === "supervalu") {
    return "SuperValu";
  }
  return store[0].toUpperCase() + store.slice(1);
}

// "2026-10-07" -> "07/10/2026"
function showDate(text) {
  if (!text) {
    return "";
  }
  const parts = String(text).slice(0, 10).split("-");
  return parts[2] + "/" + parts[1] + "/" + parts[0];
}

const cellStyle = { padding: "6px 8px", borderBottom: "1px solid " + colors.border, textAlign: "left" };
const numberCell = { ...cellStyle, textAlign: "right", whiteSpace: "nowrap" };

// Lets the user pick one of their saved receipts and compares every item with the
// online prices at Aldi, Tesco, SuperValu, Dunnes and Lidl (from BasketWatch).
// latestReceiptId is the receipt that was just scanned, so it gets picked straight away.
function PriceComparison({ userId, latestReceiptId }) {
  const [receipts, setReceipts] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [result, setResult] = useState(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");

  // load the receipts again whenever a new one is scanned
  useEffect(() => {
    if (!userId) {
      return;
    }
    getUserReceipts(userId)
      .then((list) => {
        setReceipts(list);
        if (latestReceiptId) {
          setSelectedId(String(latestReceiptId));
        } else if (list.length > 0) {
          setSelectedId((current) => current || String(list[0].transaction_id));
        }
      })
      .catch((err) => setError(err.message));
  }, [userId, latestReceiptId]);

  async function handleCompare() {
    setChecking(true);
    setError("");
    setResult(null);
    try {
      setResult(await comparePrices(userId, selectedId));
    } catch (err) {
      setError(err.message);
    }
    setChecking(false);
  }

  return (
    <div style={{ ...card, marginTop: "30px" }}>
      <h3 style={{ marginTop: 0 }}>🛒 Compare prices</h3>
      <p style={mutedText}>
        See what your grocery receipt would cost at Aldi, Tesco, SuperValu, Dunnes and Lidl today.
      </p>

      {receipts.length === 0 ? (
        <p style={mutedText}>Scan a receipt first, then you can compare its prices here.</p>
      ) : (
        <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center" }}>
          <select
            value={selectedId}
            onChange={(e) => {
              setSelectedId(e.target.value);
              setResult(null);
            }}
            disabled={checking}
            style={{
              padding: "8px",
              borderRadius: "6px",
              border: "1px solid " + colors.border,
              background: colors.page,
              color: colors.text,
              fontSize: "14px",
              colorScheme: "dark",
              maxWidth: "100%",
            }}
          >
            {receipts.map((receipt) => (
              <option key={receipt.transaction_id} value={receipt.transaction_id}>
                {receipt.merchant_name} · {showDate(receipt.transaction_date)} · {formatMoney(receipt.total_amount)}
              </option>
            ))}
          </select>
          <button
            onClick={handleCompare}
            disabled={checking || !selectedId}
            style={{ ...button, opacity: checking ? 0.6 : 1 }}
          >
            {checking ? "Checking prices…" : "Compare prices"}
          </button>
        </div>
      )}

      {error && <p style={{ color: colors.red }}>{error}</p>}

      {result && (
        <div style={{ marginTop: "16px" }}>
          <p style={{ margin: "0 0 10px" }}>
            {result.possible_saving > 0 ? (
              <>
                You could have saved <b style={{ color: colors.green }}>{formatMoney(result.possible_saving)}</b> on
                the {result.items_matched} of {result.items_total} items found online
              </>
            ) : (
              <>
                You already paid the lowest price on the {result.items_matched} of {result.items_total} items
                found online
              </>
            )}
            {result.as_of && <span style={mutedText}> (online prices of {showDate(result.as_of)})</span>}
          </p>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
              <thead>
                <tr style={{ color: colors.muted }}>
                  <th style={cellStyle}>Item</th>
                  <th style={numberCell}>You paid</th>
                  <th style={numberCell}>{result.store ? storeName(result.store) + " online" : "Same shop"}</th>
                  <th style={numberCell}>Cheapest</th>
                  <th style={numberCell}>Saving</th>
                </tr>
              </thead>
              <tbody>
                {result.items.map((item, index) => (
                  <tr key={index}>
                    <td style={cellStyle}>
                      {item.item_name}
                      {item.quantity > 1 && <span style={mutedText}> × {item.quantity}</span>}
                      {item.matched && <div style={{ ...mutedText, fontSize: "11px" }}>{item.matched_product}</div>}
                    </td>
                    <td style={numberCell}>{formatMoney(item.paid_unit_price)}</td>
                    {item.matched ? (
                      <>
                        <td style={numberCell}>{formatMoney(item.same_store_price)}</td>
                        <td style={numberCell}>
                          {formatMoney(item.cheapest_price)}
                          <div style={{ ...mutedText, fontSize: "11px" }}>{storeName(item.cheapest_store)}</div>
                        </td>
                        <td style={{ ...numberCell, color: item.possible_saving > 0 ? colors.green : colors.muted }}>
                          {item.possible_saving > 0 ? formatMoney(item.possible_saving) : "–"}
                        </td>
                      </>
                    ) : (
                      <td colSpan={3} style={{ ...numberCell, ...mutedText }}>
                        not found online
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p style={{ ...mutedText, fontSize: "12px", marginBottom: 0 }}>{result.note}</p>
        </div>
      )}
    </div>
  );
}

export default PriceComparison;
