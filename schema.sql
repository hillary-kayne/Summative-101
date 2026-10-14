-- schema.sql  (Person B)
-- Normalized SQLite schema for the NYC taxi project. 
--
--  boroughs ─┐
--             ├─< zones >─┐
--   service_zones ─┘      │  (pickup zone and dropoff zone)
--                         ├─< trips >── vendors, rate_codes, payment_types
--   exclusion_summary     (stand-alone data-quality table)
--
-- Why this shape:
--   * Names(borough, zone, payment type...) live in small lookup tables, so they are stored once, 
--     not repeated millions of times in the trips table. 
--   * trips keeps the derived features (speed, tip %, hour ...) as real columns. That duplicates
--     information that could be recalculated, but it makes the dashboard queries and indexes fast. 

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS trips;
DROP TABLE IF EXISTS zones;
DROP TABLE IF EXISTS boroughs;
DROP TABLE IF EXISTS service_zones;
DROP TABLE IF EXISTS vendors;
DROP TABLE IF EXISTS rate_codes;
DROP TABLE IF EXISTS payment_types;
DROP TABLE IF EXISTS exclusion_summary;

------------------------------------------------------------------lookup tables
CREATE TABLE boroughs (
    borough_id     INTEGER PRIMARY KEY,
    borough_name   TEXT NOT NULL UNIQUE
);

CREATE TABLE service_zones (
    service_zone_id    INTEGER PRIMARY KEY,
    service_zone_name  TEXT NOT NULL UNIQUE
);

CREATE TABLE zones (
    location_id       INTEGER PRIMARY KEY,                      --TLC LocationID
    zone_name         TEXT NOT NULL,
    borough_id        INTEGER NOT NULL REFERENCES boroughs(boroughs_id)
    service_zone_id   INTEGER NOT NULL REFERENCES service_zones(service_zone_id),
    geometry_geojson  TEXT                                      --zone boundary (GeoJSON geometry, lat/long); NULL if none
);

CREATE TABLE vendors (
    vendor_id    INTEGER PRIMARY KEY,
    vendor_name  TEXT NOT NULL
);

CREATE TABLE rate_codes  (
    rate_code_id    INTEGER PRIMARY KEY,
    rate_code_name  TEXT NOT NULL
);

CREATE TABLE payment_types (
    payment_type_id    INTEGER PRIMARY KEY,
    payment_type_name  TEXT NOT NULL
);

----------------------------------------------------------------------- fact table
CREATE TABLE trips (
    trip_id                     INTEGER PRIMARY KEY,
    vendor_id                   INTEGER NOT NULL REFERENCES vendors(vendor_id),
    pickup_datetime             TEXT NOT NULL,                       -- 'YYYY-MM-DD HH:MM:SS'
    dropoff_datetime            TEXT NOT NULL,
    pickup_date                 TEXT NOT NULL,                       -- 'YYYY-MM-DD (for daily grouping)
    passenger_count             INTEGER NOT NULL CHECK (passenger count BETWEEN 1 AND 6),
    trip_distance               REAL NOT NULL CHECK (trip_distance > 0),   -- miles
    rate_code_id                INTEGER NOT NULL REFERENCES rate_codes(rate_code_id),
    store_and_fwd_flag          TEXT NOT NULL CHECK (store_and_fwd_flag IN ('Y' , 'N')),
    pu_location_id              INTEGER NOT NULL REFERENCES zones(location_id),  --pickup zone
    do_location_id              INTEGER NOT NULL REFERENCES zones(location_id),  --dropoff zone
    payment_type_id             INTEGER NOT NULL REFERENCES payment_types(payment_type_id),
    fare_amount                 REAL NOT NULL CHECK (fare_amount > 0),           -- meter fare, USD
    extra                       REAL NOT NULL DEFAULT 0,
    mta_tax                     REAL NOT NULL DEFAULT 0, 
    tip_amount                  REAL NOT NULL DEFAULT 0, CHECK (tip_amount >= 0),
    tolls_amount                REAL NOT NULL DEFAULT 0, 
    improvement_surcharge       REAL NOT NULL DEFAULT 0,
    congestion_surcharge        REAL NOT NULL DEFAULT 0,
    airport_fee                 REAL NOT NULL DEFAULT 0,
    cbd_congestion_fee          REAL NOT NULL DEFAULT 0,
    total_amount                REAL NOT NULL CHECK (total_amount > 0),           -- everything charged, USD
    -- derived features(calculated by the pipeline)
    trip_duration_min           REAL NOT NULL CHECK (trip_duration_min > 0),  --dropoff - pickup
    avg_speed_mph               REAL NOT NULL CHECK (avg_speed_mph > 0),      --distance / duration
    fare_per_mile               REAL NOT NULL,                                --fare_amount / distance
    tip_pct                     REAL,                                         --tip / fare * 100; NULL unless paid by card
    pickup_hour                 INTEGER NOT NULL CHECK (pickup_hour BETWEEN 0 AND 23),
    pickup_dow                  INTEGER NOT NULL CHECK (pickup_dow BETWEEN 0 AND 6),  -- 0 = Monday
    is_weekend                  INTEGER NOT NULL CHECK (is_weekend IN (0, 1)), 
    is_airport_trip             INTEGER NOT NULL CHECK (is_airport_trip IN (0,1)),
    is_cross_borough            INTEGER NOT NULL CHECK (is_crossed_borough IN (0,1)),
    CHECK (dropoff_datetime > pickup_datetime)
    );

------------------------------------------------------------------------------data-quality log
CREATE TABLE exclusion_summary (
    reason         TEXT PRIMARY KEY,            --why trips were removed (or repaired)
    record_count   INTEGER NOT NULL,
    percent_of_raw REAL NOT NULL
);

------------------------------------------------------------------------------indexes
-- One index for each thing the dashboard filters or groups by. 
CREATE INDEX idx_trips_pickup_dt   ON trips(pickup_datetime);
CREATE INDEX idx_trips_pickup_date ON trips(pickup_date);
CREATE INDEX idx_trips_hour        ON trips(pickup_hour);
CREATE INDEX idx_trips_pu          ON trips(pu_location_id);
CREATE INDEX idx_trips_do          ON trips(do_location_id);
CREATE INDEX idx_trips_pu_do       ON trips(pu_location_id, do_location_id);
CREATE INDEX idx_trips_distance    ON trips(trip_distance);
CREATE INDEX idx_trips_total       ON trips(total_amount);
CREATE INDEX idx_trips_payment     ON trips(payment_type_id);
CREATE INDEX idx_trips_borough     ON zones(borough_id);

