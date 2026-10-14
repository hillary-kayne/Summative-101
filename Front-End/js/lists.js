import { el, clear } from "./dom.js";
import { METRICS, fmtInt, fmtMoney, fmtNum, fmtPct, fmtMiles, fmtMinutes, prettyDateTime } from "./format.js";

function barWidth(value, max) {
    if (!max || value == null) return "4%";
    return `${Math.max(4, (value / max) * 100).toFixed(0)}%`; 
}

function emptyItem(ol, text) {
    ol.append(el("li", { class: "muted", text}));
}

export function renderZoneList(ol, rows, metric, selectedId, onSelect) {
    clear(ol);
    if(!rows.length) return emptyItem(ol, "no zones to rank with these filters.");
    const max = rows[0][metric];
    rows.forEach((r, i) => {
        ol.append(el("li", {},
            el("button", {
                type: "button",
                style: `--w:${barWidth(r[metric], max)}`,
                "aria-pressed": String(r.location_id === selectedId),
                onclick: () => onSelect(r.location_id),
            },
                el("span", { class: "rank-no", text: String(i+1) }),
                el("span", { class: "name", text: r.zone_name }, el("small", { text: `${r.borough}, ${fmtInt(r.trips)} pickups`})),
                el("span", { class: "val", text: METRICS[metric].format(r[metric]) }),
            )));
    });
}

export function renderRoutes(ol, rows, onPick) {
    clear(ol);
    if (!rows.length) return emptyItem(ol, "No routes with these filters.");
    const max = rows[0].trips;
    rows.forEach((r, i) => {
        ol.append(el("li", {},
            el("button", { type: "button", style: `--w:${barWidth(r.trips, max)}`, onclick: () => onPick(r) },
                el("span", { class: "rank-no", text: String(i + 1) }),
                el("span", { class: "name", text: `${r.pickup_zone} to ${r.dropoff_zone}` },
                    el("small", { text: `Average total paid ${fmtMoney(r.avg_total)}` })),
                el("span", {class: "val", text: `${fmtInt(r.trips)} trips`}),
            )));
    });
}

const TRIP_VALUE = {
    trip_distance: fmtMiles,
    total_amount: fmtMoney,
    trip_duration_min: fmtMinutes,
    trip_pct: fmtPct,
    avg_speed_mph: (v) => `${fmtNum(v)} mph`,
    fare_per_mile: (v) => `${fmtMoney(v)} per mi`,
};

export function renderTopTrips(ol, rows, metric, onOpen) {
    clear(ol);
    if (!rows.length) return emptyItem(ol, "No trips match these filters.");
    const max = rows[0].value;
    rows.forEach((r, i) => {
        const button = el("button", { type: "button", style: `--w:${barWidth(r.value, max)}` },
            el("span", { class: "rank-no", text: String(i + 1) }),
            el("span", { class: "name", text: `${r.pickup_zone} to ${r.dropoff_zone}` },
                el("small", { text: prettyDateTime(r.pickup_datetime) })),
            el("span", { class: "val", text:TRIP_VALUE[metric](r.value) }),
        );
        button.addEventListener("click", () => onOpen(r.trip_id, button));
        ol.append(el("li", {}, button));
    });
}
