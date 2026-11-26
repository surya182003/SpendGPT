// Colours and styles shared by the AI components.
// Same palette as the dashboard, login and profile pages.

export const colors = {
  page: "#0A0A0C",
  card: "#151518",
  border: "#232328",
  text: "#F2F1ED",
  muted: "#8B8B93",
  accent: "#8884d8",
  green: "#82ca9d",
  yellow: "#ffc658",
  orange: "#ff8042",
  red: "#FF5C5C",
};

export const CHART_COLORS = ["#8884d8", "#82ca9d", "#ffc658", "#ff8042", "#4fc3f7", "#f06292", "#aed581", "#ba68c8", "#90a4ae", "#ffb74d"];

export const card = {
  background: colors.card,
  border: "1px solid " + colors.border,
  borderRadius: "10px",
  padding: "16px",
};

export const mutedText = { color: colors.muted, fontSize: "13px" };

export const button = {
  padding: "8px 14px",
  borderRadius: "6px",
  fontSize: "14px",
  cursor: "pointer",
  background: colors.accent,
  color: "white",
  border: "1px solid " + colors.accent,
};

export const secondaryButton = {
  ...button,
  background: colors.card,
  color: colors.text,
  border: "1px solid " + colors.border,
};

export const input = {
  width: "100%",
  boxSizing: "border-box",
  padding: "8px 10px",
  background: colors.page,
  border: "1px solid " + colors.border,
  borderRadius: "6px",
  color: colors.text,
  fontSize: "14px",
};

export const tooltipStyle = { background: colors.page, border: "1px solid " + colors.border, color: colors.text };
