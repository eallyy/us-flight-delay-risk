"""Combine 12 months of BTS on-time data (Apr 2025 - Mar 2026) into one parquet.

Source: https://transtats.bts.gov/PREZIP/ (On_Time_Reporting_Carrier_On_Time_Performance)
Airport coords: OurAirports (airports_ourairports.csv).
"""

import zipfile
from pathlib import Path

import pandas as pd

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
BTS = RAW / "bts"
OUT = RAW.parent

USECOLS = [
    "FlightDate", "Year", "Month", "DayOfWeek",
    "Reporting_Airline", "Tail_Number", "Flight_Number_Reporting_Airline",
    "Origin", "OriginCityName", "OriginState",
    "Dest", "DestCityName", "DestState",
    "CRSDepTime", "DepTime", "DepDelayMinutes", "DepDel15", "DepTimeBlk",
    "CRSArrTime", "ArrDelayMinutes", "ArrDel15",
    "TaxiOut", "TaxiIn",
    "Cancelled", "CancellationCode", "Diverted",
    "CRSElapsedTime", "ActualElapsedTime", "AirTime", "Distance",
    "CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay",
]

CARRIERS = {
    "AA": ("American Airlines", "Legacy"), "DL": ("Delta Air Lines", "Legacy"),
    "UA": ("United Airlines", "Legacy"), "AS": ("Alaska Airlines", "Legacy"),
    "HA": ("Hawaiian Airlines", "Legacy"), "WN": ("Southwest Airlines", "Low-cost"),
    "B6": ("JetBlue Airways", "Low-cost"), "NK": ("Spirit Airlines", "Ultra-low-cost"),
    "F9": ("Frontier Airlines", "Ultra-low-cost"), "G4": ("Allegiant Air", "Ultra-low-cost"),
    "OO": ("SkyWest Airlines", "Regional"), "YX": ("Republic Airways", "Regional"),
    "MQ": ("Envoy Air", "Regional"), "OH": ("PSA Airlines", "Regional"),
    "9E": ("Endeavor Air", "Regional"), "YV": ("Mesa Airlines", "Regional"),
    "QX": ("Horizon Air", "Regional"), "PT": ("Piedmont Airlines", "Regional"),
    "ZW": ("Air Wisconsin", "Regional"), "C5": ("CommuteAir", "Regional"),
    "MX": ("Breeze Airways", "Low-cost"), "XP": ("Avelo Airlines", "Ultra-low-cost"),
}


def load_month(zpath: Path) -> pd.DataFrame:
    with zipfile.ZipFile(zpath) as z:
        csv_name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(csv_name) as f:
            df = pd.read_csv(f, usecols=USECOLS, low_memory=False)
    return df


def main() -> None:
    frames = []
    for zpath in sorted(BTS.glob("ontime_*.zip")):
        df = load_month(zpath)
        print(f"{zpath.name}: {len(df):,} rows")
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    print(f"combined: {len(df):,} rows")

    df["FlightDate"] = pd.to_datetime(df["FlightDate"])
    df["dep_hour"] = (df["CRSDepTime"] // 100).clip(0, 23).astype("Int64")
    df["route"] = df["Origin"] + "-" + df["Dest"]
    names = df["Reporting_Airline"].map({k: v[0] for k, v in CARRIERS.items()})
    df["carrier_name"] = names.fillna(df["Reporting_Airline"])
    df["carrier_class"] = df["Reporting_Airline"].map({k: v[1] for k, v in CARRIERS.items()}).fillna("Other")

    air = pd.read_csv(RAW / "airports_ourairports.csv")
    air = air[air["iata_code"].notna()][["iata_code", "name", "municipality", "latitude_deg", "longitude_deg", "iso_region"]]
    air = air.drop_duplicates("iata_code").set_index("iata_code")
    for side in ("Origin", "Dest"):
        df[f"{side.lower()}_lat"] = df[side].map(air["latitude_deg"])
        df[f"{side.lower()}_lon"] = df[side].map(air["longitude_deg"])

    out = OUT / "flights_2025_2026.parquet"
    df.to_parquet(out, index=False)
    print(f"saved {out} ({out.stat().st_size/1e6:.0f} MB)")
    print(df.groupby("carrier_class")["ArrDel15"].mean().round(3))


if __name__ == "__main__":
    main()
