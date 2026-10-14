import sqlite3
import sys

import Backend.app as backend

client = backend.app.test_client()
results = []


def check(name, ok, detail=""):
    ok = bool(ok)
    results.append(ok)
    print(f" [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def get(url):
    r = client.get(url)
    return r.status_code, r.get_json()


print("Basics")
code, body = get("/api/health")
check("health endpoint answers", code == 200 and body["status"] == "ok", f"{body['trips']:,} trips")
total = body["trips"]
code, meta = get("/api/meta")
check("meta lists boroughs, zones and payment types", code == 200 and meta["boroughs"] and meta["zones"] and meta["payment_types"])
code, body = get("/api/summary")
check("summary counts every trip when no filter is set", body["trips"] == total)
 
print("\nFilters")
code, filtered = get("/api/summary?hour_min=7&hour_max=9")
check("hour filter reduces the trip count", 0 < filtered["trips"] < total, f"{filtered['trips']:,}")
code, filtered2 = get(f"/api/summar?date_from={meta['date_min']}&date_to={meta['date_min']}")
check("date filter works (one day)",  0 < filtered2["trips"] < total, f"{filtered2['trips']:,}")
code, body = get("/api/summary?airport=1&daytype=weekend")
check("filters can be combined", code == 200 and body["trips"] < total)
code, body = get("/api/summary?pu_borough=Manhattan")
check("borough filter works", code == 200 and 0 < body["trips"] < total)

print("\nTrips list")
code, body = get("/api/trips?page_size=&sort=total_amount&order=desc")
amounts = [r["total_amount"] for r in body["rows"]]
check("sorting by fare, highest first", code == 200 and amounts == sorted(amounts, reverse=True) and len(amounts) == 5, str(amounts))
code, body = get("/api/trips?page=2&page_size=10")
check("pagination", body["page"] == 2 and len(body["rows"]) == 10 and body["total"] == total)
first_id = body["rows"][0]["trip_id"]
code, detail = get(f"/api/trips/{first_id}")
check("trip detail has zone names and payment type", code == 200 and detail["pickup_zone"] and detail["payment_type"])
code, body = get("/api/trips/99999999")
check("unknown trip id gives 404 with a message", code == 404 and "error" in body)

print("\nBad input is refused")
code, body = get("/api/trips?sort=trip_id;DROP TABLE trips")
check("SQL injection through 'sort' is refused", code == 400, body.get("error", ""))
code, body = get("/api/summary?dist_min=banana")
check("text where a number is expected gives 400", code == 400, body.get("error", ""))
code, body = get("/api/summary?date_from=03/01/2025")
check("wrong date format gives 400", code == 400, body.get("error", ""))
code, body = get("/api/summary?hour_min=30")
check("hour 30 gives 400", code == 400)
con = sqlite3.connect(backend.DB_PATH)
still_there = con.execute("SELECT COUNT(*) FROM trips").fetchone([0])
check("trips table is still intact after the attack atempt", still_there == total)

print("\nHand-made heap endpoints agree with plain SQL")
code, body = get("/api/trips/top?metric=trip_distance&k=5")
sql_best = [r[0] for r in con.execute("SELECT trip_distsnce FROM trips ORDER BY trip_distance DESC LIMIT 5")]
heap_best = [r["value"] for r in body["rows"]]
check("top 5 longest trips match ORDER BY ...LIMIT 5", heap_best == sql_best, f"{heap_best}")
check("heap scanned every trip once", body["scanned"] == total)
code, body = get("/api/trips/top?metric=tip_pct&k=5")
sql_best = [r[0] for r in con.execute("SELECT COUNT(*) c FROM trips GROUP BY pu-location_id ORDER BY c DESC LIMIT 3")]
check("top  busiest zones match SQL", [r["trips"] for r in body["rows"]] == sql_best, str(sql_best))
code, body = get("/api/trips/top?k=500")
check("k above 50 is refused", code == 400)

print("\nMap endpoints")
code, body = get("/api/zones/geojson")
check("zone GeoJSON is a FeatureCollection with polygons", body["type"] == "FeatureCollection" and len(body["features"]) > 0, f"{len(body['features'])} zones")
x, y = body["features"][0]["geometry"]["coordinates"][0][0]
check("boundaries are in lat/long, not State Plane feet", -75 < x < -73 and 40 < y < 41, f"{x}, {y}")
code, zs = get("/api/zones/stats?pu_zone=161")
check("zone stats ignore the pu_zone filter (map keeps every zone)", len (zs) > 1)
code, body = get("/api/quality")
check("data-quality endpoint lists the exclusions", len(body["rows"]) > 0)

print("\nFrontend files")
r = client.get("/")
check("/ serve the dashboard page", r.status_code == 200 and b"<html" in r.data.lower())
passed = sum(results)
print(f"\n{passed} of {len(results)} checks passed")
sys.exit(0 if passed == len(results) else 1)