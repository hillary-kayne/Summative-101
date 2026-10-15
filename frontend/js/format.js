
const integer = new Intl.NumberFormat("en-US");

export const fmtInt = (v) => (v == null ? "-" : integer.format(v));
export const fmtMoney = (v) => (v == null ? "-" : "$" + Number(v).toFixed(2));
export const fmtNum = (v, digits = 1) => (v == null ? "-" : Number(v).toFixed(digits));
export const fmtPct = (v) => (v == null ? "-" : Number(v).toFixed(1) + "%");
export const fmtMiles = (v) => (v == null ? "-" : Number(v).toFixed(1) + " mi");
export const fmtMinutes = (v) => (v == null ? "-" : Math.round(v) + " min");

export function hourLabel(h) {
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${hour12} ${h < 12 ? "am" : "pm"}`;
}

export function hourShort(h) {
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${hour12}${h < 12 ? "a" : "p"}`;
}

// '2025-03-14' -> 'March 14, 2025'
export function prettyDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
}

// '2025-03-14 08:05:00' -> 'Mar 14, 2025, 8:05 am'
export function prettyDateTime(text) {
  const [date, time] = text.split(" ");
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  const day = new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  return `${day}, ${hh % 12 === 0 ? 12 : hh % 12}:${String(mm).padStart(2, "0")} ${hh < 12 ? "am" : "pm"}`;
}

// The numbers the map and the ranked lists can show
export const METRICS = {
  trips:        { label: "Pickups",          format: fmtInt },
  avg_total:    { label: "Average fare",     format: fmtMoney },
  avg_tip_pct:  { label: "Average tip",      format: fmtPct },
  avg_distance: { label: "Average distance", format: fmtMiles },
};