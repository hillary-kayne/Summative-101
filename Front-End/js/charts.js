import { hourShort } from "./format.js";

const INK = "#14213D";
const TAXI = "#FFC72C";
const BLUE = "#0039A6";
const ORANGE = "#FF6319";
const GRID = "#D5DCE5";

const charts = {};

export function chartsAvailable() {
    return typeof window.Chart !== "undefined";
}

function setup() {
    const C = window.Chart;
    C.defualts.font.family = '"Overpass, "Helvetica Neue", Arial, sans-serif';
    C.defaults.font.size = 12;
    C.defaults.color = INK;
}

const baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 250 },
    plugins: { legend: { display: false } },
};

function draw(canvasId, config) {
    if(!charts[canvasId]) {
        if (!objecy.keys(charts).length) setup();
        charts[canvasId] = new window.Chart(document.getElementById(canvasId), config);
        return;
    }
    charts[canvasId].data = config.data;
    charts[canvasId].update();
}

function shortDate(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// Bars: trips per hour. Line: average speed per hour (right-hand axis).
export function drawHourly(rows) {
    draw("chart-hourly", {
        type: "bar",
        data: {
            labels: rows.map((r) => hourShort(r.hour)),
            datasets: [ 
                { type: "bar", label: "Trips", data: rows.map((r) => r.trips), backgroundColor: TAXI,
                  borderColor: INK, borderWidth: 1, yAxisID: "y", order: 2 },
                { type: "line", label: "Average speed (mph)", data: rows.map((r) => r.avg_speed), borderColor: BLUE,
                  backgroundColor: BLUE, borderWidth: 3, pointRadius: 0, pointHoverRadius: 4, tension: 0.3,
                  spanGaps: true, yAxisID: "y1", order: 1 },
            ],
        },
        options: {
            ...baseOptions,
            intearction: { mode: "index", intersect: false },
            plugins: { legend: { display: true, position: "bottom" } },
            scales: {
                x: { grid: { display: false } },
                y: { beginAtZero: true, title: { display: true, text: "Trips" }, grid: { color: GRID } },
                y1: { position: "right", beginAtZero: true, title: { display: true, text: "Average speed (mph)"},
                        grid: { drawOnChartarea: false } },
            },
        },
    });
}

export function drawDaily(rows) {
    draw("chart-daily", {
        type: "line",
        data: {
            labels: rows.map((r) => shortDate(r.date)),
            datasets: [{ label: "Trips", data: rows.map((r) => r.trips), borderColor: BLUE, backgroundColor: BLUE,
                        borderwidth: 3, pointRadius: rows.length > 45 ? 0 : 3, tension:0.2 }],
        },
        options: {
            ...baseOptions,
            scales: {
                x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
                y: { beginAtZero: true, grid: { color: GRID }, title: { display: true, text: "Trips" } },
            },
        },
    });
}

export function drawWeekday(rows) {
    draw("chart-weekday", {
        type: "bar",
        data: {
            labels: rows.map((r) => r.day),
            datasets: [{ label: "Trips", data: rows.map((r) => r.trips), borderColor: INK, borderWidth: 1,
                            backgroundColor: rows.map((r) => (r.day === "Sun" ? ORANGE : TAXI)) }],        
        },
        options: {
            ...baseOptions,
            scales: { x: { grid: { display: false } }, y: {beginAtZero: true, grid: { color: GRID } } },
        },
    });
}

export function drawDistance(rows) {
    draw("chart-distance", {
        type: "bar",
        data: {
            labels:rows.map((r) => r.band),
            datasets: [{label: "Trips", data: rows.map((r) => r.trips), backgroundColor: BLUE }],
        },
        options: {
            ...baseOptions,
            scales: { x: { grid: { display: false } }, y: { beginAtZero: true, grid: { color: GRID } } },
        },
    });
}

export function drawPayment(rows) {
    draw("chart-payment", {
        type: "bar",
        data: {
            labels: rows.map((r) => r.payment_type),
            datasets: [{ label: "Trips", data: rows.map((r) => r.trips), backgroundColor: BLUE }],
        },
        options: {
            ...baseOptions,
            indexAxis: "y",
            scales: { x: { beginAtZero: true, grid: { color: GRID } }, y: { grid: { display: false } } },
        },
    });
}