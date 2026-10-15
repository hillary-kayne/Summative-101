# NYC Yellow Cab Trips Dashboard

A full-stack data project that cleans a sample of New York City yellow taxi trips, stores them in a SQLite database, serves them through a Flask API, and explores them in an interactive web dashboard.

The data comes from the NYC Taxi & Limousine Commission (TLC) Yellow Taxi trip records for January 2019, together with the TLC taxi zone lookup table and zone boundary shapefile.

## Team

| Member | Role | Responsibility |
|---|---|---|
| Ines Ingabire | Data pipeline | Cleaning and preparing the raw trip data |
| Hillary Kayinababo | Database | Schema design, loading and verifying the SQLite database |
| Sonia Keza Gendaneza | Backend | Flask API and the top-K algorithm |
| Elsie Glenna Ineza | Frontend | The interactive dashboard |
Team task sheet: https://docs.google.com/spreadsheets/d/16av-Zpefs4udbdqLACQPTo6-7nepp_k7o-vtTDcg5k0/edit?gid=0#gid=0

## How it works

```
Raw TLC data  ->  Pipeline  ->  data/processed/  ->  Database  ->  Backend (Flask API)  ->  Frontend dashboard
                  (clean)       (parquet, json)     (SQLite)      (JSON endpoints)         (map, charts, tables)
```

1. **Pipeline** reads the raw trips, zone lookup and zone boundaries, removes bad records, repairs harmless gaps, adds derived columns, and writes clean files to `data/processed/`.
2. **Database** builds a normalized SQLite database from those clean files and adds indexes for fast queries.
3. **Backend** exposes the database through a read-only JSON API and also serves the dashboard files.
4. **Frontend** is a browser dashboard with filters, a zone map, charts, ranked lists and a trip table.

## Project structure

```
Summative-101/
├── Backend/
│   ├── app.py                  Flask API and dashboard server
│   ├── algorithms.py           Hand-built min-heap and top-K function
│   └── test_api.py             Automated API checks
├── Database/
│   ├── schema.sql              Table definitions, constraints and indexes
│   ├── insight_report.py       Helps in finding the insights
│   ├── load_db.py              Builds nyc_taxi.db from data/processed/
│   ├── verify_db.py            Health checks for the database
│   └── insight_queries.sql     SQL queries behind the data insights
├── data/
│   ├── raw/                    Zone lookup table and zone boundary shapefile
│   └── processed/              Cleaned trips, zones, and exclusion logs
├── frontend/
│   ├── index.html              Dashboard page
│   ├── css/style.css           Styling
│   └── js/                     main, api, map, charts, table, lists, drawer, format, dom
├── pipeline/
│   └── clean_data.py           Data cleaning and feature engineering
├── tools/
│   ├── make_sample_data.py     Generates sample trip data for testing
│   └── real_rows_sample.csv    Small sample of real TLC rows
├── requirements.txt
└── README.md
```

## Getting started

### Requirements

- Python 3.10 or newer
- Git
- A modern web browser

### 1. Clone the repository

```
git clone https://github.com/hillary-kayne/Summative-101.git
cd Summative-101
```

### 2. Install the dependencies

```
python -m venv .venv             # for setting up the environment
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

This installs Flask, pandas, pyarrow, pyshp and pyproj.

### 3. Build the database

```
python Database/load_db.py
```

This creates `Database/nyc_taxi.db` from the cleaned files in `data/processed/`. The database file is listed in `.gitignore`, so every team member builds their own copy. You must do this step before starting the app.

### 4. Check that everything is healthy (optional)

```
python Database/verify_db.py
python Backend/test_api.py
```

Both scripts print PASS or FAIL for each check.

### 5. Start the app

```
python Backend/app.py
```

Open **http://127.0.0.1:5000** in your browser. The Flask server serves the dashboard, so the frontend does not need to be started separately. Press `Ctrl+C` in the terminal to stop the server.

## Re-running the data pipeline (optional)

The cleaned data is already included in `data/processed/`, so you do not need this step to run the project. To regenerate it from a raw trips file:

```
python pipeline/clean_data.py --trips path/to/yellow_tripdata.csv
```

Optional arguments:

| Argument | Purpose |
|---|---|
| `--trips` | Path to the raw yellow taxi trips file (`.parquet` or `.csv`) |
| `--lookup` | Path to `taxi_zone_lookup.csv` |
| `--zones` | Path to the zone boundaries (`taxi_zones.zip` shapefile or a `.geojson`) |
| `--sample N` | Use only N random trips, for quick testing |

After regenerating the data, run `python Database/load_db.py` again to rebuild the database.

## Data cleaning

The pipeline keeps a log of every record it removes so the cleaning is transparent. From a raw sample of 200,000 trips, about 2,900 were excluded (roughly 1.5%) for these reasons:

| Reason | Trips removed |
|---|---|
| Trip shorter than 1 minute | 1,774 |
| Trip longer than 6 hours | 504 |
| Distance zero or negative | 308 |
| Drop-off not after pickup | 166 |
| Fare zero or negative | 153 |
| Pickup outside the main month | 17 |
| Impossible speed (over 80 mph) | 7 |
| Distance over 100 miles | 1 |
| Negative fee component | 1 |

A further 2,928 trips had a missing passenger count. These were repaired by setting it to 1 instead of being discarded.

The cleaning thresholds are defined in one place (`LIMITS` in `pipeline/clean_data.py`) so they are easy to review and change.

**Derived columns** added to each trip: trip duration, average speed, fare per mile, tip percentage, pickup hour, day of week, weekend flag, airport trip flag, and cross-borough flag.

**Output files** in `data/processed/`:

- `trips_clean.parquet`: the cleaned trips
- `zones.json`: zones with borough, service zone and map boundaries
- `excluded_trips.csv`: every removed trip and the reason
- `exclusion_summary.csv`: the counts shown above

## Database design

The SQLite database is normalized into a central `trips` table and several lookup tables:

| Table | Contents |
|---|---|
| `trips` | One row per cleaned trip, including the derived columns |
| `zones` | Taxi zones with their map boundaries |
| `boroughs` | Borough names |
| `service_zones` | TLC service zone names |
| `vendors` | Taxi technology vendors |
| `rate_codes` | Fare rate types (standard, JFK, Newark, and so on) |
| `payment_types` | Payment methods |
| `exclusion_summary` | Data quality summary from the pipeline |

Foreign keys link trips to zones, vendors, rate codes and payment types. Indexes are created after the bulk insert, which makes loading much faster. `verify_db.py` checks that every table has data, that integrity and foreign key checks are clean, that the main dashboard queries use indexes, and that the constraints reject bad data.

`Database/insight_queries.sql` contains the SQL used to find insights such as rush-hour speeds, airport trip behavior, the busiest routes, tipping by borough, and weekday versus weekend demand.

## Backend API

All endpoints return JSON, and errors are also returned as JSON with a clear message. The database is opened read-only, and all filter values are passed as SQL parameters, never pasted into the query text, which prevents SQL injection.

### Filters

Most endpoints accept these URL parameters, and they can be combined:

| Parameter | Meaning |
|---|---|
| `date_from`, `date_to` | Pickup date range, formatted like `2019-01-15` |
| `hour_min`, `hour_max` | Pickup hour, 0 to 23 |
| `dist_min`, `dist_max` | Trip distance in miles |
| `fare_min`, `fare_max` | Total charged, in USD |
| `pu_borough`, `do_borough` | Pickup or drop-off borough name |
| `pu_zone`, `do_zone` | Pickup or drop-off zone ID |
| `payment` | Payment type ID |
| `daytype` | `weekday` or `weekend` |
| `airport` | `1` for airport trips only |

### Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/health` | Confirms the API is running and returns the trip count |
| `GET /api/meta` | Boroughs, zones, payment types, and the date, distance and fare ranges |
| `GET /api/summary` | Headline numbers: trips, average fare, distance, duration, speed, tip, revenue |
| `GET /api/trips` | Paginated trip list (`sort`, `order`, `page`, `page_size`) |
| `GET /api/trips/<id>` | Full details of a single trip |
| `GET /api/trips/top` | Top K trips by a metric (`metric`, `k`) |
| `GET /api/stats/hourly` | Trips, average speed and fare by hour |
| `GET /api/stats/weekday` | Trips and average fare by day of the week |
| `GET /api/stats/daily` | Trips per day |
| `GET /api/stats/distance` | Trips by distance band |
| `GET /api/stats/payment` | Trips by payment type |
| `GET /api/zones/stats` | Per-zone numbers used to colour the map |
| `GET /api/zones/top` | Top K pickup zones by a metric |
| `GET /api/flows/top` | Busiest pickup-to-drop-off routes |
| `GET /api/zones/geojson` | Zone boundaries for the map |
| `GET /api/quality` | What the cleaning step removed |

Example:

```
http://127.0.0.1:5000/api/trips/top?metric=total_amount&k=5&daytype=weekend
```

### Custom top-K algorithm

Instead of sorting every matching trip, the "top K" endpoints use a hand-built binary min-heap (`Backend/algorithms.py`). The heap holds only the K best items seen so far. Each new item is compared against the smallest item in the heap and replaces it only if it ranks higher.

- Time: O(n log K), compared with O(n log n) for a full sort
- Memory: O(K), because the database rows are streamed one at a time
- Ties are broken by arrival order, and missing values are skipped

Running `python Backend/algorithms.py` runs a self-test (300 random trials in both directions, including ties and missing values) and a timing comparison against a full sort.

## Frontend dashboard

The dashboard is built with plain HTML, CSS and JavaScript, with Chart.js included locally in `frontend/js/vendor/`, so it needs no build step or internet connection.

Features:

- **Summary cards** for trips, average fare, average distance, average ride time and average card tip
- **Filter panel** covering all the API filters, with a button to clear them
- **Zone map** that colours each pickup zone by the chosen metric, with tooltips and click-to-filter
- **Charts** for trips by hour (with average speed), trips per day, trips by day of the week, trips by distance band, and trips by payment type
- **Ranked lists** for the top pickup zones, busiest routes and standout trips
- **Trip table** with sorting, paging and a page size selector
- **Detail drawer** that opens full information about a single trip
- **Data quality section** showing what the cleaning step removed
- Clear error and empty-state messages when the server is unreachable or no trips match the filters

## Troubleshooting

| Problem | Fix |
|---|---|
| `Database not found` when starting the app | Run `python Database/load_db.py` first |
| `ImportError` mentioning `pyarrow` | Run `python -m pip install -r requirements.txt` |
| `Cannot replace nyc_taxi.db` | Close any program that has the database open (including its tab in VS Code), then run the loader again |
| Port 5000 is already in use | Start on another port. In PowerShell: `$env:PORT=5001; python Backend/app.py` |
| Dashboard shows an error banner | Make sure the server is running and the database has been built |

# Demo video: https://youtu.be/ElIgVyGplSk


## Data sources

- NYC Taxi & Limousine Commission, Yellow Taxi Trip Records: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page
- NYC TLC Taxi Zone Lookup Table and Taxi Zone shapefile, from the same page
