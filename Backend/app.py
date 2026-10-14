import os
import re
import sqlite3
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory

from Backend.algorithms import top_k

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.ge("TAXI_DB", ROOT / "database" / "nyc_taxi.db")).resolve()
FRONTEND = ROOT / "frontend"

app = Flask(__name__, static_folder=None)


# --------------------------------------------------------------------------
# Database access( Make it a read-only and have one connection per request)
# --------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, params=()):
    return [dict(r) for r in get_db().execute(sql, params).fetchall()]


def query_one(sql, params=()):
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None



# -----------------------------------------------------------
# Errors should come back as a JSON file
# -----------------------------------------------------------

class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


@app.errorhandler(ApiError)
def handle_api_error(err):
    return jsonify({"error": err.message}), err.status


@app.errorhandler(404)
def handle_404(_err):
    if request.path.startswith("/api/"):
        return jsonify({"error": "That endpoint does not exist."}), 404
    return "Not found", 404


@app.errorhandler(sqlite3.Error)
def handle_db_error(err):
    return jsonify({"error": f"Databse problem: {err}"}), 500


@app.after_request
def add_cors(resp):
    resp.heaers["Access-Control-Allow-Origin"] = "*"
    return resp


# --------------------------------------------------------
# Reading and validating the request parameters
# --------------------------------------------------------

def arg_number(name, cast=float, low=None, high=None):
    raw = request.args.get(name)
    if raw in (None, ""):
        return None
    try:
        value = cast(raw)
    except ValueError:
        raise ApiError(f"'{name}' must be a number, but got '{raw}'.")
    if (low is not None and value < low) or (high is not None and value > high):
        raise ApiError(f"'{name}' must be between {low} and {high}.")
    return value



def arg_date(name):
    raw = request.args.get(name)
    if raw in (None, ""):
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise ApiError(f"'{name}' must look like 2025-03-31, but got '{raw}'.")
    return raw


BOROUGH_SUBQUERY = ("{col} IN (SELECT z.location_id FROM zones z "
                    "JOIN boroughs b ON b.borough_id = z.borough_id WHERE b.borough_name = ?)")
 
def build_filters(skip=()):

  clauses, params = [], []


  def add(name, clause, value):
        if name in skip or value is None:
           return
        clauses.append(clause)
        params.append(value)
  
  
  add("date_from", "t.pickup_date >= ?", arg_date("date_from"))
  add("date_to", "t.pickup_date <= ?", arg_date("date_to"))
  add("hour_min", "t.pickup_hour >= ?", arg_number("hour_min", int, 0, 23))
  add("hour_max", "t.pickup_hour <= ?", arg_number("hour_max", int, 0, 23))
  add("dist_min", "t.trip_distance >= ?", arg_number("dist_min"))
  add("dist_max", "t.trip_distance <= ?", arg_number("dist_max"))
  add("fare_min", "t.total_amount >= ?", arg_number("fare_min"))
  add("fare_max", "t.total_amount <= ?", arg_number("fare_max"))
  add("pu_zone", "t.pu_location_id = ?", arg_number("pu_zone", int))
  add("do_zone", "t.do_location_id = ?", arg_number("do_zone", int))
  add("payment", "t.payment_type_id = ?", arg_number("payment", int))      
  if request.args.get("pu_borough"):
      add("pu_borough", BOROUGH_SUBQUERY.format(col="t.pu_location_id"), request.args["pu_borough"])
  if request.args.get("do_borough"):
      add("do_borough", BOROUGH_SUBQUERY.format(col="t.do_location_id"), request.args["do_borough"])

  daytype = request.args.get("daytype")
  if daytype in ("weekday", "weekend") and "daytype" not in skip:
      clauses.append("t.is_weekend = ?")
      params.append(1 if daytype == "weekend" else 0) 
  elif daytype not in (None, "", "weekday", "weekend"):
      raise ApiError("'daytype' must be 'weekday' or 'weekend'")
  if request.args.get("airport") == "1"and "airport" not in skip:
      clauses.append("t.is_airport_trip = 1")

  return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def arg_k(default=10):
    return arg_number("k", int, 1, 50) or default


# -------------------------------------------------------
# Meta, summary
# -------------------------------------------------------
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "trips": query_one("SELECT COUNT(*) AS n FROM trips")["n"]})


@app.route("/api/meta")
def meta():
    ranges = query_one("""SELECT COUNT(*) AS trips, MIN(pickup_date) AS date_min, MAX(pickup_date) AS date_max, MAX(trip_distance) AS distance_max, MAX(total_amount) AS fare_max FROM trips""")
    return jsonify({
        **ranges,
        "boroughs": [r["borough_name"] for r in query(
            "SELECT borough_name FROM boroughs WHERE borough_name != 'Unknown' ORDER BY borough_name")],
        "payment_types": query("SELECT payment_type_id AS id, payment_type_name AS name FROM payment_types "
                               "WHERE payment_type_id IN (SELECT DISTINCT payment_type_id FROM trips) ORDER BY id"),
        "zones": query("""SELECT z.location_id AS id, z.zone_name AS name, b.borough_name AS borough
                          FROM zones z JOIN boroughs b ON b.borough_id = z.borough_id
                          WHERE z.location_id IN (SELECT DISTINCT pu_location_id FROM trips)
                          ORDER BY z.zone_name"""), 
    })


@app.route("/api/summary")
def summary():
    where, params = build_filters()
    row = query_one(f"""SELECT COUNT(*) AS trips,
                               ROUND(AVG(t.total_amount), 2)     AS avg_total,
                               ROUND(AVG(t.trip_distance), 2)    AS avg_distance,
                               ROUND(AVG(t.trip_duration_min), 1) AS avg_duration,
                               ROUND(AVG(t.avg_speed_mph), 1)    AS avg_speed,
                               ROUND(AVG(t.tip_pct), 1)          AS avg_tip_pct,
                               ROUND(SUM(t.total_amount), 2)     AS total_revenue
                        FROM trips t {where}""", params)
    return jsonify(row)


# --------------------------------------------------------
# Trips: list, detail, top-K
# --------------------------------------------------------

SORTABLE = {"pickup_datetime", "trip_disance", "trip_duration_min", "avg_speed_mph", "fare_amount", "tip_amount", "total_amount", "tip_pct"}

@app.route("/api/trips")
def trips():
    where, params = build_filters()
    sort = request.args.get("sort", "pickup_datetime")
    if sort not in SORTABLE:
        raise ApiError(f"'sort' must be one of: {', '.join(sorted(SORTABLE))}.")
    direction = "ASC" if request.args.get("order", "desc").lower() == "asc" else "DESC"
    page = arg_number("page", int, 1) or 1
    page_size = arg_number("page_size", int, 1,100) or 25

    total = query_one(f"SELECT COUNT(*) AS n FROM trips t {where}", params)["n"]
    rows = query("""SELECT t.trip_id, t.pickup_datetime, t.dropoff_datetime,
                            pz.zone_name AS pickup_zone, dz.zone_name AS dropoff_zone,
                            t.trip_distance, t.trip_duration_min, t.avg_speed_mph,
                            t.fare_amount, t.tip_amount, t.total_amount, t.tip_pct,
                            p.payment_type_name AS payment_type
                     FROM trips t
                     JOIN zones pz ON pz.location_id = t.pu_location_id
                     JOIN zones dz ON dz.location_id = t.do_location_id
                     JOIN payment_types p ON p.payment_type_id = t.payment_type_id
                     {where}
                     ORDER BY t.{sort} {direction}, t.trip_id
                     LIMIT ? OFFSET ?""", params + [page_size, (page - 1) * page_size])

    return jsonify({"page": page, "page_size": page_size, "total": total, "pages": max(1, -(-total // page_size)), "rows": rows})

@app.route("/api/trips/<int:trip_id>")
def trip_detail(trip_id):
    row = query_one("""SELECT t.*,
                              pz.zone_name AS pickup_zone, pb.borough_name AS pickup_borough,
                              dz.zone_name AS dropoff_zone, db.borough_name AS dropoff_borough,
                              p.payment_type_name AS payment_type, r.rate_code_name AS rate_code,
                              v.vendor_name AS vendor
                       FROM trips t
                       JOIN zones pz ON pz.location_id = t.pu_location_id
                       JOIN boroughs pb ON pb.borough_id = pz.borough_id
                       JOIN zones dz ON dz.location_id = t.do_location_id
                       JOIN boroughs db ON db.borough_id = dz.borough_id
                       JOIN payment_types p ON p.payment_type_id = t.payment_type_id
                       JOIN rate_codes r ON r.rate_code_id = t.rate_code_id
                       JOIN vendors v ON v.vendor_id = t.vendor_id
                       WHERE t.trip_id = ?""", (trip_id,))
    if row is None:
        raise ApiError(f"There is no trip with id {trip_id}.", 404)
    return jsonify(row)


TOP_TRIP_METRICS = {"trip_distance", "total_amount", "trip_duration_min", "tip_pct", "avg_speed_mph", "fare_per_mile"}

@app.route("/api/trips/top")
def trips_top():
    """K best trios by ametric. It reads matching rows One at a time from the database and keeps only K of them in the hand-made heap"""

    metric = request.args.get("metric", "trip_distance")
    if metric not in TOP_TRIP_METRICS:
        raise ApiError(f"'metric' must be one of: {', '.join(sorted(TOP_TRIP_METRICS))}.")
    k =arg_k()
    where, params = build_filters()

    scanned = {"n": 0}

    def stream():
        for row in get_db().execute(f"SELECT t.trip_id, t.{metric} AS value FROM trips t {where}, params"):
            scanned["n"] +=1
            yield row


    best = top_k(stream(), k, lambda r: r["value"])
    ids = [r["trip_id"] for r in best]
    details = {}
    if ids:
        marks = ",".join("?" * len(ids))
        for r in query(f"""SELECT t.trip_id, t.pickup_datetime, pz.zone_name AS pickup_zone,
                                  dz.zone_name AS dropoff_zone, t.trip_distance, t.trip_duration_min,
                                  t.total_amount, t.tip_pct, t.avg_speed_mph, t.fare_per_mile
                           FROM trips t
                           JOIN zones pz ON pz.location_id = t.pu_location_id
                           JOIN zones dz ON dz.location_id = t.do_location_id
                           WHERE t.trip_id IN ({marks})""", ids):
            details[r["trip_id"]] = r
        return jsonify({"metric": metric, "k": k, "scanned": scanned["n"], "rows": [{**details[r["trip_id"]], "value": r["value"]} for r in best]})


# --------------------------------------------------------
# Statistics for the charts
# --------------------------------------------------------

@app.route("/api/stats/hourly")
def stats_hourly():
    where, params = build_filters()
    found = {r["hour"]: r for r in query(f"""SELECT t.pickup_hour AS hour, COUNT(*) AS trips,
                                                    ROUND(AVG(t.avg_speed_mph), 1) AS avg_speed, ROUND(AVG(t.total_amount), 2) AS avg_total 
                                                    FROM trips t {where} GROUP BY t.pickup_hour""", params)}
    return jsonify([found.get(h, {"hour": h, "trips": 0, "avg_speed": None, "avg_total": None}) for h in range(24)])


@app.route("/api/stats/weekday")
def stats_weekday():
    where, params = build_filters
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    found = {r["dow"]: r for r in query(f"""
        SELECT .pickup_dow AS dow, COUNT(*) AS trips, ROUND(AVG(t.total_amount), 2) As avg_total FROM trips t {where} GROUP BY t.pickup_dow""", params)}
    return jsonify([{"day": names[d], "trips": found.get(d, {}).get("trips", 0), "avg_total": found.get(d, {}).get("avg_total")} for d in range(7)])


@app.route("/api/stat/daily")
def stats_daily():
    where, params = build_filters()
    return jsonify(query(f"""SELECT t.pickup_date AS date, COUNT(*) AS trips FROM trips t {where} GROUP BY t.pickup_date ORDER BY t.pickup_date""", params))


DISTANCE_LABELS = ["Under 1 mi", "1 to 2", "2 to 3", "3 to 5", "5 to 10", "10 to 20", "Over 20 mi"]


@app.route("/api/stats/distance")
def stats_distance():
    where, params = build_filters()
    found = {r["bucket"]: r["trips"] for r in query(f"""
        SELECT CASE WHEN t.trip_distance < 1 THEN 0 WHEN t.trip_distance < 2 THEN 1
                    WHEN t.trip_distance < 3 THEN 2 WHEN t.trip_distance < 5 THEN 3
                    WHEN t.trip_distance < 10 THEN 4 WHEN t.trip_distance < 20 THEN 5 ELSE 6 END AS bucket,
                    COUNT(*) AS trips FROM trips t {where} GROUP BY bucket""", params)}
    return jsonify([{"band": DISTANCE_LABELS[i], "trips": found.get(i,0)} for i in range(7)])

@app.route("/api/stats/payment")
def stats_payment():
    where, params = build_filters()
    return jsonify(query(f"""SELECT p.payment_type_name AS payment_type, COUNT(*) AS trips, ROUND(AVG(t.total_amount), 2) AS avg_total
                             FROM trips t JOIN payment_types p ON p.payment_type_id = t.payment_type_id {where} GROUP BY p.payment_type_name ORDER BY trips DESC""", params))


# -----------------------------------------------------
# Zones and routes
# -----------------------------------------------------

def zone_rows():
    """Per pickup_zone numbers for the current filters. The pu_zone filter is ignored here, clicking a zone doesn't make every other zone disappear."""
    where, params = build_filters(skip=("pu_zone",))
    return query(f"""SELECT t.pu_location_id AS location_id, z.zone_name, b.borough_name AS borough,
                        COUNT(*) AS trips,
                        ROUND(AVG(t.total_amount), 2) AS avg_total,
                        ROUND(AVG(t.tip_pct), 1)      AS avg_tip_pct,
                        ROUND(AVG(t.trip_distance), 2) AS avg_distance
                    FROM trips t
                    JOIN zonesz ON z.location_id = t.pu_location_id
                    JOIN boroughs b ON b.borough_id =z.borough_id
                    {where} GROUP BY t.pu_location_id""", params)

@app.route("/api/zones/stats")
def zones_stats():
    return jsonify(zone_rows())

ZONE_METRICS = {"trips", "avg_total", "avg_tip_pct", "avg_distance"}


@app.route("/api/zones/top")
def zones_top():
    metric = request.args.get("metric", "trips")
    if metric not in ZONE_METRICS:
        raise ApiError(f"'metric' must be one of: {', '.join(sorted(ZONE_METRICS))}.")
    k = arg_k()
    # averages from a handful of trips is a lot so we need to rank by an average needs a mininimum sample
    min_trips = arg_number("min_trips", int, 1) or (1 if metric == "trips" else 20)
    rows = [r for r in zone_rows() if r["trips"] >= min_trips]
    return jsonify({"metric": metric, "k": k, "min_trips": min_trips, "rows": top_k(rows, k, lambda r: r[metric])})


@app.route("/api/flows/top")
def flows_top():
    k = arg_k()
    where, params = build_filters()
    names = {r["location_id"]: r["zone_name"] for r in query("SELECT location_id, zone_name FROM zones")}
    pairs = query(f"""SELECT t.pu_location_id AS pu, t.do_location_id AS dropoff, COUNT(*) AS trips, ROUND(AVG(t.total_amount), 2) AS avg_total FROMtrips t {where} GROUP BY t.pu_location_id, t.do_location_id""", params)
    best = top_k(pairs, k, lambda r: r["trips"])
    return jsonify ({"k": k, "routes_considered": len(pairs),
                    "rows": [{"pickup_zone": names[r["pu"]], "dropoff_zone": names[r["dropoff"]],
                              "pickup_id": r["pu"], "dropoff_id": r["dropoff"],
                              "trips": r["trips"], "avg_total": r["avg_total"]} for r in best]})


_geojson_cache = {}

@app.route("/api/zone/geojson")
def zones_geojson():
    import json
    if "fc" not in _geojson_cache:
        features = []
        for r in query("""SELECT z.location_id, z.zone_name, b.borough_name AS borough, z.geometry_geojson FROM zones z JOIN boroughs b ON b.borough_id = z.borough_id WHERE z.geometry_geojson IS NOT NULL"""):
            features.append({"type": "Feature", "properties": {"location_id": r["location_id"], "zone_name": r["zone_name"], "borough": r["borough"]}, "geometry": json.loads(r["geometry_geojson"])})
        _geojson_cache["fc"] = {"type": "FeatureCollection", "features": features}
    return jsonify(_geojson_cache["fc"])


@app.route("/api/qulity")
def quality():
    rows = query("SELECT reason, record_count, percent_of_raw FROM excusion_summary ORDER BY record_count DESC")
    return jsonify({"kept_trips": query_one("SELECT COUNT(*) AS n FROM trips")["n"], "rows": rows})

# -----------------------------------------------------------
# Dashboard files
# -----------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(FRONTEND, "index.html")


@app.route("/<path:path>")
def frontend_files(path):
    return send_from_directory(FRONTEND, path)


if __name__ == "__main__":
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found : {DB_PATH}\nBuild it first:\n"
                          " python pipeline/clean_data.py\n python database/load_db.py")
    port = int(os.environ.get("PORT", 5000))
    print(f"Database : {DB_PATH}\nDashboard: http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
    
   



    