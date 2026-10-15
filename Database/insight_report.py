"""
insight_report.py  (Person B)
Prints the numbers behind the three insights in the report, straight from the database.
Run it after load_db.py, then copy everything it prints.

    python database/insight_report.py

Everything here is read-only. The same numbers are in the dashboard, and the underlying SQL is
in database/insight_queries.sql.
"""

import argparse
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / "nyc_taxi.db"


def heading(text):
    print("\n" + "=" * 70 + f"\n{text}\n" + "=" * 70)


def main(db_path):
    if not Path(db_path).exists():
        raise SystemExit(f"{db_path} not found. Run: python database/load_db.py")
    con = sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)
    q = lambda sql, p=(): con.execute(sql, p).fetchall()
    total = q("SELECT COUNT(*) FROM trips")[0][0]
    d0, d1 = q("SELECT MIN(pickup_date), MAX(pickup_date) FROM trips")[0]
    print(f"Trips in the database: {total:,}   Dates: {d0} to {d1}")

    # ------------------------------------------------------------------ insight 1
    heading("INSIGHT 1: trips and average speed by hour of day")
    hours = q("""SELECT pickup_hour, COUNT(*), ROUND(AVG(avg_speed_mph), 1), ROUND(AVG(total_amount), 2)
                 FROM trips GROUP BY pickup_hour ORDER BY pickup_hour""")
    print(f"{'hour':>5} {'trips':>9} {'share':>7} {'avg mph':>8} {'avg $':>8}")
    for h, n, sp, fare in hours:
        print(f"{h:>5} {n:>9,} {100 * n / total:>6.1f}% {sp:>8} {fare:>8}")
    busiest = max(hours, key=lambda r: r[1])
    slowest = min(hours, key=lambda r: r[2])
    fastest = max(hours, key=lambda r: r[2])
    quietest = min(hours, key=lambda r: r[1])
    print(f"\nBusiest hour : {busiest[0]}:00  ({busiest[1]:,} trips, {busiest[2]} mph)")
    print(f"Quietest hour: {quietest[0]}:00  ({quietest[1]:,} trips, {quietest[2]} mph)")
    print(f"Slowest hour : {slowest[0]}:00  ({slowest[2]} mph)")
    print(f"Fastest hour : {fastest[0]}:00  ({fastest[2]} mph)")
    rush = q("""SELECT ROUND(AVG(avg_speed_mph), 1), COUNT(*) FROM trips
                WHERE pickup_hour IN (7,8,9,16,17,18,19) AND is_weekend = 0""")[0]
    night = q("""SELECT ROUND(AVG(avg_speed_mph), 1), COUNT(*) FROM trips
                 WHERE pickup_hour IN (0,1,2,3,4,5)""")[0]
    print(f"Weekday rush hours (7-9am, 4-7pm): {rush[0]} mph over {rush[1]:,} trips")
    print(f"Night (midnight-6am)             : {night[0]} mph over {night[1]:,} trips")

    # ------------------------------------------------------------------ insight 2
    heading("INSIGHT 2: airport trips versus all other trips")
    rev_total = q("SELECT SUM(total_amount) FROM trips")[0][0]
    print(f"{'kind':<14} {'trips':>9} {'% trips':>8} {'avg mi':>7} {'avg min':>8} {'avg $':>8} {'% revenue':>10}")
    for flag, label in ((1, "Airport"), (0, "Other")):
        n, mi, mins, fare, rev = q("""SELECT COUNT(*), AVG(trip_distance), AVG(trip_duration_min),
                                             AVG(total_amount), SUM(total_amount)
                                      FROM trips WHERE is_airport_trip = ?""", (flag,))[0]
        print(f"{label:<14} {n:>9,} {100 * n / total:>7.1f}% {mi:>7.1f} {mins:>8.1f} {fare:>8.2f} {100 * rev / rev_total:>9.1f}%")
    tips = q("""SELECT is_airport_trip, ROUND(AVG(tip_pct), 1) FROM trips
                WHERE tip_pct IS NOT NULL GROUP BY is_airport_trip""")
    print("Average tip % (card payments only):", {("Airport" if k else "Other"): v for k, v in tips})
    air_zones = q("""SELECT z.zone_name, COUNT(*) FROM trips t JOIN zones z ON z.location_id = t.pu_location_id
                     WHERE t.is_airport_trip = 1 GROUP BY z.zone_name ORDER BY 2 DESC LIMIT 3""")
    print("Top airport pickup zones:", [(n, f"{c:,}") for n, c in air_zones])

    # ------------------------------------------------------------------ insight 3
    heading("INSIGHT 3: where trips start and where they go")
    zones = q("""SELECT z.zone_name, b.borough_name, COUNT(*) FROM trips t
                 JOIN zones z ON z.location_id = t.pu_location_id
                 JOIN boroughs b ON b.borough_id = z.borough_id
                 GROUP BY t.pu_location_id ORDER BY 3 DESC""")
    print(f"{'#':>3} {'pickup zone':<38} {'borough':<14} {'trips':>8} {'share':>7} {'cumulative':>11}")
    running = 0
    for i, (name, borough, n) in enumerate(zones[:10], 1):
        running += n
        print(f"{i:>3} {name[:38]:<38} {borough:<14} {n:>8,} {100 * n / total:>6.1f}% {100 * running / total:>10.1f}%")
    running, needed = 0, 0
    for _, _, n in zones:
        running += n
        needed += 1
        if running >= total / 2:
            break
    print(f"\nThe top {needed} of {len(zones)} pickup zones account for half of all pickups.")
    print("\nPickups by borough:")
    for borough, n in q("""SELECT b.borough_name, COUNT(*) FROM trips t
                           JOIN zones z ON z.location_id = t.pu_location_id
                           JOIN boroughs b ON b.borough_id = z.borough_id
                           GROUP BY b.borough_name ORDER BY 2 DESC"""):
        print(f"  {borough:<14} {n:>9,}  {100 * n / total:>5.1f}%")
    print("\nTen busiest routes (pickup to dropoff):")
    for pz, dz, n, fare in q("""SELECT pz.zone_name, dz.zone_name, COUNT(*), ROUND(AVG(t.total_amount), 2)
                                FROM trips t JOIN zones pz ON pz.location_id = t.pu_location_id
                                JOIN zones dz ON dz.location_id = t.do_location_id
                                GROUP BY t.pu_location_id, t.do_location_id ORDER BY 3 DESC LIMIT 10"""):
        print(f"  {n:>7,}  ${fare:<6} {pz[:30]} to {dz[:30]}")
    cross = q("SELECT ROUND(100.0 * AVG(is_cross_borough), 1) FROM trips")[0][0]
    same_zone = q("SELECT ROUND(100.0 * AVG(pu_location_id = do_location_id), 1) FROM trips")[0][0]
    print(f"\nTrips that cross a borough line: {cross}%   Trips that start and end in the same zone: {same_zone}%")

    # ------------------------------------------------------------------ spare ideas
    heading("SPARE IDEAS (use one only if it is more interesting than the three above)")
    print("Weekday vs weekend average trips per day:")
    for wk, n, days in q("SELECT is_weekend, COUNT(*), COUNT(DISTINCT pickup_date) FROM trips GROUP BY is_weekend"):
        print(f"  {'Weekend' if wk else 'Weekday'}: {n / days:,.0f} trips per day ({days} days)")
    print("\nHow people pay:")
    for name, n, tip in q("""SELECT p.payment_type_name, COUNT(*), ROUND(AVG(t.tip_pct), 1) FROM trips t
                             JOIN payment_types p ON p.payment_type_id = t.payment_type_id
                             GROUP BY p.payment_type_name ORDER BY 2 DESC"""):
        print(f"  {name:<14} {n:>9,}  {100 * n / total:>5.1f}%   avg tip % {tip if tip is not None else 'not recorded'}")
    print("\nCard tip % by pickup borough:")
    for borough, n, tip in q("""SELECT b.borough_name, COUNT(*), ROUND(AVG(t.tip_pct), 1) FROM trips t
                                JOIN zones z ON z.location_id = t.pu_location_id
                                JOIN boroughs b ON b.borough_id = z.borough_id
                                WHERE t.tip_pct IS NOT NULL GROUP BY b.borough_name HAVING COUNT(*) >= 100
                                ORDER BY 3 DESC"""):
        print(f"  {borough:<14} {n:>9,} card trips   avg tip {tip}%")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    main(ap.parse_args().db)