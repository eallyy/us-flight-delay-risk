"""Generate the analysis notebook (analysis.ipynb) from (markdown, code) cell pairs."""

from pathlib import Path

import nbformat as nbf

OUT = Path(__file__).resolve().parent.parent / "notebook"
OUT.mkdir(exist_ok=True)

cells: list = []


def md(text: str) -> None:
    cells.append(nbf.v4.new_markdown_cell(text.strip()))


def code(src: str) -> None:
    cells.append(nbf.v4.new_code_cell(src.strip()))


md("""
# When Should You Fly? — Delay Risk in the US Air Network
### 7 million flights, 12 months (Apr 2025 – Mar 2026), every US domestic carrier

**Business context.** A travel platform wants to answer the question every traveler asks:
*"Which flight should I book to minimize the risk of arriving late?"* Using the US
Department of Transportation's complete on-time performance records, this notebook
quantifies where delay risk comes from — carrier, route, airport, hour, season — and
turns it into concrete booking guidance.

**Data.** [BTS On-Time Reporting Carrier On-Time Performance](https://www.transtats.bts.gov/PREZIP/),
Apr 2025 – Mar 2026 (12 monthly files, 7,027,258 flights). Airport coordinates:
[OurAirports](https://ourairports.com/data/). A flight counts as *delayed* when it
arrives ≥15 minutes late (DOT standard).

**Story in three acts.**
1. **Where** does delay risk cluster? (carrier, geography, hour, route)
2. **Why** — what causes it and how it compounds through the day
3. **So what** — the booking playbook: quantified choices that save time
""")

code("""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

# ---- CVD-safe palette (Okabe-Ito) ----
BLUE, ORANGE, SKY = "#0072B2", "#E69F00", "#56B4E9"
GREEN, RED, PURPLE = "#009E73", "#D55E00", "#CC79A7"
GREY, LIGHTGREY, DARK = "#9A9A9A", "#DCDCDC", "#333333"

pio.templates["clean"] = go.layout.Template(
    layout=dict(
        font=dict(family="Helvetica, Arial, sans-serif", size=13, color=DARK),
        title=dict(font=dict(size=17, color=DARK), x=0.01, xanchor="left"),
        paper_bgcolor="white", plot_bgcolor="white",
        xaxis=dict(showgrid=False, zeroline=False, ticks="outside", ticklen=4),
        yaxis=dict(gridcolor="#EEEEEE", zeroline=False),
        margin=dict(l=120, r=40, t=90, b=70),
        showlegend=False,
    )
)
pio.templates.default = "clean"

df = pd.read_parquet("../data/flights_2025_2026.parquet")
df["ym"] = df["FlightDate"].dt.to_period("M").astype(str)
MONTHS = sorted(df["ym"].unique())
MONTH_LABEL = {m: pd.Period(m).strftime("%b %y") for m in MONTHS}
print(f"{len(df):,} flights | {df.FlightDate.min().date()} → {df.FlightDate.max().date()}")
""")

md("""
## Preliminary EDA
*(exploratory — establishes scale and data quality before the analytical questions)*
""")

code("""
flown = df[df["Cancelled"] == 0]
print(f"flights: {len(df):,}  | flown: {len(flown):,} | cancelled: {df.Cancelled.mean():.2%} | diverted: {df.Diverted.mean():.2%}")
print(f"delayed >=15m (arr): {flown.ArrDel15.mean():.2%} | mean arr delay (delayed only): {flown.loc[flown.ArrDel15==1,'ArrDelayMinutes'].mean():.0f} min")
print(f"carriers: {df.Reporting_Airline.nunique()} | airports: {df.Origin.nunique()} | routes: {df.route.nunique()}")
missing = df[["DepTime", "ArrDelayMinutes", "Tail_Number", "CarrierDelay"]].isna().mean()
print("\\nmissing shares:\\n", missing.round(3))
print("\\nNote: cause columns (CarrierDelay etc.) are only filled for delayed flights - by design.")
""")

code("""
monthly = df.groupby("ym").agg(flights=("FlightDate", "size"), delayed=("ArrDel15", "mean")).reset_index()
fig = go.Figure()
fig.add_bar(x=[MONTH_LABEL[m] for m in monthly.ym], y=monthly.flights, marker_color=LIGHTGREY,
            name="flights")
fig.update_layout(
    title="<b>Scale check: 515k–631k flights per month, no gaps</b><br><sup>US domestic flights by month, Apr 2025 – Mar 2026 (preliminary EDA)</sup>",
    yaxis_title="flights / month", height=380)
fig.show()
""")

md("""
---
# Act 1 — Where does delay risk cluster?

## Q1. Which carriers degrade the most when summer comes?
Carrier choice is the first lever a traveler controls. But a carrier's *average* hides
its seasonal behavior — we compare carriers month by month.
""")

code("""
main = flown[flown.carrier_class != "Regional"]
top_carriers = main.carrier_name.value_counts().head(10).index
cm = (main[main.carrier_name.isin(top_carriers)]
      .groupby(["carrier_name", "ym"]).ArrDel15.mean().unstack()[MONTHS])
cm = cm.dropna()  # keep carriers reporting in all 12 months (drops e.g. Hawaiian's sparse mainland ops)
order = cm.mean(axis=1).sort_values().index
cm = cm.loc[order] * 100

summer = cm[[m for m in MONTHS if m[5:] in ("06", "07", "08")]].mean(axis=1)
winter = cm[[m for m in MONTHS if m[5:] in ("12", "01", "02")]].mean(axis=1)
worst = (summer - winter).idxmax()

cm.columns = [MONTH_LABEL[m] for m in cm.columns]
fig = px.imshow(cm.round(1), color_continuous_scale="Oranges", aspect="auto", text_auto=".0f",
                labels=dict(color="% delayed"))
fig.update_xaxes(side="bottom", tickangle=0)
fig.update_layout(
    title=f"<b>{worst} loses the most punctuality in summer "
          f"(+{(summer-winter)[worst]:.0f} pts vs winter)</b><br>"
          "<sup>% of arrivals delayed ≥15 min, by mainline carrier and month · sorted by overall punctuality</sup>",
    height=480, coloraxis_showscale=False, xaxis_title=None, yaxis_title=None)
fig.show()
print(cm.mean(axis=1).round(1).to_string())
""")

md("""
## Q2. Which states are the delay hotspots — and is it where the traffic is?
Geography sets the baseline: weather regimes and airspace congestion differ by region.
""")

code("""
st = (flown.groupby("OriginState")
      .agg(flights=("FlightDate", "size"), delayed=("ArrDel15", "mean"), avg_dep=("DepDelayMinutes", "mean"))
      .query("flights > 20_000").reset_index())
worst_state = st.loc[st.delayed.idxmax()]

fig = px.choropleth(st, locations="OriginState", locationmode="USA-states", scope="usa",
                    color=st.delayed * 100, color_continuous_scale="Oranges",
                    labels=dict(color="% delayed"))
fig.update_layout(
    title=f"<b>Delay risk concentrates around Chicago, the Northeast corridor and Florida — "
          f"{worst_state.OriginState} worst at {worst_state.delayed:.0%}</b><br>"
          "<sup>% of departures arriving ≥15 min late by origin state · states with >20k flights/yr</sup>",
    height=520, coloraxis_colorbar=dict(len=0.7))
fig.show()
print(st.nlargest(8, "delayed")[["OriginState", "flights", "delayed"]].to_string(index=False))
""")

md("""
## Q3. Does the "fly before 9 am" rule actually hold?
Received wisdom says early flights are safer. We test it across the biggest hubs.
""")

code("""
hubs = flown.Origin.value_counts().head(8).index
hr = flown[flown.dep_hour.between(5, 23)].groupby("dep_hour").ArrDel15.mean() * 100
hub_hr = (flown[flown.Origin.isin(hubs) & flown.dep_hour.between(5, 23)]
          .groupby(["Origin", "dep_hour"]).ArrDel15.mean() * 100)

worst_hub = hub_hr.groupby("Origin").max().idxmax()
fig = go.Figure()
for h in hubs:
    s = hub_hr.loc[h]
    fig.add_scatter(x=s.index, y=s.values, mode="lines", line=dict(color=LIGHTGREY, width=1.2),
                    hovertemplate=f"{h}: %{{y:.0f}}%<extra></extra>")
fig.add_scatter(x=hr.index, y=hr.values, mode="lines", line=dict(color=BLUE, width=3.5),
                name="national")
s = hub_hr.loc[worst_hub]
fig.add_scatter(x=s.index, y=s.values, mode="lines", line=dict(color=ORANGE, width=2.5))
fig.add_annotation(x=s.idxmax(), y=s.max(), text=f"<b>{worst_hub}</b>", font=dict(color=ORANGE),
                   showarrow=False, yshift=12)
fig.add_annotation(x=8, y=hr.loc[8], text="<b>national</b>", font=dict(color=BLUE), showarrow=False, yshift=-16)
early, late = hr.loc[5:8].mean(), hr.loc[18:21].mean()
fig.update_layout(
    title=f"<b>The 8 am rule is real: evening flights are {late/early:.1f}× more likely to be late</b><br>"
          f"<sup>% delayed by scheduled departure hour · grey = 8 busiest hubs · {worst_hub} highlighted</sup>",
    xaxis_title="scheduled departure hour", yaxis_title="% delayed ≥15 min", height=440)
fig.show()
""")

md("""
## Q4. Which busy routes are the least reliable — and who is to blame?
High-volume routes with poor reliability hurt the most travelers.
""")

code("""
rt = (flown.groupby("route")
      .agg(flights=("FlightDate", "size"), delayed=("ArrDel15", "mean"),
           avg_delay=("ArrDelayMinutes", "mean"))
      .nlargest(50, "flights").reset_index())
rt["delayed"] *= 100
bad = rt.nlargest(5, "delayed")

fig = go.Figure()
fig.add_scatter(x=rt.flights, y=rt.delayed, mode="markers",
                marker=dict(color=GREY, size=9, opacity=0.65),
                text=rt.route, hovertemplate="%{text}: %{y:.0f}%<extra></extra>")
fig.add_scatter(x=bad.flights, y=bad.delayed, mode="markers+text",
                marker=dict(color=ORANGE, size=11), text=bad.route, textposition="top center",
                textfont=dict(color=ORANGE, size=11))
fig.add_hline(y=rt.delayed.mean(), line=dict(color=LIGHTGREY, dash="dot"),
              annotation_text="top-50 average", annotation_font_color=GREY)
fig.update_layout(
    title=f"<b>{bad.iloc[0].route} is the least reliable big route — "
          f"{bad.iloc[0].delayed:.0f}% of arrivals run late</b><br>"
          "<sup>50 busiest US routes · x = annual flights, y = % delayed ≥15 min</sup>",
    xaxis_title="flights per year", yaxis_title="% delayed", height=460)
fig.show()
""")

md("""
---
# Act 2 — Why: cause decomposition and dynamics

## Q5. What actually causes delay — and how does the mix shift with the seasons?
DOT decomposes every delayed flight's minutes into five causes. The mix, not the total,
tells you what is fixable.
""")

code("""
CAUSES = {"CarrierDelay": ("Carrier", BLUE), "LateAircraftDelay": ("Late aircraft", ORANGE),
          "NASDelay": ("Airspace (NAS)", SKY), "WeatherDelay": ("Extreme weather", PURPLE),
          "SecurityDelay": ("Security", GREEN)}
cs = flown.groupby("ym")[list(CAUSES)].sum()
share = cs.div(cs.sum(axis=1), axis=0) * 100

fig = go.Figure()
for col, (label, color) in CAUSES.items():
    fig.add_bar(x=[MONTH_LABEL[m] for m in share.index], y=share[col], name=label,
                marker_color=color)
late_share = share["LateAircraftDelay"].mean()
fig.update_layout(
    barmode="stack", showlegend=True,
    legend=dict(orientation="h", y=-0.15),
    title=f"<b>{late_share:.0f}% of all delay minutes are inherited from a late aircraft — "
          "the system's biggest lever</b><br>"
          "<sup>share of total delay minutes by DOT cause category and month</sup>",
    yaxis_title="% of delay minutes", height=480)
fig.show()
""")

md("""
## Q6. How does delay cascade through the day?
If late aircraft dominate, delay should *accumulate*: every evening flight inherits the
sins of the morning. We measure the inherited share by hour.
""")

code("""
hourly = flown[flown.dep_hour.between(5, 23)].groupby("dep_hour").agg(
    late_ac=("LateAircraftDelay", "sum"), total=("ArrDelayMinutes", "sum"),
    avg_delay=("DepDelayMinutes", "mean"))
hourly["inherited"] = hourly.late_ac / hourly.total * 100

fig = go.Figure()
fig.add_bar(x=hourly.index, y=hourly.avg_delay, marker_color=LIGHTGREY, yaxis="y2")
fig.add_scatter(x=hourly.index, y=hourly.inherited, mode="lines+markers",
                line=dict(color=ORANGE, width=3))
fig.add_annotation(x=21, y=hourly.inherited.loc[21], yshift=14,
                   text="<b>inherited share</b>", font=dict(color=ORANGE), showarrow=False)
fig.update_layout(
    title=f"<b>By evening, {hourly.inherited.loc[18:22].mean():.0f}% of delay is inherited — "
          "delay is a cascade, not bad luck</b><br>"
          "<sup>orange: % of delay minutes caused by late-arriving aircraft · grey bars: avg departure delay (min, right axis)</sup>",
    xaxis_title="scheduled departure hour", yaxis_title="% of delay minutes inherited",
    yaxis2=dict(overlaying="y", side="right", showgrid=False, title="avg dep delay (min)"),
    height=460)
fig.show()
""")

md("""
## Q7. Can airlines buy punctuality with schedule padding?
Block-time padding (scheduled minus actual flying time) is the airline's insurance
policy against delay. If padding worked as insurance, the most-padded routes should be
the most punctual. We test that directly.
""")

code("""
rp = (flown.dropna(subset=["ActualElapsedTime"])
      .assign(padding=lambda d: d.CRSElapsedTime - d.ActualElapsedTime)
      .groupby("route")
      .agg(flights=("FlightDate", "size"), padding=("padding", "median"),
           delayed=("ArrDel15", "mean"), dist=("Distance", "median"))
      .nlargest(100, "flights").reset_index())
rp["delayed"] *= 100
corr = rp.padding.corr(rp.delayed)

rp["padded"] = rp.padding >= rp.padding.median()

fig = px.scatter(rp, x="padding", y="delayed", size="flights", size_max=26,
                 color_discrete_sequence=[GREY], hover_name="route", opacity=0.6)
b1, b0 = np.polyfit(rp.padding, rp.delayed, 1)
xs = np.linspace(rp.padding.min(), rp.padding.max(), 50)
fig.add_scatter(x=xs, y=b0 + b1 * xs, mode="lines", line=dict(color=ORANGE, width=2.5))
lean = rp.nsmallest(5, "padding")
fig.add_scatter(x=lean.padding, y=lean.delayed, mode="markers",
                marker=dict(color=BLUE, size=12), hovertext=lean.route)
fig.add_annotation(x=lean.padding.median(), y=lean.delayed.max(), ax=55, ay=-40,
                   text="<b>Hawaiian inter-island hops</b><br>barely padded, most punctual",
                   font=dict(size=10, color=BLUE), arrowcolor=BLUE)
for _, r in rp.nlargest(2, "padding").iterrows():
    fig.add_annotation(x=r.padding, y=r.delayed, text=r.route, font=dict(size=10, color=DARK),
                       arrowcolor=GREY, ax=0, ay=-24)
fig.update_layout(
    title=f"<b>Padding is a symptom, not a cure — the most-padded routes are no more "
          f"punctual (r = {corr:+.2f})</b><br>"
          "<sup>100 busiest routes · x = median (scheduled − actual) block time, y = % delayed · bubble = volume</sup>",
    xaxis_title="median schedule padding (min)", yaxis_title="% delayed", height=470)
fig.show()
print(f"correlation padding vs %delayed: {corr:+.3f} (flat)")
print(f"padding vs distance: {rp.padding.corr(rp.dist):+.2f} - airlines pad long, hard routes")
""")

md("""
**Reading it correctly.** The trend is flat and slightly *positive* — padding does not
buy punctuality. The confound explains why: padding tracks route difficulty
(correlation with distance is strong). Airlines add slack precisely where flying is
long and hubs are congested, and that slack is only enough to keep those routes near
the average — never down to the reliability of a short, simple hop. Padding absorbs
delay; it does not prevent it.
""")

md("""
## Q8. Are airport delays driven by weather or by congestion?
The fix differs: weather-driven airports need buffers, congestion-driven ones need
schedule discipline. We classify the 30 biggest airports.
""")

code("""
ap = (flown.groupby("Origin")
      .agg(flights=("FlightDate", "size"),
           weather=("WeatherDelay", "mean"), nas=("NASDelay", "mean"),
           delayed=("ArrDel15", "mean"))
      .nlargest(30, "flights").reset_index())

mx, my = ap.weather.median(), ap.nas.median()
fig = px.scatter(ap, x="weather", y="nas", size="flights", size_max=30,
                 color=ap.delayed * 100, color_continuous_scale="Oranges",
                 hover_name="Origin", text="Origin",
                 labels=dict(color="% delayed"))
fig.update_traces(textposition="top center", textfont=dict(size=9, color=GREY))
fig.add_vline(x=mx, line=dict(color=LIGHTGREY, dash="dot"))
fig.add_hline(y=my, line=dict(color=LIGHTGREY, dash="dot"))
fig.add_annotation(x=ap.weather.max(), y=my, text="weather-exposed →", showarrow=False,
                   font=dict(color=GREY, size=11), yshift=-14, xanchor="right")
fig.add_annotation(x=mx, y=ap.nas.max(), text="↑ congestion-driven", showarrow=False,
                   font=dict(color=GREY, size=11), xshift=6, xanchor="left")
fig.update_layout(
    title="<b>Two different diseases: NYC airports suffer congestion, "
          "the South suffers weather</b><br>"
          "<sup>30 busiest airports · x = weather-delay min/flight, y = airspace-delay min/flight · color = % delayed</sup>",
    xaxis_title="weather delay (min per flight)", yaxis_title="airspace/NAS delay (min per flight)",
    height=520)
fig.show()
""")

md("""
## Q9. Cancellation: which carrier×airport pairs simply give up?
Delay is recoverable; cancellation is not. Are the same carriers bad at both?
""")

code("""
top_ap = flown.Origin.value_counts().head(12).index
cx = (df[df.Origin.isin(top_ap) & df.carrier_name.isin(top_carriers)]
      .groupby(["carrier_name", "Origin"]).Cancelled.mean().unstack() * 100)
cx = cx.dropna(thresh=8).loc[lambda d: d.mean(axis=1).sort_values().index]

fig = px.imshow(cx.round(1), color_continuous_scale="Oranges", aspect="auto", text_auto=".1f",
                labels=dict(color="% cancelled"))
fig.update_xaxes(side="bottom")
wc, wa = np.unravel_index(np.nanargmax(cx.values), cx.shape)
fig.update_layout(
    title=f"<b>{cx.index[wc]} at {cx.columns[wa]} cancels {cx.values[wc, wa]:.1f}% of flights — "
          f"{cx.values[wc, wa]/df.Cancelled.mean()/100:.1f}× the national rate</b><br>"
          "<sup>cancellation rate (%), 10 largest mainline carriers × 12 busiest airports</sup>",
    height=480, coloraxis_showscale=False, xaxis_title=None, yaxis_title=None)
fig.show()
""")

md("""
---
# Act 3 — So what: the booking playbook

## Q10. On the biggest routes, how much time does the *right* choice save?
Same route, same day — different carrier and departure window. The spread is the prize.
""")

code("""
flown_tb = flown.assign(window=pd.cut(flown.dep_hour, [4, 11, 16, 24],
                                      labels=["morning", "afternoon", "evening"]))
top10 = flown.route.value_counts().head(10).index
combos = (flown_tb[flown_tb.route.isin(top10)]
          .groupby(["route", "carrier_name", "window"], observed=True)
          .agg(n=("FlightDate", "size"), exp_delay=("ArrDelayMinutes", "mean"))
          .query("n >= 200").reset_index())
best = combos.loc[combos.groupby("route").exp_delay.idxmin()].set_index("route")
worst = combos.loc[combos.groupby("route").exp_delay.idxmax()].set_index("route")
saving = (worst.exp_delay - best.exp_delay).sort_values(ascending=False)

fig = go.Figure()
for r in saving.index:
    fig.add_scatter(x=[best.loc[r, "exp_delay"], worst.loc[r, "exp_delay"]], y=[r, r],
                    mode="lines", line=dict(color=LIGHTGREY, width=3), showlegend=False)
fig.add_scatter(x=worst.loc[saving.index, "exp_delay"], y=saving.index, mode="markers",
                marker=dict(color=GREY, size=11), name="worst choice")
fig.add_scatter(x=best.loc[saving.index, "exp_delay"], y=saving.index, mode="markers",
                marker=dict(color=GREEN, size=11), name="best choice")
r0 = saving.index[0]
fig.add_annotation(x=worst.loc[r0, "exp_delay"], y=r0,
                   text=f"{worst.loc[r0, 'carrier_name']} {worst.loc[r0, 'window']}",
                   font=dict(size=10, color=GREY), yshift=13, showarrow=False)
fig.add_annotation(x=best.loc[r0, "exp_delay"], y=r0,
                   text=f"{best.loc[r0, 'carrier_name']} {best.loc[r0, 'window']}",
                   font=dict(size=10, color=GREEN), yshift=13, showarrow=False)
fig.update_layout(
    title=f"<b>Choosing well saves up to {saving.max():.0f} expected minutes per trip "
          f"({r0})</b><br>"
          "<sup>10 busiest routes · expected arrival delay of best vs worst carrier+window combo (≥200 flights)</sup>",
    xaxis_title="expected arrival delay (min)", height=470, showlegend=True,
    legend=dict(orientation="h", y=-0.12))
fig.show()
""")

md("""
## Q11. Holiday travel: which peaks actually break the system?
Everyone fears Thanksgiving. The data says fear summer thunderstorm season more.
""")

code("""
daily = flown.set_index("FlightDate").resample("D").ArrDel15.mean() * 100
roll = daily.rolling(7, center=True).mean()

HOLIDAYS = {"Jul 4": ("2025-06-30", "2025-07-07"), "Thanksgiving": ("2025-11-24", "2025-12-01"),
            "Christmas/NY": ("2025-12-19", "2026-01-04")}
fig = go.Figure()
fig.add_scatter(x=daily.index, y=daily.values, mode="lines",
                line=dict(color=LIGHTGREY, width=1))
fig.add_scatter(x=roll.index, y=roll.values, mode="lines", line=dict(color=BLUE, width=3))
for label, (a, b) in HOLIDAYS.items():
    fig.add_vrect(x0=a, x1=b, fillcolor=ORANGE, opacity=0.15, line_width=0)
    fig.add_annotation(x=pd.Timestamp(a) + (pd.Timestamp(b) - pd.Timestamp(a)) / 2,
                       y=daily.max() * 0.97, text=f"<b>{label}</b>",
                       font=dict(size=10, color=ORANGE), showarrow=False)
peak_day = daily.idxmax()
fig.add_annotation(x=peak_day, y=daily.max(), text=f"worst day: {peak_day:%b %d} ({daily.max():.0f}%)",
                   arrowcolor=GREY, font=dict(size=10), ax=40, ay=-25)
fig.update_layout(
    title="<b>Summer storm season strains the network more than any holiday</b><br>"
          "<sup>daily % of arrivals delayed ≥15 min (grey) with 7-day average (blue) · holiday windows shaded</sup>",
    yaxis_title="% delayed", height=440)
fig.show()
""")

md("""
## Q12. The route reliability score — one number a booking engine can use
We fold four risk dimensions into a single composite score per route
(delay probability, delay severity, cancellation risk, cascade exposure),
z-scored and averaged. This is the metric a travel product would ship.
""")

code("""
rs = (df.groupby("route")
      .agg(flights=("FlightDate", "size"), delayed=("ArrDel15", "mean"),
           sev=("ArrDelayMinutes", "mean"), cancel=("Cancelled", "mean"),
           cascade=("LateAircraftDelay", "mean"))
      .query("flights >= 2000").copy())
for c in ["delayed", "sev", "cancel", "cascade"]:
    rs[f"z_{c}"] = (rs[c] - rs[c].mean()) / rs[c].std()
rs["score"] = rs[[f"z_{c}" for c in ["delayed", "sev", "cancel", "cascade"]]].mean(axis=1)

show = pd.concat([rs.nsmallest(10, "score"), rs.nlargest(10, "score")]).sort_values("score")
colors = [GREEN] * 10 + [ORANGE] * 10
fig = go.Figure(go.Bar(x=show.score, y=show.index, orientation="h", marker_color=colors))
fig.add_vline(x=0, line=dict(color=GREY, width=1))
fig.update_layout(
    title=f"<b>The reliability gap is structural: {show.index[-1]} vs {show.index[0]} "
          "is a different product</b><br>"
          "<sup>composite risk score (z-scored delay prob + severity + cancellation + cascade exposure) · "
          "10 best & 10 worst of all routes with ≥2,000 flights/yr</sup>",
    xaxis_title="composite delay-risk score (lower = more reliable)", height=560)
fig.show()
print(f"routes scored: {len(rs):,}")
""")

md("""
---
# Conclusions

1. **Delay is structural, not random.** Risk concentrates in identifiable carriers
   (ULCCs degrade hardest in summer), regions (Northeast + Florida), hours (evening)
   and routes.
2. **The cascade is the system's core disease** — roughly a third of all delay minutes
   are inherited from late aircraft, and the inherited share grows all day. This is why
   the morning rule works.
3. **The airline's own defence is limited.** Schedule padding tracks route difficulty
   rather than curing it, so the fix has to come from the schedule structure
   (congestion) or from buffers where weather dominates — the two diseases need
   different medicine.
4. **Travelers have real agency.** On the biggest routes, picking the right
   carrier + departure window saves double-digit expected minutes, and a composite
   score makes route risk a single bookable number.

**Limitations.** One year of data (no COVID-era baseline); cause attribution is
carrier-reported; estimated relationships are correlational, not causal.

*Data: US DOT/BTS On-Time Performance, Apr 2025 – Mar 2026 · Analysis: Plotly only ·
CVD-safe Okabe-Ito palette throughout.*
""")

nb = nbf.v4.new_notebook(cells=cells, metadata={
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3"},
})
path = OUT / "analysis.ipynb"
nbf.write(nb, path)
print(f"wrote {path} with {len(cells)} cells")
