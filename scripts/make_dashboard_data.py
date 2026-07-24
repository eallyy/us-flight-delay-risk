"""Precompute small aggregate tables for the Streamlit dashboard.

The full 7M-row parquet (162 MB) is too large for a GitHub repo / Community Cloud,
so the dashboard reads these aggregates (< 5 MB total) instead.
"""

from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = Path(__file__).resolve().parent.parent / "dashboard" / "data"
OUT.mkdir(parents=True, exist_ok=True)

df = pd.read_parquet(DATA / "flights_2025_2026.parquet")
df["ym"] = df["FlightDate"].dt.to_period("M").astype(str)
flown = df[df.Cancelled == 0]

# 1. KPI summary
pd.DataFrame([{
    "flights": len(df), "delayed_share": flown.ArrDel15.mean(),
    "cancelled_share": df.Cancelled.mean(),
    "mean_delay_when_delayed": flown.loc[flown.ArrDel15 == 1, "ArrDelayMinutes"].mean(),
    "carriers": df.Reporting_Airline.nunique(), "airports": df.Origin.nunique(),
    "routes": df.route.nunique(),
    "date_min": str(df.FlightDate.min().date()), "date_max": str(df.FlightDate.max().date()),
}]).to_csv(OUT / "kpi.csv", index=False)

# 2. carrier x month
(flown[flown.carrier_class != "Regional"]
 .groupby(["carrier_name", "carrier_class", "ym"])
 .agg(flights=("FlightDate", "size"), delayed=("ArrDel15", "mean"),
      avg_delay=("ArrDelayMinutes", "mean"), cancelled_n=("FlightDate", "size"))
 .reset_index()).to_csv(OUT / "carrier_month.csv", index=False)

# cancellation needs all flights, not just flown
(df[df.carrier_class != "Regional"]
 .groupby(["carrier_name", "ym"])
 .agg(flights=("FlightDate", "size"), cancelled=("Cancelled", "mean"))
 .reset_index()).to_csv(OUT / "carrier_cancel.csv", index=False)

# 3. state aggregates
(flown.groupby("OriginState")
 .agg(flights=("FlightDate", "size"), delayed=("ArrDel15", "mean"),
      avg_dep_delay=("DepDelayMinutes", "mean"))
 .reset_index()).to_csv(OUT / "state.csv", index=False)

# 4. airport aggregates (top 40)
(flown.groupby(["Origin", "OriginCityName"])
 .agg(flights=("FlightDate", "size"), delayed=("ArrDel15", "mean"),
      weather=("WeatherDelay", "mean"), nas=("NASDelay", "mean"),
      late_ac=("LateAircraftDelay", "mean"),
      lat=("origin_lat", "first"), lon=("origin_lon", "first"))
 .nlargest(40, "flights").reset_index()).to_csv(OUT / "airports.csv", index=False)

# 5. hour x airport (top 12 hubs) + national
hubs = flown.Origin.value_counts().head(12).index
hr_hub = (flown[flown.Origin.isin(hubs) & flown.dep_hour.between(5, 23)]
          .groupby(["Origin", "dep_hour"])
          .agg(flights=("FlightDate", "size"), delayed=("ArrDel15", "mean")).reset_index())
hr_nat = (flown[flown.dep_hour.between(5, 23)].groupby("dep_hour")
          .agg(flights=("FlightDate", "size"), delayed=("ArrDel15", "mean")).reset_index())
hr_nat["Origin"] = "National"
pd.concat([hr_hub, hr_nat]).to_csv(OUT / "hourly.csv", index=False)

# 6. cause mix by month
CAUSES = ["CarrierDelay", "LateAircraftDelay", "NASDelay", "WeatherDelay", "SecurityDelay"]
flown.groupby("ym")[CAUSES].sum().reset_index().to_csv(OUT / "cause_month.csv", index=False)

# hourly inherited share
(flown[flown.dep_hour.between(5, 23)].groupby("dep_hour")
 .agg(late_ac=("LateAircraftDelay", "sum"), total=("ArrDelayMinutes", "sum"),
      avg_dep=("DepDelayMinutes", "mean"))
 .reset_index()).to_csv(OUT / "hourly_inherited.csv", index=False)

# 7. daily national series
(flown.set_index("FlightDate").resample("D")
 .agg(flights=("ArrDel15", "size"), delayed=("ArrDel15", "mean"))
 .reset_index()).to_csv(OUT / "daily.csv", index=False)

# 8. route-level table (all routes >= 1000 flights) incl. score components
rs = (df.groupby("route")
      .agg(flights=("FlightDate", "size"), delayed=("ArrDel15", "mean"),
           severity=("ArrDelayMinutes", "mean"), cancelled=("Cancelled", "mean"),
           cascade=("LateAircraftDelay", "mean"), distance=("Distance", "median"))
      .query("flights >= 1000").reset_index())
for c in ["delayed", "severity", "cancelled", "cascade"]:
    rs[f"z_{c}"] = (rs[c] - rs[c].mean()) / rs[c].std()
rs["score"] = rs[[f"z_{c}" for c in ["delayed", "severity", "cancelled", "cascade"]]].mean(axis=1)
rs[["origin", "dest"]] = rs.route.str.split("-", expand=True)
air = pd.read_csv(DATA / "raw" / "airports_ourairports.csv")
air = air[air.iata_code.notna()].drop_duplicates("iata_code").set_index("iata_code")
for side in ("origin", "dest"):
    rs[f"{side}_lat"] = rs[side].map(air.latitude_deg)
    rs[f"{side}_lon"] = rs[side].map(air.longitude_deg)
rs.to_csv(OUT / "routes.csv", index=False)

# 9. booking combos: top 25 routes x carrier x window
flown_tb = flown.assign(window=pd.cut(flown.dep_hour, [4, 11, 16, 24],
                                      labels=["morning", "afternoon", "evening"]))
top25 = flown.route.value_counts().head(25).index
(flown_tb[flown_tb.route.isin(top25)]
 .groupby(["route", "carrier_name", "window"], observed=True)
 .agg(flights=("FlightDate", "size"), exp_delay=("ArrDelayMinutes", "mean"),
      delayed=("ArrDel15", "mean"))
 .query("flights >= 200").reset_index()).to_csv(OUT / "combos.csv", index=False)

total = sum(f.stat().st_size for f in OUT.glob("*.csv")) / 1e6
print(f"wrote {len(list(OUT.glob('*.csv')))} files, {total:.1f} MB total")
