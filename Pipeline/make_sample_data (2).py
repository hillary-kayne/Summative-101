import numpy as np
import pandas as pd
import argparse 
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW=ROOT / "data" / "raw"
AIRPORTS= (132, 138) # JFK, LaGuardia
def zone_weights(lookup):
    """Busy manhattan zones and the airports get most trips, like the
      real city"""
    w=[]
    for r in lookup.itertuples():
        if r.LocationID in AIRPORTS:
            w.append(8.0)
        elif r.LocationID in (264,265):
            w.append(0.3)
        elif r.service_zone=="Yellow Zone":
            w.append(10.0)
        elif r.service_zone=="EWR":
            w.append(0.2)
        else:
            w.append(1.0)
    w=np.array(w)
    return w/w.sum()
def make_trips(n, lookup, seed=7):
    rng = np.random.default_rng(seed)
    ids=lookup["LocationID"].to_numpy()
    p=zone_weights(lookup)

    day=rng.integers(1,32,n)
    hour_p=np.array([4 , 3, 2, 1, 1, 1, 2, 4, 6, 5, 5, 5, 5, 5, 6, 6, 7, 8, 8, 7, 6, 6, 5],float)
    hour_p/=hour_p.sum()
    hour=rng.choice(24, n, p=hour_p)
    pickup=pd.to_datetime("2019-01-01") + pd.to_timedelta((day-1)*86400 + hour*3600 + rng.integers(0, 3600, n), unit="s")

    pu=rng.choice(ids, n, p=p)
    do=rng.choice(ids, n, p=p)
    airport=np.isin(pu, AIRPORTS) | np.isin(do, AIRPORTS)
    dist=np.round(np.clip(rng.lognormal(0.55,0.85, n), 0.1, 40), 2)
    dist=np.where(airport, np.round(dist + rng.uniform(5, 13, n), 2), dist)
    rush=np.isin(hour, [7,8,9,16,17,18,19])
    speed=np.clip(rng.normal(np.where(rush, 8.5, 13),3), 4, 35)
    minutes=np.clip(dist / speed * 60 + rng.uniform(1,4,n), 2, 180)
    dropoff=pickup + pd.to_timedelta(np.round(minutes*60), unit="s")

    payments= rng.choice([1, 2, 3, 4] n, p=[0.68, 0.30, 0.012, 0.008])
    fare = np.round(2.5 + 2.5 * dist + 0.5* minutes, 2)
    tip= np.where(payment ==1, np.round(fare * rng.uniform(0.0, 0.3, n), 2), 0.0)
    extra=np.where(rush | (hour>=20) | (hour < 6), 0.5, 0.0)
    tolls= np.where(airport & (rng.random(n) < 0.4), 5.76, 0.0)
    total= np.round(fare + extra + 0.5 + tip + tolls + 0.3, 2)  

    df = pd.DataFrame({
        "VendorID": rng.choice([1, 2], n),
        "tpep_pickup_datetime": pickup,
        "tpep_dropoff_datetime": dropoff,
        "passenger_count": rng.choice([1, 2, 3, 4, 5, 6], n, p=[0,7, 0.15, 0.05, 0.03, 0.05, 0.02]),
        "trip_distance": dist,
        "RateCodeID": np.where(np.isin(pu, [132]) | np.isin(do, [132]), 2, 1),
        "store_and_fwd_flag": rng.choice(["Y", "N"], n, p=[0.01, 0.99]),
        "PULocationID": pu,
        "DOLocationID": do,
        "payment_type": payments,
        "fare_amount": fare,
        "extra": extra,
        "mta_tax": 0.5,
        "tip_amount": tip,
        "tolls_amount": tolls,
        "improvement_surcharge": 0.3,
        "total_amount": total,
        "congestion_surcharge": np.where((pickup >= pd.to_datetime("2019-01-01")) & (pickup < pd.to_datetime("2019-09-01")), 2.5, 0.03),
        
    })   
    def pick(k):
        return rng.choice(n, k, replace=False)

    k = max(n // 100, 5)
    df.loc[pick(k), "fare_amount"] = -5.0                                    
    df.loc[pick(k), "trip_distance"] = 500.0                                  
    i = pick(k)
    df.loc[i, "tpep_dropoff_datetime"] = df.loc[i, "tpep_pickup_datetime"] - pd.Timedelta(minutes=10)
    i = pick(k)                                                            
    df.loc[i, "tpep_pickup_datetime"] = pd.Timestamp("2018-11-28 15:52:25")
    df.loc[i, "tpep_dropoff_datetime"] = pd.Timestamp("2018-11-28 15:55:45")
    i = pick(k)                                                         
    df.loc[i, ["trip_distance", "RatecodeID", "fare_amount", "PULocationID", "DOLocationID"]] = [0.0, 2, 52.0, 193, 193]
    df.loc[pick(k), "PULocationID"] = 999                                    
    df.loc[pick(k), "total_amount"] = np.nan                                   
    i = pick(k)
    df.loc[i, "tpep_dropoff_datetime"] = df.loc[i, "tpep_pickup_datetime"] + pd.Timedelta(seconds=1)   
    i = pick(k)
    df.loc[i, "trip_distance"] = 60.0                                          
    df.loc[i, "tpep_dropoff_datetime"] = df.loc[i, "tpep_pickup_datetime"] + pd.Timedelta(minutes=20)
    df.loc[pick(k), "passenger_count"] = 0                                     
    dupes = df.sample(k, random_state=3)
    df = pd.concat([df, dupes], ignore_index=True)                            
    return df.sample(frac=1, random_state=1).reset_index(drop=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=20000)
    args = ap.parse_args()

    lookup_path = RAW / "taxi_zone_lookup.csv"
    if not lookup_path.exists():
        raise SystemExit(f"Put the real taxi_zone_lookup.csv in {RAW} first (this tool uses its zone ids).")
    lookup = pd.read_csv(lookup_path, keep_default_na=False)

    trips = make_trips(args.rows, lookup)
    out = RAW / "yellow_tripdata_sample.parquet"
    trips.to_parquet(out, index=False)
    print(f"Wrote {len(trips):,} FAKE trips to {out}")
    print("Reminder: these are invented. Use the real TLC file for the report.")
                