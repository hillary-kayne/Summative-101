import argparse
import sqlite3
import sys 
from pathlib import Path 

DEFAULT_DB =Path(__file__).resolve().parent / "nyc_taxi.db"
results = []


def check(name, ok, detail=""):
    ok = bool(ok)
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))

def main(db_path):
    if not Path(db_path). exists():
        raise SystemExit(f"{db_path} not found. Run: python database/load_db.py")
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    
    print("1. Tables contain data")
    for t in ("boroughs", "service_zones", "zones", "vendors", "rate_codes", "payment_types", "trips", "exclusion_summary"):
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        check(f"{t} has rows", n > 0, f"{n:,} rows")
    
    print("\n2.Intergrity")
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    check("no foreign-key violations", len(fk) == 0, f"{len(fk)} violations")
    check("SQLite integrity_check is ok", con.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
    bad = con.execute("""SELECT COUNT(*)FROM trips
                         WHERE dropoff_datetime<= pickup_datetime OR trip_distance <= 0
                            OR fare_amount <= 0 OR total_amount <= 0""").fetchone()[0]
    check("no impossible trips slipped through", bad == 0, f"{bad} found")
    orphans = con.execute("""SELECT COUNT(*) FROM trips
                             LEFT JOIN zones z ON z.location_id = t.pu_location_id
                             WHERE z.location_id IS NULL""").fetchone()[0]
    check("every pickup zone exists in zones", orphans == 0)

    print("\n3. Queries use indexes")
    plans = {
        "filter by date range": "SELECT * FROM trips WHERE pickup_date BETWEEN '2025-03-01' AND '2025-03-07'",
        "filter by pickup zone": "SELECT * FROM trips WHERE pu_location_id = 161",
        "filter by distance": "SELECT * FROM trips WHERE pickup_hour = 8", 
        "filter by hour": "SELECT * FROM trips WHERE pickup_hour = 8", 
        "route (pickup + dropoff)": "SELECT * FROM trips WHERE pu_location_id = 161 AND do_location_id = 230",
        "filter by payment type": "SELECT * FROM trips WHERE payment_type_id = 1", 
    }  
    for label, sql in plans.items(): 
        plan = " ".join(r["detail"] for r in con.execute("EXPLAIN QUERY PLAN "+sql))
        check(label, "USING" in plan and "INDEX" in plan, plan)

    print("\n4. Constraints reject bad data")
    base = dict(con.execute("SELECT * from trips LIMIT 1").fetchone())
    new_id = con.execute("SELECT MAX(trip_id) + 1 FROM trips").fetchone()[0]
    cases = {
        "negative fare is rejected": {"fare_amount": -5},
        "zero distance is rejected": {"trip_distance": 0},
        "dropoff before pickup is rejected": {"dropoff_datetime": "2000-01-01 00:00:00"},
        "pickup hour 25 is rejected": {"pickup_hour": 25},
        "unkwown zone id is rejected (foreign key)": {"pu_location_id": 99999}, 
        "unknown payment type is rejected (foreign key)": {"payment_type_id":99999},
    } 
    for label, change in cases.items():
        row = {**base, "trip_id": new_id, **change}
        cols = ", ".join(row)
        marks = ", ".join(f":{k}" for k in row)
        try: 
            con.execute(f"INSERT INTO trips ({cols}) VALUES ({marks})", row)
            check(label, False, "the bad row was ACCEPTED")
        except sqlite3.IntegrityError as e:
            check(label, True, str(e))
        finally: 
            con.rollback()

    con.close()
    passed = sum(results)
    print(f"\\n{passed} of {len(results)} checks passed")
    sys.exit(0 if passed ==len(results) else 1)


if __name__ =="__main__":
    ap = argparse.ArgumentParser()
    ap. add_argument("--db", default=str(DEFAULT_DB))
    main(ap.parse_args().db)
    
