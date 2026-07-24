# 🛫 US Flight Delay Risk — When Should You Fly?

Analysis of **7,027,258 US domestic flights** (April 2025 – March 2026) answering the
question every traveler asks: *which flight should I book to minimize the risk of
arriving late?*

**Live dashboard:** https://us-flight-delay-risk-ismail-emir-alanyalioglu.streamlit.app/

Final individual project for the MSc Data Visualization course (Summer 2026).

## Findings at a glance

- **22.8%** of US domestic flights arrive ≥15 min late; when late, the average delay is **74 minutes**.
- Delay is a **cascade**: roughly a third of all delay minutes are inherited from a
  late-arriving aircraft, and the inherited share grows all day — by evening it approaches half.
  This is why the "fly before 9 am" rule genuinely works.
- Risk is **structural**, concentrated in identifiable carriers (ULCCs degrade hardest in
  summer), regions (Northeast corridor, Chicago, Florida) and hours (evening).
- Travelers have real agency: on the busiest routes, picking the right carrier + departure
  window saves **up to ~60 expected minutes** per trip.

## Deliverables

| Piece | Where |
|---|---|
| Analysis notebook (EDA + 12 analytical questions, Plotly only) | [`notebook/analysis.ipynb`](notebook/analysis.ipynb) · [HTML export](notebook/analysis.html) |
| Interactive dashboard (4 tabs, Streamlit + Plotly) | [`app.py`](app.py) · live link above |
| Data pipeline | [`scripts/`](scripts/) |

## Data

| Source | Used for | Link |
|---|---|---|
| US DOT / BTS On-Time Reporting Carrier On-Time Performance (12 monthly files, Apr 2025 – Mar 2026) | flights, delays, causes, cancellations | [transtats.bts.gov/PREZIP](https://www.transtats.bts.gov/PREZIP/) |
| OurAirports | airport coordinates | [ourairports.com/data](https://ourairports.com/data/) |

**The full dataset ships inside this repo.** The combined file (7,027,258 rows, 162 MB)
exceeds GitHub's 100 MB per-file limit, so it lives in [`data/full/`](data/full/) as four
quarterly parquet parts. Reassemble it with one call:

```python
from scripts.load_full_data import load_flights
df = load_flights()  # 7,027,258 rows, Apr 2025 - Mar 2026
```

It is also attached as a single file under
[Releases → data-v1](../../releases/tag/data-v1). The dashboard itself reads the small
pre-aggregated tables in [`data/`](data/) (produced by `scripts/make_dashboard_data.py`).
To rebuild everything from the original source instead: download the monthly zips from
the BTS link above into `data/raw/bts/`, then run `scripts/prepare_flights.py` followed
by `scripts/make_dashboard_data.py`.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Design notes

Plotly-only figures; CVD-safe Okabe-Ito palette; muted grey context + one highlight
color; takeaway-stating titles; white background; decluttered axes. A flight counts as
*delayed* at ≥15 min after scheduled arrival (DOT standard).
