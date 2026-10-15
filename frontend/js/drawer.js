
import { api } from "./api.js";
import { el, clear } from "./dom.js";
import { fmtMoney, fmtNum, fmtMinutes, fmtMiles, fmtPct, prettyDateTime } from "./format.js";

function section(title, rows) {
  return [
    el("h3", { text: title }),
    el("dl", {}, rows.flatMap(([label, value, total]) => [
      el("dt", { class: total ? "total" : null, text: label }),
      el("dd", { class: total ? "total" : null, text: value }),
    ])),
  ];
}

const yesNo = (v) => (v ? "Yes" : "No");

export function createDrawer({ root, title, sub, body, closeButton }) {
  let trigger = null;

  function close() {
    root.hidden = true;
    document.querySelectorAll("tr.open").forEach((r) => r.classList.remove("open"));
    if (trigger && document.contains(trigger)) trigger.focus();
    trigger = null;
  }

  closeButton.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !root.hidden) close();
  });

  async function open(tripId, triggerElement) {
    trigger = triggerElement || null;
    document.querySelectorAll("tr.open").forEach((r) => r.classList.remove("open"));
    if (trigger && trigger.tagName === "TR") trigger.classList.add("open");
    root.hidden = false;
    title.textContent = "Loading trip...";
    sub.textContent = "";
    clear(body);
    closeButton.focus();

    try {
      const t = await api(`/api/trips/${tripId}`);
      title.textContent = `${t.pickup_zone} to ${t.dropoff_zone}`;
      sub.textContent = `${t.pickup_borough} to ${t.dropoff_borough}. Picked up ${prettyDateTime(t.pickup_datetime)}.`;

      const charges = [["Meter fare", fmtMoney(t.fare_amount)]];
      const optional = [
        ["Extra", t.extra], ["MTA tax", t.mta_tax], ["Tolls", t.tolls_amount],
        ["Improvement surcharge", t.improvement_surcharge], ["Congestion surcharge", t.congestion_surcharge],
        ["Airport fee", t.airport_fee], ["Congestion pricing fee", t.cbd_congestion_fee],
      ];
      for (const [label, value] of optional) if (value > 0) charges.push([label, fmtMoney(value)]);
      charges.push(["Tip", t.tip_pct == null ? "Not recorded" : fmtMoney(t.tip_amount)]);
      charges.push(["Total paid", fmtMoney(t.total_amount), true]);

      body.append(
        ...section("The ride", [
          ["Distance", fmtMiles(t.trip_distance)],
          ["Ride time", fmtMinutes(t.trip_duration_min)],
          ["Average speed", `${fmtNum(t.avg_speed_mph)} mph`],
          ["Passengers", String(t.passenger_count)],
          ["Payment", t.payment_type],
          ["Rate", t.rate_code],
          ["Airport trip", yesNo(t.is_airport_trip)],
          ["Crosses boroughs", yesNo(t.is_cross_borough)],
        ]),
        ...section("What was charged", charges),
        ...section("Worked out from the data", [
          ["Fare per mile", fmtMoney(t.fare_per_mile)],
          ["Tip as a share of the fare", t.tip_pct == null ? "Only recorded for card payments" : fmtPct(t.tip_pct)],
          ["Taxi vendor", t.vendor],
        ]),
      );
    } catch (err) {
      title.textContent = "Could not load this trip";
      sub.textContent = err.message;
    }
  }

  return { open, close };
}
