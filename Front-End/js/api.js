export class ApiError extends Error {}

// If the page is opened straight from a file, fall back to the default backend address.
const BASE = window.location.protocol.startsWith("http") ? window.location.origin : "http://127.0.0.1:5000";

export async function api(path, params = {}) {
    const url = new URL(path, BASE);
    for (const[key, value] of Object.entries(params)) {
        if (value !== "" && value != null && value !== false) url.searchParams.set(key, value);
    }

    let response;
    try {
        response = await fetch(url);
    } catch {
        throw new ApiError("Can't reach the backend. Start it with: python backend/app.py");
    }

    let body =null;
    try {
        body = await response.json();
    } catch {
        /* the body was not JSON; the status check below still reportsthe problem */
    }
    if (!response.ok) {
        throw new ApiError((body && body.error) || `The server answered with status ${response.status}.`);
    }
    return body;
}