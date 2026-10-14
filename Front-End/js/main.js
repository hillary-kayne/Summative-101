import { api } from "./api.js";
import {el, clear, debounce} from "./dom.js";
import { METRICS, fmtInt, fmtMoney, fmtMiles, fmtMinutes, fmtPct, hourLabel, prettyDate } from "./format.js";
import { chartsAvailable, drawHourly, drawDaily, drawWeekday, drawDistance, drawPayment } from "./charts.js";
import { createMap } from "./map.js";
import { renderZoneList, renderRoutes, renderTopTrips } from "./lists.js";
import { createTable } from "./table.js";
import { createDrawer } from "./drawer.js";

const $ = (id) => document.getElementById(id);
const form = $("filters");

const FILTER_NAMES = ["date_from", "date_to", "hour_min", "hour_max", "dist_min", "dist_max", "fare_min", "fare_max", "pu_borough", "pu_zone", "do_zone", "payment", "daytype"];
let meta = null;
let mapMetric = "trips";
let currentFilters = {};
let zoneStats = [];
let refreshId = 0;
let zoneListId = 0;
let topTripsId = 0;

// ----------------------------------------------------------------- pieces
const drawer = createDrawer({
    root: $("drawer"), title: $("drawer-title"), sub: $("drawer-sub"),
    body: $("drawer-body"), closeButton: $("drawer-close"),
});

const table = createTable({
    table: $("trips-table"), countE1: $("table-count"), pageInfo: $("page-info"),
    prev: $("prev"), next: $("next"), pageSize: $("page-size"),
    onOpen: (id, trigger) => drawer.open(id, trigger),
});

const map = createMap ({
    svg: $("map"), wrap: document.querySelector(".map-wrap"), tooltip: $("tooltip"),
    legendMin: $("legend-min"), legendMax: $("legend-max"),
    onSelect: (id) => selectZone(id),
});

// --------------------------------------------------------------------------- filters
function readFilters() {
    const f = {};
    for (const name of FILTER_NAMES) f[name] = form.elements[name].value;
    f.airport = form.elements.airport.checked ? "1" : "";
    return f;
}

function optionList(select, first, items) {
    clear(select);
    select.append(el("option", {value: "", text: first}));
    for (const [value, label] of items) select.append(el("option", { value: String(value), text: label }));
}

function fillPickupZones () {
    const borough = form.elements.pu_borough.value;
    const zones = meta.zones.filter((z) => !borough || z.borough === borough);
    optionList(form.elements.pu_zone, "Any zone", zones.map((z) => [z.id, z.name]));
}

function fillControls () {
    const hours = Array.from({ length: 24 }, (_, h) => [h, hourlabel(h)]);
    optionList(form.elements.hour_min, "Any time", hours);
    optionList(form.elements.hour_max, "Any time", hours);
    optionList(form.elements.pu_borough, "All boroughs", meta.boroughs.maps((b) => [b, b]));
    optionList(form.elements.payment, "Any payment", meta.payment_types,map((p) => [p.id, p.name]));
    optionList(form.elements.do_zone, "Any zone", meta.zones.map((z) => [z.id, z.name]));
    fillPickupZones();
    for (const name of ["date_from", "date_to"]) {
        form.elements[name].min = meta.date_min;
        form.elements[name].max = meta.date_max;
        }
}

function describeFilters(f){
    const active = Object.entries(f).filter(([, v]) => v !== "").length;
    $("filter-count").textContent = active
        ? `${active} ${active === 1 ? "filter is" : "filters are"} on.`
        : "No filters on. Showing every trip.";
        $("reset").disabled = active === 0;
}

function setPickupZone(id) {
    const zone = meta.zones.find((z) => z.id === id);
    const boroughSelect = form.elements.pu_borough;
    // Only clear the borough if it would contrac=dict the zone; otherwise leave the user's choice alone,
    // so clicking a zone does not hide the rest of the map.
    if (zone && boroughSelect.value && zone.borough !==boroughSelect.value) boroughSelect.value= "";
    fillPickupZones();
    form.elements.pu_zone.value = String(id);
}

function selectZone(id) {
    if (String(id) === form.elements.pu_zone.value) form.elements.pu_zone.value = "";  // click again to clear
    else setPickupZone(id);
    refreshId();
}

// ------------------------------------------------------------------- rendering
function showBanner(message) {
    $("banner").textContent = message;
    $("banner").hidden = false;
}

function renderKpis(s) {
    const none = s.trips === 0;
    $("kpi-trips").textContent = fmtInt(s.trips);
    $("kpi-fare").textContent = none ? "-" : fmtMoney(s.avg_total);
    $("kpi-distance").textContent = none ? "-" : fmtMiles(s.avg_distance);
    $("kpi_duration").textContent = none ? "-" : fmtMinutes(s.avg_duration);
    $("kpi-tip").textContent = none || s.avg_tip_pct == null ? "-" : fmtPct(s.avg_tip_pct);
    $("empty-note").hidden = !none;
}

function renderZoneTop(data) {
    const label = METRICS[data.metric].label;
    $("zones-title").textContent = `Top zones by ${label.toLowerCase()}`;
    $("zones-note").textContent = data.metric === "trips" ? "" : `Zones with fewer than ${data.min_trips} trips are left out.`;
    renderZoneList($("top-zones"), data.rows, data.metric, Number(form.elements.pu_zone.value) || null, selectZone);
}

async function loadZoneTop() {
    const id = ++zoneListId;
    const data = await api("/api/zones/top", { ...currentFilters, metric: mapMetric, k: 10 });
    if (id !== zoneListId) return;
    renderZoneTop(data);
}

// The standout-trips list scans every matching trip, so it loads on its own and never blocks the rest.
async function loadTopTrips() {
    const id = ++topTripsId;
    const metric = $("top-trip-metric").value;
    $("top-trips-note").textContent = "Scanning trips...";
    try {
        const data = await api("/api/trips/top", { ...currentFilters, metric, k: 10});
        if (id !== topTripsId) return;
        $("top-trips-note").textContent = `Found by scanning ${fmtInt(data.scanned)} trips with a heap built by hand that keeps only 10 in memory.`;
        renderTopTrips($("top-trips"), data.rows, metric, (tripId, trigger) => drawer.open(tripId, trigger));
    }   catch (err) {
        if (id === topTripId) $("top-trips-note").textContent = err.message;
    }
}

async function refresh() {
    const id = ++refreshId;
    const f = readFilters();
    currentFilters = f;
    describeFilters(f);
    $("main").classList.add("loading");

    try {
        const [summary, hourly, daily, weekly, distance, payment, zones, zoneTop, flows] = await Promise.all([
            api("/api/summary", f),
            api("/api/stats/hourly", f),
            api("/api/stats/daily", f),
            api("/api/stats/weekday", f),
            api("/api/stats/distance", f),
            api("/api/stats/payment", f),
            api("/api/zones/stats", f),
            api("/api/zones/top", { ...f, metric: mapMetric, k:10}),
            api("/api/flows/top", { ...f, k:10}),
        ]);
        if (id !== refreshId) return;               // the user changed a filter while this was loading

        renderKpis(summary);
        if (chartsAvailable()) {
            drawHourly(hourly); drawDaily(daily); drawWeekday(weekday); drawDistance(distance); drawPayment(payment);
        } else {
            showBanner("The chart library did not load. Check your internet connection and reload the page.");
        }
        zoneStats = zones;
        map.update(zones, mapMetric, Number(f.pu_zone) || null);
        renderZoneTop(zoneTop);
        renderRoutes($("top-routes"), flows.rows, (r) => {
            setPickupZone(r.pickup_id);
            form.elements.do_zone.value = String(r.dropoff_id);
            refresh();
        });
        if (chartsAvailable()) $("banner").hidden = true;

        loadTopTrips();
        await table.setFilters(f);
    } catch (err) {
        if (id === refreshId) showBanner(err.message);
    } finally {
        if (id === refreshId) $("main").classList.remove("loading");
    }
}

function renderQuality(data) {
    const body = $("quality-table").querySelector("tbody");
    clear(body);
    for (const r of data.rows) {
        const text = r.reason.replaceAll("-", " ");
        body.append(el("tr", {},
            el("td", { text: text.charAt(0).toUpperCase() + text.slice(1) }),
            el("td", { class: "num", text: fmtInt(r.record_count) }),
            el("td", {class: "num", text: `${r.percent_of_raw}%`}),
        ));
    }
}

// ---------------------------------------------------------------------- events
const refreshSoon = debounce(refresh, 350);
form.addEventListener("input", refreshSoon);
form.addEventListener("change", refreshSoon);
form.elements.pu_borough.addEventListener("change", fillPickupZones);       // runs before the refresh above fires
$("reset").addEventListener("click", () => {
    form.reset();
    fillPickupZones();
    refresh();
});

$("metric-buttons").addEventListener("click", (e) => {
    const button = e.target.closest("button[data-metric]");
    if (!button) return;
    mapMetric = button.dataset.metric;
    document.querySelectorAll("#metric-buttons button").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
    map.update(zoneStats, mapMetric, Number(form.elements.pu_zone.value) || null);     // instant: numbers are already loaded
    loadZoneTop().catch((err) => showBanner(err.message));
});

$("top-trip-metric").addEventListener("change", loadTopTrips);

// -------------------------------------------------------------------------------- start
async function init() {
    try {
        meta = await api("/api/meta");
        fillControls();
        ("period").textContent=`{fmtInt(meta.trips)} cleaned trips from ${prettyDate(meta.date_min)} to ${prettyDate(meta.date_max)}.`;
        map.init(await api("/api/zones/geojson"));
        api("/api/quality").then(renderQuality).catch(() => {});
        await refresh();
    } catch (err) {
        $("period").textContent = "The dashboard could not load.";
        showBanner(err.message);
    }
}

init();
