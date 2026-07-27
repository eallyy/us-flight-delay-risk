"""US Flight Delay Risk — interactive dashboard.

Data: US DOT/BTS On-Time Performance, Apr 2025 - Mar 2026 (7.0M flights),
pre-aggregated in data/ (see repo scripts).
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

st.set_page_config(page_title="US Flight Delay Risk", page_icon="🛫", layout="wide")

# ---- CVD-safe palette (Okabe-Ito) ----
BLUE, ORANGE, SKY = "#0072B2", "#E69F00", "#56B4E9"
GREEN, PURPLE = "#009E73", "#CC79A7"
GREY, LIGHTGREY, DARK = "#9A9A9A", "#DCDCDC", "#333333"

pio.templates["clean"] = go.layout.Template(
    layout=dict(
        font=dict(family="Helvetica, Arial, sans-serif", size=13, color=DARK),
        title=dict(font=dict(size=16, color=DARK), x=0.01, xanchor="left"),
        paper_bgcolor="white", plot_bgcolor="white",
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(gridcolor="#EEEEEE", zeroline=False),
        margin=dict(l=60, r=30, t=70, b=50), showlegend=False,
    )
)
pio.templates.default = "clean"

DATA = Path(__file__).resolve().parent / "data"


@st.cache_data
def load(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / f"{name}.csv")


kpi = load("kpi").iloc[0]
MONTH_ORDER = sorted(load("cause_month").ym)
MLABEL = {m: pd.Period(m).strftime("%b %y") for m in MONTH_ORDER}

cm_all = load("carrier_month")
with st.sidebar:
    st.header("Filters")
    classes = st.multiselect(
        "Carrier class", sorted(cm_all.carrier_class.unique()),
        default=sorted(cm_all.carrier_class.unique()),
        help="Applies to the Carriers & seasons tab")
    m_from, m_to = st.select_slider(
        "Months", options=MONTH_ORDER, value=(MONTH_ORDER[0], MONTH_ORDER[-1]),
        format_func=lambda m: MLABEL[m],
        help="Applies to time-based views (carrier heatmaps, daily trend)")
    MONTHS_SEL = [m for m in MONTH_ORDER if m_from <= m <= m_to]

    st.divider()
    st.markdown("**About**")
    st.caption(
        "Every US domestic flight over 12 months, from the official US DOT/BTS "
        "on-time performance records. A flight counts as *delayed* when it arrives "
        "≥15 minutes late (DOT standard).")
    st.caption(f"Data window: {kpi.date_min} → {kpi.date_max} · retrieved Jul 2026")

st.title("🛫 US Flight Delay Risk")
st.caption(
    f"7,027,258 US domestic flights · {kpi.date_min} → {kpi.date_max} · "
    "Source: [US DOT / BTS On-Time Performance](https://www.transtats.bts.gov/) · "
    "delayed = arrival ≥ 15 min late"
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Flights analyzed", f"{int(kpi.flights)/1e6:.1f}M")
c2.metric("Delayed (≥15 min)", f"{kpi.delayed_share:.1%}")
c3.metric("Cancelled", f"{kpi.cancelled_share:.2%}")
c4.metric("Avg delay when late", f"{kpi.mean_delay_when_delayed:.0f} min")

tab_overview, tab_when, tab_where, tab_book = st.tabs(
    ["📊 Carriers & seasons", "⏰ When to fly", "🗺️ Where it hurts", "🎯 Booking playbook"]
)

# ------------------------------------------------------------------ carriers
with tab_overview:
    sel = cm_all[cm_all.carrier_class.isin(classes) & cm_all.ym.isin(MONTHS_SEL)]
    if sel.empty:
        st.warning("Select at least one carrier class and month in the sidebar.")
        st.stop()

    left, right = st.columns([3, 2])
    with left:
        heat = (sel.groupby(["carrier_name", "ym"]).delayed.mean().unstack()[MONTHS_SEL] * 100)
        heat = heat.dropna()
        heat = heat.loc[heat.mean(axis=1).sort_values().index]
        heat.columns = [MLABEL[m] for m in heat.columns]
        fig = px.imshow(heat.round(0), color_continuous_scale="Oranges", aspect="auto",
                        text_auto=".0f", labels=dict(color="% delayed"))
        fig.update_layout(title="<b>Summer is the great equalizer — the gap between carriers narrows</b>"
                          "<br><sup>% delayed by carrier and month · sorted by punctuality</sup>",
                          height=460, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)
    with right:
        yearly = (sel.groupby("carrier_name")
                  .apply(lambda g: (g.delayed * g.flights).sum() / g.flights.sum(),
                         include_groups=False)
                  .sort_values() * 100)
        colors = [GREEN if v == yearly.min() else (ORANGE if v == yearly.max() else LIGHTGREY)
                  for v in yearly]
        fig = go.Figure(go.Bar(x=yearly.values, y=yearly.index, orientation="h",
                               marker_color=colors,
                               text=[f"{v:.0f}%" for v in yearly.values], textposition="outside"))
        fig.update_layout(title="<b>Year-round punctuality gap</b><br><sup>% delayed, full year</sup>",
                          height=460, xaxis=dict(visible=False))
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("Cancellations by carrier and month"):
        cc = load("carrier_cancel")
        heat2 = (cc[cc.carrier_name.isin(sel.carrier_name.unique()) & cc.ym.isin(MONTHS_SEL)]
                 .groupby(["carrier_name", "ym"]).cancelled.mean().unstack()[MONTHS_SEL] * 100)
        heat2 = heat2.dropna()
        heat2 = heat2.loc[heat2.mean(axis=1).sort_values().index]
        heat2.columns = [MLABEL[m] for m in heat2.columns]
        fig = px.imshow(heat2.round(1), color_continuous_scale="Oranges", aspect="auto",
                        text_auto=".1f", labels=dict(color="% cancelled"))
        fig.update_layout(height=420, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------ when
with tab_when:
    left, right = st.columns([3, 2])
    hourly = load("hourly")
    hubs = [h for h in hourly.Origin.unique() if h != "National"]
    with left:
        pick = st.selectbox("Highlight a hub", hubs, index=hubs.index("ORD") if "ORD" in hubs else 0)
        fig = go.Figure()
        for h in hubs:
            s = hourly[hourly.Origin == h]
            fig.add_scatter(x=s.dep_hour, y=s.delayed * 100, mode="lines",
                            line=dict(color=LIGHTGREY, width=1.2),
                            hovertemplate=f"{h}: %{{y:.0f}}%<extra></extra>")
        nat = hourly[hourly.Origin == "National"]
        fig.add_scatter(x=nat.dep_hour, y=nat.delayed * 100, mode="lines",
                        line=dict(color=BLUE, width=3.5), hovertemplate="national: %{y:.0f}%<extra></extra>")
        s = hourly[hourly.Origin == pick]
        fig.add_scatter(x=s.dep_hour, y=s.delayed * 100, mode="lines",
                        line=dict(color=ORANGE, width=3), hovertemplate=f"{pick}: %{{y:.0f}}%<extra></extra>")
        fig.add_annotation(x=s.dep_hour.iloc[-4], y=s.delayed.iloc[-4] * 100, text=f"<b>{pick}</b>",
                           font=dict(color=ORANGE), showarrow=False, yshift=14)
        fig.update_layout(
            title="<b>Delay risk climbs all day — book the morning</b>"
                  "<br><sup>% delayed by scheduled departure hour · grey: 12 busiest hubs · blue: national</sup>",
            xaxis_title="scheduled departure hour", yaxis_title="% delayed", height=470)
        st.plotly_chart(fig, use_container_width=True)
    with right:
        inh = load("hourly_inherited")
        inh["share"] = inh.late_ac / inh.total * 100
        fig = go.Figure()
        fig.add_scatter(x=inh.dep_hour, y=inh.share, mode="lines+markers",
                        line=dict(color=ORANGE, width=3))
        fig.update_layout(
            title="<b>…because delay cascades: evening flights inherit it</b>"
                  "<br><sup>% of delay minutes caused by late-arriving aircraft</sup>",
            xaxis_title="scheduled departure hour", yaxis_title="% inherited", height=470)
        st.plotly_chart(fig, use_container_width=True)

    daily = load("daily")
    daily["FlightDate"] = pd.to_datetime(daily.FlightDate)
    daily = daily[daily.FlightDate.dt.to_period("M").astype(str).isin(MONTHS_SEL)]
    roll = daily.set_index("FlightDate").delayed.rolling(7, center=True).mean() * 100
    fig = go.Figure()
    fig.add_scatter(x=daily.FlightDate, y=daily.delayed * 100, mode="lines",
                    line=dict(color=LIGHTGREY, width=1))
    fig.add_scatter(x=roll.index, y=roll.values, mode="lines", line=dict(color=BLUE, width=3))
    for label, a, b in [("Jul 4", "2025-06-30", "2025-07-07"),
                        ("Thanksgiving", "2025-11-24", "2025-12-01"),
                        ("Christmas/NY", "2025-12-19", "2026-01-04")]:
        if daily.empty or pd.Timestamp(a) > daily.FlightDate.max() or pd.Timestamp(b) < daily.FlightDate.min():
            continue
        fig.add_vrect(x0=a, x1=b, fillcolor=ORANGE, opacity=0.15, line_width=0)
        fig.add_annotation(x=pd.Timestamp(a), y=52, text=f"<b>{label}</b>",
                           font=dict(size=10, color=ORANGE), showarrow=False, xanchor="left")
    fig.update_layout(
        title="<b>Every seasonal peak beats the average — but the worst week was a "
              "March storm, not a holiday</b>"
              "<br><sup>daily % delayed (grey) and 7-day average (blue) · holiday windows shaded</sup>",
        yaxis_title="% delayed", height=380)
    st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------ where
with tab_where:
    left, right = st.columns(2)
    with left:
        stt = load("state")
        fig = px.choropleth(stt, locations="OriginState", locationmode="USA-states", scope="usa",
                            color=stt.delayed * 100, color_continuous_scale="Oranges",
                            labels=dict(color="% delayed"))
        fig.update_layout(title="<b>Northeast corridor, Chicago and Florida are the hotspots</b>"
                          "<br><sup>% delayed by origin state</sup>",
                          height=460, coloraxis_colorbar=dict(len=0.6))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        ap = load("airports")
        min_fl = st.slider("Min flights/year", 50_000, 400_000, 100_000, step=25_000)
        sub = ap[ap.flights >= min_fl]
        fig = px.scatter(sub, x="weather", y="nas", size="flights", size_max=30,
                         color=sub.delayed * 100, color_continuous_scale="Oranges",
                         hover_name="Origin", text="Origin", labels=dict(color="% delayed"))
        fig.update_traces(textposition="top center", textfont=dict(size=9, color=GREY))
        fig.add_vline(x=ap.weather.median(), line=dict(color=LIGHTGREY, dash="dot"))
        fig.add_hline(y=ap.nas.median(), line=dict(color=LIGHTGREY, dash="dot"))
        fig.update_layout(
            title="<b>Two diseases: congestion (top) vs weather (right)</b>"
                  "<br><sup>weather vs airspace delay, min/flight · bubble = volume</sup>",
            xaxis_title="weather delay (min/flight)", yaxis_title="airspace delay (min/flight)",
            height=430)
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------ playbook
with tab_book:
    routes = load("routes")
    combos = load("combos")
    left, right = st.columns([2, 3])
    with left:
        st.markdown("#### Route reliability score")
        st.caption("Composite z-score: delay probability + severity + cancellation + cascade "
                   "exposure. Lower = more reliable. Routes with ≥1,000 flights/yr.")
        n = st.slider("Show top/bottom", 5, 15, 10)
        show = pd.concat([routes.nsmallest(n, "score"), routes.nlargest(n, "score")]).sort_values("score")
        colors = [GREEN] * n + [ORANGE] * n
        fig = go.Figure(go.Bar(x=show.score, y=show.route, orientation="h", marker_color=colors))
        fig.add_vline(x=0, line=dict(color=GREY, width=1))
        fig.update_layout(height=30 * 2 * n + 120,
                          xaxis_title="risk score (lower = better)")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.markdown("#### Best booking on a specific route")
        route = st.selectbox("Route", sorted(combos.route.unique()))
        rc = combos[combos.route == route].sort_values("exp_delay")
        best, worst = rc.iloc[0], rc.iloc[-1]
        st.metric(
            f"Best: {best.carrier_name}, {best.window}",
            f"{best.exp_delay:.0f} min expected delay",
            delta=f"-{worst.exp_delay - best.exp_delay:.0f} min vs worst "
                  f"({worst.carrier_name}, {worst.window})",
            delta_color="inverse")
        fig = px.bar(rc, x="exp_delay", y=rc.carrier_name + " · " + rc.window.astype(str),
                     orientation="h",
                     color=[GREEN if i == rc.index[0] else (ORANGE if i == rc.index[-1] else GREY)
                            for i in rc.index],
                     color_discrete_map="identity",
                     labels=dict(x="expected arrival delay (min)", y=""))
        fig.update_layout(height=max(300, 34 * len(rc) + 100),
                          title=f"<b>{route}: every carrier × departure-window option</b>"
                                "<br><sup>≥200 flights per combination</sup>",
                          yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

st.divider()
st.caption("Data: US DOT/BTS On-Time Performance, Apr 2025 – Mar 2026 · scraped Jul 2026 · "
           "CVD-safe Okabe-Ito palette · Built with Streamlit + Plotly")
