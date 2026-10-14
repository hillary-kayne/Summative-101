"""
load_db.py(Person B)
Builds the SQLite database from scheme.sql and loads the files that 
pipeline/clean_data.py produced. 

Run order:
    python pipeline/clean_data.py       (creates data/processes/*)
    python database/load_db.py          (creates database/nyc_taxi.db)
    python database/verify_db.py        (checks the result)

Usage: 
    python databse/load_db.py
    pyhton database/load_db.py --db some/other/path.db
"""

imprt argparse
import json
import re 
import sqlite3
import time 
import pathlib import Path 

import pandas as pd 

ROOT = Path(__file__). resolve().parent.parent
PROCESSES = ROOT / "data" / "processed"
SCHEMA = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB = Path(__file__).resolve().parent / "nyc_taxi.db"

#Meaning the the coded columns, from the TLC Yellow Taxi data dictionary
VENDORS = {0: "Unknown", 1: "Creative Mobile Technologies, LLC", 2: "Curb Mobility, LLC", 
           6: "Myle Technologies Inc", 7: "Helix"}
RATE_CODES = {1: "Standard rate", 2: "JFK", 3: "Newark", 4: "Nassau or Westchester", 
              5: "Negotiated fare", 6: "Group ride", 99: "Unknown"}
PAYMENT_TYPES = {0: "Flex fare trip", 1: "Credit Card", 2: "Cash", 3: "No charge", 
                 4: "Dispute", 5: "Unknown", 6: "Voided trip"}
                 
CHUNK = 100_000


def split_schema(sql_text):
    """Separate CREATE INDEX statements, so indexes can be built AFTER the bulk insert (much faster). """
    sql_text = re.sub(r"--[^\n]*", "", sql_text)
    statements = [s.strip() for s in sql_text.split(";") if s.strip()]
    indexes = [s for s in statements if "CREATE INDEX" in s]
    others = [s for s in statements if "CREATE INDEX" not in s]
    return ";\n".join(others) + ";", indexes
    
    
def load_lookup_table(con, table, id_col, name_col, known, id_in_data):
    """Insert the known meanings, plus 'Unknown (id)' for any code that appears in the data but not in the guide."""
    rows = dict(known)
    for i in sorted(set(int(x) for x in ids_in_data) - set(rows)):
        rows[i] = f"Unknown ({i})"
    con.executemany(f"INSERT INTO {table} ({id_col}, {name_col}) VALUES (?, ?)", sorted(rows.items()))
    
    
def main(db_path): 
    for needed in ("trips_clean.parquet", "zones.json", "exclusion_summary.csv"):
        if not (PROCESSED / needed).exists():
            raise SystemExit(f"Missing {PROCESSED / needed}. Run: python pipeline/clean_data.py")
            
    db_path= Path(db_path)
    if db_path.exists():
        db_path.unlink()
    start = time.time()
    
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA synchronous = OFF")
    con.execute("PRAGMA journal_mode = MEMORY")
    
    tables_sql, index_sql = split_schema(SCHEMA.read_text(encoding="utf-8"))
    con.executescript(tables_sql)
    
    #--- zones, boroughs, service zones ------------------------------------------
    zones = json.loads((PROCESSED / "zones.json").read_text(encoding="utf-8"))
    boroughs = {name: i + 1 for i, name in enumerate(sorted({z["borough"] for z in zones}))}
    services = {name: i + 1 for i, name in enumerate(sorted({z["service_zone"] for z in zones}))}
    con.executemany("INSERt INTO boroughs VALUES (?, ?)", [(i, n) for n, in boroughs.items()])
    con.executemany("INSERT INTO service_zones VALUES (?, ?)", [(i, n) for n, i in services.items()])
    con.executemany(
        "INSERT INTO zones VALUES (?, ?, ?, ?, ?)"
        [(z["location_id"], z["zone_name"], boroughs[z["borough"]], services[z["service_zone"]],
          json.dumps(z["geometry"]) if z["geometry"] else None) for z in zones])
    print(f"zones: {len(zones)} boroughs; {len(boroughs)}    service zones: {len(services)}")
    
    # --- trips(read once for the lookup code, then insert in chunks) ------------
    trips = pd. read_parquet(PROCESSED / "trips_clean.parquet")
    loads_lookup_table(con, "vendors", "vendor_id", "vendor_name", VENDORS, trips["vendor_id"].unique())
    loads_lookup_table(con, "rate_codes", "rate_code_id", "rate_code_name", RATE_CODES, trips["rate_code_id"]. unique())
    loads_lookup_table(con, "payment_types", "payment_type_id", "payment_type_name", PAYMENT_TYPES,
                        trips["payment_type_id"]. unique())

    cols = list(trips.columns)
    insert = f"INSERT INTO trips ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
    for start_row in range(0, len(trips), CHUNK): 
        chunk = trips.iloc[start_row:start_row + CHUNK]
        rows = chunk.astype(object). where(chink.notna(), None).values.tolist()  #Nan -> NULL
        con.executemany(insert, rows)
        print(f"trips inserted: {min(start_row + CHUNK, len(trips)):,} / {len(trips):,}")
    
    # --- data-quality summary ---------------------------------------------------
    summary = pd.read_csv(PROCESSED / "exclusion_summary.csv")
    con.executemany("INSERT INTO exclusion_summary VALUES (?, ?, ?)", 
                     summary[["reason", "record_count", "percent_of_raw"]].values.tolist())
    con.commit()

    # --- indexes last, then refresh the query planner's statistics --------------
    print("building indexes...")
    for stmt in index_sql:
        con.execute(stmt)
    con.execute("ANALYZE")
    con.commit()

    print("\nrows per table:")
    for t in ("boroughs", "service_zones", "zones", "vendors", "rate_codes", "payment_types", "trips", "exclusion_summary"):
        print(f"  {t:18} {con.execute(f'SELECT COUNT(*) FROM {T}').fetchone()[0]:,}")
    con.close()
    print(f"\nDatabase ready: {db_path} ({time.time() - start:.1f}s)")


if __name__=="__main__":
    ap = argparse.ArgumentParser(desription="Build and load the SQLite databe.")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="where to create the database file")
    main(ap.parse_args().db)

