
import { el } from "./dom.js";
import { METRICS, fmtInt } from "./format.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const WIDTH = 700;
const PAD = 10;
const NO_DATA = "#E3E7EC";

// Colour scale: pale yellow -> taxi yellow -> deep rust
const STOPS = [[0, [255, 243, 194]], [0.5, [255, 176, 0]], [1, [138, 59, 0]]];

function rampColor(t) {
  for (let i = 1; i < STOPS.length; i++) {
    const [t0, c0] = STOPS[i - 1];
    const [t1, c1] = STOPS[i];
    if (t <= t1) {
      const f = (t - t0) / (t1 - t0);
      const rgb = c0.map((v, k) => Math.round(v + (c1[k] - v) * f));
      return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
    }
  }
  return `rgb(${STOPS[2][1].join(", ")})`;
}

// Every ring (outline) of a Polygon or MultiPolygon, as a flat list
function ringsOf(geometry) {
  return geometry.type === "Polygon" ? geometry.coordinates : geometry.coordinates.flat();
}

export function createMap({ svg, wrap, tooltip, legendMin, legendMax, onSelect }) {
  const zones = new Map();          // location_id -> { path, name, borough }
  let rowsById = new Map();
  let metric = "trips";

  function init(geojson) {
    let minLng = Infinity, maxLng = -Infinity, minLat = Infinity, maxLat = -Infinity;
    for (const f of geojson.features) {
      for (const ring of ringsOf(f.geometry)) {
        for (const [lng, lat] of ring) {
          if (lng < minLng) minLng = lng;
          if (lng > maxLng) maxLng = lng;
          if (lat < minLat) minLat = lat;
          if (lat > maxLat) maxLat = lat;
        }
      }
    }
    // One degree of longitude is shorter than one degree of latitude, so squeeze x by cos(latitude)
    const cosLat = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180);
    const scale = (WIDTH - 2 * PAD) / ((maxLng - minLng) * cosLat);
    const height = Math.round((maxLat - minLat) * scale + 2 * PAD);
    svg.setAttribute("viewBox", `0 0 ${WIDTH} ${height}`);
    const project = (lng, lat) => [PAD + (lng - minLng) * cosLat * scale, PAD + (maxLat - lat) * scale];

    for (const f of geojson.features) {
      const d = ringsOf(f.geometry)
        .map((ring) => "M" + ring.map(([lng, lat]) => project(lng, lat).map((n) => n.toFixed(1)).join(",")).join("L") + "Z")
        .join("");
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", d);
      path.setAttribute("fill", NO_DATA);
      const info = { path, name: f.properties.zone_name, borough: f.properties.borough };
      zones.set(f.properties.location_id, info);

      path.addEventListener("pointermove", (e) => showTip(e, f.properties.location_id));
      path.addEventListener("pointerleave", () => { tooltip.hidden = true; });
      path.addEventListener("click", () => onSelect(f.properties.location_id));
      svg.append(path);
    }
  }

  function showTip(event, id) {
    const info = zones.get(id);
    const row = rowsById.get(id);
    tooltip.replaceChildren(
      el("strong", { text: info.name }),
      el("div", { text: info.borough }),
      row
        ? el("div", { text: `${METRICS[metric].label}: ${METRICS[metric].format(row[metric])}` })
        : el("div", { text: "No trips start here with these filters" }),
      row && metric !== "trips" ? el("div", { text: `${fmtInt(row.trips)} pickups` }) : null,
    );
    tooltip.hidden = false;
    const box = wrap.getBoundingClientRect();
    let left = event.clientX - box.left + 14;
    if (left + tooltip.offsetWidth > box.width) left = event.clientX - box.left - tooltip.offsetWidth - 14;
    tooltip.style.left = `${Math.max(0, left)}px`;
    tooltip.style.top = `${Math.max(0, event.clientY - box.top + 14)}px`;
  }

  // rows: from /api/zones/stats. selectedId: the zone currently filtered, or null.
  function update(rows, newMetric, selectedId) {
    metric = newMetric;
    rowsById = new Map(rows.map((r) => [r.location_id, r]));
    const values = rows.map((r) => r[metric]).filter((v) => v != null);
    const min = values.length ? Math.min(...values) : 0;
    const max = values.length ? Math.max(...values) : 0;

    for (const [id, info] of zones) {
      const row = rowsById.get(id);
      const value = row ? row[metric] : null;
      if (value == null) {
        info.path.setAttribute("fill", NO_DATA);
      } else {
        const t = max === min ? 1 : (value - min) / (max - min);
        info.path.setAttribute("fill", rampColor(Math.pow(t, 0.75)));   // power < 1 lifts the low end so mid zones stay readable
      }
      const selected = id === selectedId;
      info.path.classList.toggle("selected", selected);
      if (selected) svg.append(info.path);       // move to the top so its thick outline isn't hidden
    }
    legendMin.textContent = METRICS[metric].format(min);
    legendMax.textContent = METRICS[metric].format(max);
  }

  return { init, update };
}
