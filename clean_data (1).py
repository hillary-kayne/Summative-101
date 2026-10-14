import argparse
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
LIMITS = {
    "min_duration_min": 1,     
    "max_duration_min": 360,  
    "max_distance_mi": 100,   
    "max_fare": 500,          
    "max_speed_mph": 80,       
    "max_passengers": 6,       
}

RENAME = {
    "vendorid": "vendor_id",
    "tpep_pickup_datetime": "pickup_datetime",
    "tpep_dropoff_datetime": "dropoff_datetime",
    "passenger_count": "passenger_count",
    "trip_distance": "trip_distance",
    "ratecodeid": "rate_code_id",
    "store_and_fwd_flag": "store_and_fwd_flag",
    "pulocationid": "pu_location_id",
    "dolocationid": "do_location_id",
    "payment_type": "payment_type_id",
    "fare_amount": "fare_amount",
    "extra": "extra",
    "mta_tax": "mta_tax",
    "tip_amount": "tip_amount",
    "tolls_amount": "tolls_amount",
    "improvement_surcharge": "improvement_surcharge",
    "total_amount": "total_amount",
    "congestion_surcharge": "congestion_surcharge",
    "airport_fee": "airport_fee",
    "cbd_congestion_fee": "cbd_congestion_fee",
}
CRITICAL = ["pickup_datetime", "dropoff_datetime", "pu_location_id", "do_location_id",
            "trip_distance", "fare_amount", "total_amount"]
FEES = ["extra", "mta_tax", "tip_amount", "tolls_amount", "improvement_surcharge",
        "congestion_surcharge", "airport_fee", "cbd_congestion_fee"]
DUP_KEYS = ["vendor_id", "pickup_datetime", "dropoff_datetime", "pu_location_id",
            "do_location_id", "trip_distance", "total_amount"]

FINAL_COLUMNS = [
    "trip_id", "vendor_id", "pickup_datetime", "dropoff_datetime", "pickup_date",
    "passenger_count", "trip_distance", "rate_code_id", "store_and_fwd_flag",
    "pu_location_id", "do_location_id", "payment_type_id",
    "fare_amount", "extra", "mta_tax", "tip_amount", "tolls_amount",
    "improvement_surcharge", "congestion_surcharge", "airport_fee", "cbd_congestion_fee",
    "total_amount",
    # derived features
    "trip_duration_min", "avg_speed_mph", "fare_per_mile", "tip_pct",
    "pickup_hour", "pickup_dow", "is_weekend", "is_airport_trip", "is_cross_borough",
]

def tidy_text(value):
    """Turn blanks and 'N/A' style placeholders into the single word 'Unknown'."""
    text = str(value).strip()
    return "Unknown" if text in ("", "N/A", "NA", "nan", "None") else text


def load_lookup(path):
    # keep_default_na=False so the literal text "N/A" is not silently turned into NaN
    df = pd.read_csv(path, keep_default_na=False)
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns={"locationid": "location_id", "zone": "zone_name"})
    df["location_id"] = df["location_id"].astype(int)
    for col in ("borough", "zone_name", "service_zone"):
        df[col] = df[col].map(tidy_text)
    return df.drop_duplicates(subset="location_id").reset_index(drop=True)
def _first_coord(coords):
    while isinstance(coords[0], (list, tuple)):
        coords = coords[0]
    return coords


THIN_TOLERANCE = 0.0002 


def _thin_ring(points):
    """Drop points that sit almost on top of the previous one, so the map file stays small."""
    kept = [points[0]]
    for pt in points[1:-1]:
        if abs(pt[0] - kept[-1][0]) >= THIN_TOLERANCE or abs(pt[1] - kept[-1][1]) >= THIN_TOLERANCE:
            kept.append(pt)
    kept.append(points[-1])
    return kept if len(kept) >= 4 else points 


def _convert_geometry(geom, fn):
    def ring(r):
        pts = []
        for coord in r:
            x, y = fn(coord[0], coord[1])
            pts.append([round(x, 5), round(y, 5)])
        return _thin_ring(pts)

    if geom["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": [ring(r) for r in geom["coordinates"]]}
    return {"type": "MultiPolygon", "coordinates": [[ring(r) for r in poly] for poly in geom["coordinates"]]}


def _read_shapefile(path):
    """Read the TLC shapefile (a .zip holding .shp/.shx/.dbf/.prj, or a bare .shp). Returns (features, crs_text)."""
    import shapefile                                   # the 'pyshp' package
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            def member(ext):
                found = [n for n in z.namelist() if n.lower().endswith(ext)]
                return io.BytesIO(z.read(found[0])) if found else None
            reader = shapefile.Reader(shp=member(".shp"), shx=member(".shx"), dbf=member(".dbf"))
            prj = member(".prj")
            crs_text = prj.read().decode("utf-8", "ignore") if prj else None
    else:
        reader = shapefile.Reader(str(path))
        prj_path = path.with_suffix(".prj")
        crs_text = prj_path.read_text(encoding="utf-8", errors="ignore") if prj_path.exists() else None
    features = [{"properties": sr.record.as_dict(), "geometry": sr.shape.__geo_interface__}
                for sr in reader.shapeRecords()]
    return features, crs_text


def _read_geojson(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    crs_name = (data.get("crs") or {}).get("properties", {}).get("name")
    return data["features"], crs_name


def load_geometries(path):
    """
    Returns {location_id: geometry} with every geometry in lat/long (WGS84), because browsers
    and web maps expect lat/long.
    The official TLC boundaries are a shapefile in NY State Plane feet (EPSG:2263). This reads the
    projection from the file, converts to lat/long, and thins out needless points. Zones that appear
    in several pieces (the TLC file has a few) are merged into one MultiPolygon.
    """
    path = Path(path)
    if path.suffix.lower() in (".zip", ".shp"):
        features, crs_text = _read_shapefile(path)
    else:
        features, crs_text = _read_geojson(path)

    sample = next(f["geometry"]["coordinates"] for f in features if f.get("geometry"))
    x, y = _first_coord(sample)[:2]
    convert = lambda px, py: (px, py)
    if abs(x) > 180 or abs(y) > 90:
        from pyproj import CRS, Transformer
        source = CRS.from_epsg(2263)                  
        if crs_text:
            try:
                source = CRS.from_user_input(crs_text)
            except Exception:
                pass
        convert = Transformer.from_crs(source, "EPSG:4326", always_xy=True).transform
        print(f"  zone boundaries are projected ({source.name}); converting to lat/long")

    geoms = {}
    for f in features:
        if not f.get("geometry"):
            continue
        props = {k.lower(): v for k, v in f["properties"].items()}
        loc_id = int(props.get("locationid", props.get("location_id")))
        g = _convert_geometry(f["geometry"], convert)
        if loc_id not in geoms:
            geoms[loc_id] = g
            continue
        old = geoms[loc_id]
        polys = old["coordinates"] if old["type"] == "MultiPolygon" else [old["coordinates"]]
        new = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        geoms[loc_id] = {"type": "MultiPolygon", "coordinates": polys + new}
    return geoms


def build_zones(lookup, geoms):
    zones = []
    for r in lookup.itertuples():
        zones.append({
            "location_id": int(r.location_id),
            "zone_name": r.zone_name,
            "borough": r.borough,
            "service_zone": r.service_zone,
            "geometry": geoms.get(int(r.location_id)),
        })
    missing = [z["location_id"] for z in zones if z["geometry"] is None and z["location_id"] not in (264, 265)]
    extra = sorted(set(geoms) - set(lookup["location_id"]))
    if missing:
        print(f"  note: zones with no boundary polygon (they just won't be drawn): {missing}")
    if extra:
        print(f"  note: polygons with no lookup row (ignored): {extra}")
    return zones

def read_raw_trips(path):
    """Read only the columns we need, so a multi-million-row month fits in memory. Accepts .parquet or .csv."""
    path = Path(path)
    wanted = set(RENAME)
    if path.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq
        names = pq.ParquetFile(path).schema_arrow.names
        return pd.read_parquet(path, columns=[n for n in names if n.strip().lower() in wanted])
    if path.suffix.lower() in (".csv", ".gz"):
        header = pd.read_csv(path, nrows=0).columns
        return pd.read_csv(path, usecols=[c for c in header if c.strip().lower() in wanted])
    raise SystemExit(f"Unsupported trips file type: {path.name} (use .parquet or .csv)")


def load_trips(path, sample):
    df = read_raw_trips(path)
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns=RENAME)
    missing = [c for c in CRITICAL if c not in df.columns]
    if missing:
        raise SystemExit(f"The trips file is missing required columns: {missing}\nFound: {list(df.columns)}")
    if sample and sample < len(df):
        df = df.sample(n=sample, random_state=42)   # random, so every day of the month is represented
    df["raw_row"] = df.index
    for col in ("vendor_id", "passenger_count", "rate_code_id", "store_and_fwd_flag", "payment_type_id", *FEES):
        if col not in df.columns:
            df[col] = np.nan      # files from other years lack some columns (e.g. airport_fee before 2021)
    keep = ["raw_row", "vendor_id", "pickup_datetime", "dropoff_datetime", "passenger_count",
            "trip_distance", "rate_code_id", "store_and_fwd_flag", "pu_location_id", "do_location_id",
            "payment_type_id", "fare_amount", *FEES, "total_amount"]
    return df[keep].reset_index(drop=True)


def clean_trips(df, lookup):
    n_raw = len(df)

    df["pickup_datetime"] = pd.to_datetime(df["pickup_datetime"], errors="coerce")
    df["dropoff_datetime"] = pd.to_datetime(df["dropoff_datetime"], errors="coerce")
    numeric = ["vendor_id", "passenger_count", "trip_distance", "rate_code_id", "pu_location_id",
               "do_location_id", "payment_type_id", "fare_amount", "total_amount", *FEES]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    duration = (df["dropoff_datetime"] - df["pickup_datetime"]).dt.total_seconds() / 60
    with np.errstate(divide="ignore", invalid="ignore"):
        speed = df["trip_distance"] / (duration / 60)

    reason = pd.Series("", index=df.index, dtype=object)

    def flag(mask, why):
        mask = mask & (reason == "")
        reason[mask] = why

    flag(df[CRITICAL].isna().any(axis=1), "missing_critical_value")

    month = df["pickup_datetime"].dt.to_period("M")
    main_month = month.mode().iloc[0]
    print(f"  main month in the file: {main_month}")
    flag(month != main_month, "pickup_outside_main_month")

    flag(duration <= 0, "dropoff_not_after_pickup")
    flag(duration < LIMITS["min_duration_min"], "duration_under_1_min")
    flag(duration > LIMITS["max_duration_min"], "duration_over_6_hours")
    flag(df["trip_distance"] <= 0, "distance_zero_or_negative")
    flag(df["trip_distance"] > LIMITS["max_distance_mi"], "distance_over_100_miles")
    flag(df["fare_amount"] <= 0, "fare_zero_or_negative")
    flag(df["fare_amount"] > LIMITS["max_fare"], "fare_over_500")
    flag(df["total_amount"] <= 0, "total_zero_or_negative")
    flag((df[FEES].fillna(0) < 0).any(axis=1), "negative_fee_component")
    known_zones = set(lookup["location_id"])
    flag(~df["pu_location_id"].isin(known_zones) | ~df["do_location_id"].isin(known_zones), "unknown_zone_id")
    flag(speed > LIMITS["max_speed_mph"], "impossible_speed")

    ok = reason == ""
    dup = df[ok].duplicated(subset=DUP_KEYS, keep="first")
    flag(df.index.isin(dup[dup].index), "duplicate_trip")

    removed = df[reason != ""].copy()
    removed["reason"] = reason[reason != ""]
    for col in ("pickup_datetime", "dropoff_datetime"):
        removed[col] = removed[col].dt.strftime("%Y-%m-%d %H:%M:%S")
    log_cols = ["raw_row", "reason", "pickup_datetime", "dropoff_datetime", "pu_location_id",
                "do_location_id", "trip_distance", "fare_amount", "total_amount"]
    excluded_log = removed[log_cols]

    summary = (excluded_log["reason"].value_counts().rename_axis("reason")
               .reset_index(name="record_count"))

    kept = df[reason == ""].copy()
    repairs = {}

    def repair(mask, col, value, label):
        if int(mask.sum()):
            repairs[label] = int(mask.sum())
        kept.loc[mask, col] = value

    pc = kept["passenger_count"]
    repair(pc.isna() | (pc < 1) | (pc > LIMITS["max_passengers"]), "passenger_count", 1,
           "repaired_passenger_count_set_to_1")
    repair(kept["rate_code_id"].isna(), "rate_code_id", 99, "repaired_rate_code_set_to_99_unknown")
    repair(kept["payment_type_id"].isna(), "payment_type_id", 5, "repaired_payment_type_set_to_5_unknown")
    repair(kept["vendor_id"].isna(), "vendor_id", 0, "repaired_vendor_set_to_0_unknown")
    flagv = kept["store_and_fwd_flag"].astype(str).str.upper().str[:1]
    kept["store_and_fwd_flag"] = np.where(flagv == "Y", "Y", "N")
    kept[FEES] = kept[FEES].fillna(0)

    kept["trip_duration_min"] = (kept["dropoff_datetime"] - kept["pickup_datetime"]).dt.total_seconds() / 60    
    kept["avg_speed_mph"] = kept["trip_distance"] / (kept["trip_duration_min"] / 60)
    kept["fare_per_mile"] = kept["fare_amount"] / kept["trip_distance"]
    card = kept["payment_type_id"] == 1
    kept["tip_pct"] = np.where(card, kept["tip_amount"] / kept["fare_amount"] * 100, np.nan)
    kept["pickup_hour"] = kept["pickup_datetime"].dt.hour
    kept["pickup_dow"] = kept["pickup_datetime"].dt.dayofweek          # 0 = Monday ... 6 = Sunday
    kept["is_weekend"] = (kept["pickup_dow"] >= 5).astype(int)

    svc = lookup.set_index("location_id")["service_zone"]
    bor = lookup.set_index("location_id")["borough"]
    is_air = kept["pu_location_id"].map(svc).isin(["Airports", "EWR"]) | kept["do_location_id"].map(svc).isin(["Airports", "EWR"])
    kept["is_airport_trip"] = is_air.astype(int)
   
    kept["is_cross_borough"] = (kept["pu_location_id"].map(bor) != kept["do_location_id"].map(bor)).astype(int)

 
    kept = kept.sort_values("pickup_datetime").reset_index(drop=True)
    kept["trip_id"] = np.arange(1, len(kept) + 1)
    kept["pickup_date"] = kept["pickup_datetime"].dt.strftime("%Y-%m-%d")
    kept["pickup_datetime"] = kept["pickup_datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
    kept["dropoff_datetime"] = kept["dropoff_datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
    for col in ("vendor_id", "passenger_count", "rate_code_id", "pu_location_id", "do_location_id",
                "payment_type_id", "pickup_hour", "pickup_dow"):
        kept[col] = kept[col].astype(int)
    for col in ("trip_distance", "fare_amount", "total_amount", *FEES,
                "trip_duration_min", "avg_speed_mph", "fare_per_mile", "tip_pct"):
        kept[col] = kept[col].round(2)
    kept = kept[FINAL_COLUMNS]
    rep = pd.DataFrame({"reason": list(repairs), "record_count": list(repairs.values())})
    summary = pd.concat([summary, rep], ignore_index=True)
    summary["record_count"] = summary["record_count"].astype(int)
    summary["percent_of_raw"] = (summary["record_count"] / n_raw * 100).round(3)
    return kept, excluded_log, summary

def find_one(patterns, label):
    for pattern in patterns:
        matches = sorted(RAW.glob(pattern))
        if matches:
            return matches[0]
    raise SystemExit(f"Could not find {label} in {RAW} (looked for {', '.join(patterns)}). "
                     f"Put the file there, or point to it with the matching --option.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Clean the NYC taxi data.")
    ap.add_argument("--trips", help="path to the yellow_tripdata .parquet (or .csv) file")
    ap.add_argument("--lookup", help="path to taxi_zone_lookup.csv")
    ap.add_argument("--zones", help="path to taxi_zones.zip (shapefile) or a zones .geojson")
    ap.add_argument("--sample", type=int, default=0, help="only use this many random trips (for fast testing)")
    args = ap.parse_args()

    trips_path = Path(args.trips) if args.trips else find_one(["yellow_tripdata*.parquet", "yellow_tripdata*.csv"], "the trips file")
    lookup_path = Path(args.lookup) if args.lookup else find_one(["taxi_zone_lookup*.csv"], "the zone lookup CSV")
    zones_path = Path(args.zones) if args.zones else find_one(["taxi_zones*.zip", "taxi_zones*.shp", "taxi_zones*.geojson"], "the taxi zones file")
    OUT.mkdir(parents=True, exist_ok=True)

    print(f"Trips : {trips_path.name}\nLookup: {lookup_path.name}\nZones : {zones_path.name}")

    print("\n[1/3] Zones")
    lookup = load_lookup(lookup_path)
    zones = build_zones(lookup, load_geometries(zones_path))
    (OUT / "zones.json").write_text(json.dumps(zones), encoding="utf-8")
    print(f"  {len(zones)} zones written")

    print("\n[2/3] Trips")
    raw = load_trips(trips_path, args.sample)
    print(f"  {len(raw):,} raw trips loaded")
    clean, excluded, summary = clean_trips(raw, lookup)

    print("\n[3/3] Writing files")
    clean.to_parquet(OUT / "trips_clean.parquet", index=False)
    excluded.to_csv(OUT / "excluded_trips.csv", index=False)
    summary.to_csv(OUT / "exclusion_summary.csv", index=False)

    print(f"\n  kept     : {len(clean):,}")
    print(f"  excluded : {len(excluded):,}  ({len(excluded) / len(raw) * 100:.2f}% of raw)")
    print("\nWhy trips were excluded / repaired:")
    print(summary.to_string(index=False))
    print(f"\nFiles saved in {OUT}")
