from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st
import theme

DB = Path(__file__).resolve().parents[1] / "data" / "warehouse.duckdb"

st.set_page_config(page_title="Sourcing control tower", layout="wide",
                   initial_sidebar_state="expanded")


@st.cache_data(ttl=300)
def q(sql):
    con = duckdb.connect(DB, read_only=True)
    try:
        return con.sql(sql).df()
    finally:
        con.close()


if not DB.exists():
    st.error(
        "No warehouse found. Run `python fetch.py --offline && python load.py "
        "&& dbt build --profiles-dir .`"
    )
    st.stop()

orders = q("select * from main_marts.fct_purchase_orders")
country = q("select * from main_marts.mart_sourcing_scorecard")
suppliers = q("select * from main_marts.mart_supplier_scorecard")
risk = q("select * from main_marts.mart_spend_at_risk")
drivers = q("select * from main_marts.mart_lead_time_drivers")

with st.sidebar:
    st.markdown("### Filters")
    categories = st.multiselect("Category", sorted(orders.category.unique()),
                                default=list(sorted(orders.category.unique())))
    crits = st.multiselect("Criticality", ["A", "B", "C"], default=["A", "B", "C"])
    st.caption(
        "External risk feeds are live (World Bank, ECB via Frankfurter, Open-Meteo). "
        "The supplier book is simulated — see the README."
    )

book = orders[orders.category.isin(categories) & orders.criticality.isin(crits)]
if book.empty:
    st.warning("No orders match those filters.")
    st.stop()

cutoff = book.order_date.max() - pd.Timedelta(days=90)
recent = book[book.order_date >= cutoff]

st.title("Sourcing control tower")
st.caption(f"Order book through {book.order_date.max():%d %b %Y} · "
           f"{len(book):,} purchase orders · {book.supplier_id.nunique()} suppliers")

# Late past tolerance with a weather cause — not merely "touched bad weather".
exposed = recent.loc[(recent.storm_days > 0) & (recent.delay_days > 7), "line_value_usd"].sum()
otif = 100 * (~recent.is_late).mean()
per_storm = float(drivers.days_lost_per_storm_day.iloc[0])
days_lost = recent.storm_days.sum() * per_storm
deteriorating = int((suppliers.trend_flag == "deteriorating").sum())

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Spend, last 90 days", f"${recent.line_value_usd.sum()/1e6:,.0f}M")
k2.metric("Spend late on weather", f"${exposed/1e6:,.0f}M",
          f"{100*exposed/recent.line_value_usd.sum():.0f}% of spend", delta_color="inverse")
k3.metric("OTIF", f"{otif:.0f}%")
k4.metric("Est. delivery days lost", f"{days_lost:,.0f}", f"{per_storm:.2f} d per storm day")
k5.metric("Suppliers deteriorating", deteriorating, delta_color="inverse")

tabs = st.tabs(["Exposure", "What drives delay", "Inventory risk",
                "Cost of disruption", "Weight simulator", "Suppliers",
                "Switch analysis"])

# ---------------------------------------------------------------- exposure
with tabs[0]:
    lanes = (recent.groupby(["country_iso3", "category"], as_index=False)
             .agg(spend=("line_value_usd", "sum"),
                  exposed=("line_value_usd", lambda s: s[
                      (recent.loc[s.index, "storm_days"] > 0)
                      & (recent.loc[s.index, "delay_days"] > 7)].sum()),
                  orders=("po_id", "size")))
    lanes["exposed_pct"] = (100 * lanes.exposed / lanes.spend).round(1)

    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Spend running materially late with a weather cause, by lane**")
        st.altair_chart(
            alt.Chart(lanes).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4,
                                      stroke=theme.SURFACE, strokeWidth=2)
            .encode(
                x=alt.X("exposed:Q", title="Exposed spend (USD)", axis=alt.Axis(format="$~s")),
                y=alt.Y("country_iso3:N", sort="-x", title=None),
                color=alt.Color("category:N", title="Category",
                                scale=alt.Scale(range=theme.SERIES)),
                tooltip=[alt.Tooltip("country_iso3", title="Country"),
                         alt.Tooltip("category"),
                         alt.Tooltip("orders", format=","),
                         alt.Tooltip("spend", format="$,.0f"),
                         alt.Tooltip("exposed", format="$,.0f"),
                         alt.Tooltip("exposed_pct", title="Exposed %")],
            ).properties(height=340),
            width="stretch",
        )
    with right:
        st.markdown("**Share of lane spend exposed**")
        st.dataframe(
            lanes.sort_values("exposed", ascending=False)
            .assign(spend=lambda d: d.spend.map("${:,.0f}".format),
                    exposed=lambda d: d.exposed.map("${:,.0f}".format))
            [["country_iso3", "category", "orders", "spend", "exposed", "exposed_pct"]],
            hide_index=True, width="stretch", height=340,
        )

    st.markdown("**Disrupted port days by month**")
    wx = q("select port, obs_date, is_disrupted from main_marts.fct_port_weather")
    wx["month"] = pd.to_datetime(wx.obs_date).dt.to_period("M").dt.to_timestamp()
    monthly = wx.groupby(["port", "month"], as_index=False).is_disrupted.sum()
    st.altair_chart(
        alt.Chart(monthly).mark_rect(stroke=theme.SURFACE, strokeWidth=2)
        .encode(
            x=alt.X("yearmonth(month):O", title=None),
            y=alt.Y("port:N", title=None,
                    sort=alt.EncodingSortField("is_disrupted", op="sum", order="descending")),
            color=alt.Color("is_disrupted:Q", title="Disrupted days",
                            scale=alt.Scale(range=theme.SEQ_BLUE)),
            tooltip=["port", alt.Tooltip("yearmonth(month):O", title="Month"),
                     alt.Tooltip("is_disrupted:Q", title="Disrupted days")],
        ).properties(height=280),
        width="stretch",
    )

# ---------------------------------------------------------------- drivers
with tabs[1]:
    st.markdown("**Delay against storm exposure**")
    st.caption(
        "Nothing upstream records storm days — orders are joined back to port weather "
        f"to derive them. Fitted slope {per_storm:.2f} days lost per anomalous port day "
        f"(R² {drivers.model_r2.iloc[0]:.3f})."
    )

    base = alt.Chart(drivers).encode(
        x=alt.X("storm_days:Q", title="Anomalous port days in transit"))
    points = base.mark_circle(size=140, color=theme.SERIES[0]).encode(
        y=alt.Y("mean_delay_days:Q", title="Mean delay vs promise (days)"),
        size=alt.Size("orders:Q", title="Orders", scale=alt.Scale(range=[80, 600])),
        tooltip=["storm_days", alt.Tooltip("orders", format=","),
                 "mean_delay_days", "delay_vs_clean_transit"],
    )
    fit = base.transform_regression("storm_days", "mean_delay_days").mark_line(
        color=theme.SERIES[1], strokeDash=[6, 4], size=2).encode(y="mean_delay_days:Q")
    st.altair_chart((points + fit).properties(height=320), width="stretch")

    st.divider()
    st.markdown("**Why each country scores where it does**")
    pick = st.selectbox("Country", country.country_iso3.tolist(),
                        format_func=lambda c: country.set_index("country_iso3").country_name[c])
    row = country.set_index("country_iso3").loc[pick]

    steps = [
        ("Logistics index (LPI)", row.lpi_score, "start"),
        ("Port disruption", -row.weather_penalty, "penalty"),
        ("Currency move", -row.currency_penalty, "penalty"),
        ("Delivery delay", -row.delay_penalty, "penalty"),
    ]
    wf, running = [], 0.0
    for label, value, kind in steps:
        wf.append({"step": label, "start": running, "end": running + value,
                   "value": value, "kind": kind})
        running += value
    wf.append({"step": "Sourcing score", "start": 0, "end": running,
               "value": running, "kind": "total"})
    wf = pd.DataFrame(wf)

    st.altair_chart(
        alt.Chart(wf).mark_bar(cornerRadius=4, stroke=theme.SURFACE, strokeWidth=2).encode(
            x=alt.X("step:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("start:Q", title="Score contribution"),
            y2="end:Q",
            color=alt.Color("kind:N", legend=None, scale=alt.Scale(
                domain=["start", "penalty", "total"],
                range=[theme.SERIES[0], theme.CRITICAL, theme.GOOD])),
            tooltip=["step", alt.Tooltip("value:Q", format=".3f")],
        ).properties(height=300)
        + alt.Chart(wf).mark_text(dy=-8, color=theme.INK, fontSize=11).encode(
            x=alt.X("step:N", sort=None), y="end:Q",
            text=alt.Text("value:Q", format=".2f")),
        width="stretch",
    )

# ------------------------------------------------------------- inventory risk
with tabs[2]:
    ss = q("select * from main_marts.mart_safety_stock")
    ss = ss[ss.category.isin(categories) & ss.criticality.isin(crits)]
    if ss.empty:
        st.info("No SKUs match those filters.")
    else:
        a, b, c = st.columns(3)
        a.metric("Safety stock tied up", f"${ss.safety_stock_value_usd.sum()/1e6:,.1f}M")
        a.caption("Sized to the service level each ABC class is held to")
        share = (ss.safety_stock_value_usd * ss.pct_buffer_from_lead_time / 100).sum()
        b.metric("Held because lead times move", f"${share/1e6:,.1f}M",
                 f"{100*share/ss.safety_stock_value_usd.sum():.0f}% of the buffer",
                 delta_color="inverse")
        c.metric("SKUs with enough receipts to model", f"{len(ss)}")

        st.caption(
            "SS = Z × √(L·σ²demand + demand²·σ²lead). The second term is the one most "
            "buffers ignore — an unreliable lead time drives more stock than volatile demand."
        )

        st.markdown("**Which SKUs are buffered against the supplier, not the market**")
        st.altair_chart(
            alt.Chart(ss).mark_circle(opacity=0.8, stroke=theme.SURFACE, strokeWidth=2).encode(
                x=alt.X("lead_weeks_sd:Q", title="Lead-time variability (weeks, σ)"),
                y=alt.Y("safety_stock_value_usd:Q", title="Safety stock value (USD)",
                        axis=alt.Axis(format="$~s")),
                size=alt.Size("weekly_demand:Q", title="Weekly demand",
                              scale=alt.Scale(range=[50, 600])),
                color=alt.Color("criticality:N", title="Criticality",
                                scale=alt.Scale(domain=["A", "B", "C"], range=theme.SERIES)),
                tooltip=["sku_id", "category", "criticality",
                         alt.Tooltip("weekly_demand", format=",.0f"),
                         alt.Tooltip("lead_weeks_mean", format=".2f"),
                         alt.Tooltip("lead_weeks_sd", format=".2f"),
                         alt.Tooltip("safety_stock_units", format=",.0f"),
                         alt.Tooltip("safety_stock_value_usd", format="$,.0f"),
                         alt.Tooltip("pct_buffer_from_lead_time", title="% from lead time")],
            ).properties(height=360),
            width="stretch",
        )

        st.divider()
        st.markdown("**Single-source critical items behind disrupted ports**")
        sr = q("select * from main_marts.mart_single_source_risk")
        sr = sr[sr.category.isin(categories) & sr.criticality.isin(crits)]
        only_single = st.toggle("Only SKUs with one qualified supplier", value=True)
        if only_single:
            sr = sr[sr.qualified_suppliers == 1]
        st.dataframe(
            sr[["sku_id", "category", "criticality", "primary_supplier", "country_iso3",
                "port", "qualified_suppliers", "spend_usd", "port_disruption_rate_pct",
                "safety_stock_value_usd", "expedite_cost_usd",
                "concentration_risk_score"]].head(50),
            hide_index=True, width="stretch", height=340,
        )

# ---------------------------------------------------------- disruption cost
with tabs[3]:
    dc = q("select * from main_marts.mart_disruption_cost")
    a, b, c = st.columns(3)
    a.metric("Air freight paid", f"${dc.expedite_cost_usd.sum()/1e3:,.0f}K")
    b.metric("Annual carrying cost of the delay buffer",
             f"${dc.annual_carrying_cost_usd.sum()/1e6:,.2f}M")
    c.metric("Total cost of disruption",
             f"${dc.total_disruption_cost_usd.sum()/1e6:,.2f}M",
             f"{100*dc.total_disruption_cost_usd.sum()/dc.spend_usd.sum():.2f}% of spend",
             delta_color="inverse")

    st.caption(
        "Delay days are not a cost. These two are: air freight actually paid to rescue "
        "critical lines, and the carrying cost of stock held only because lead times move."
    )

    melted = dc.melt(id_vars=["country_iso3", "port", "spend_usd"],
                     value_vars=["expedite_cost_usd", "annual_carrying_cost_usd"],
                     var_name="component", value_name="cost_usd")
    melted["component"] = melted.component.map({
        "expedite_cost_usd": "Air freight",
        "annual_carrying_cost_usd": "Buffer carrying cost"})

    st.altair_chart(
        alt.Chart(melted).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4,
                                   stroke=theme.SURFACE, strokeWidth=2).encode(
            x=alt.X("cost_usd:Q", title="Cost (USD)", axis=alt.Axis(format="$~s")),
            y=alt.Y("country_iso3:N", sort="-x", title=None),
            color=alt.Color("component:N", title="Component",
                            scale=alt.Scale(range=theme.SERIES[:2])),
            tooltip=["country_iso3", "port", "component",
                     alt.Tooltip("cost_usd", format="$,.0f"),
                     alt.Tooltip("spend_usd", format="$,.0f")],
        ).properties(height=340),
        width="stretch",
    )
    st.dataframe(
        dc[["country_iso3", "port", "orders", "spend_usd", "air_shipments",
            "expedite_cost_usd", "annual_carrying_cost_usd",
            "total_disruption_cost_usd", "cost_pct_of_spend", "mean_delay_days"]],
        hide_index=True, width="stretch",
    )


# ---------------------------------------------------------------- simulator
with tabs[4]:
    st.markdown("**Reweight the score and watch the ranking move**")
    st.caption("Baseline weights are the ones the mart ships with. Changing them here "
               "does not touch the warehouse — it re-scores the same components.")

    c1, c2, c3 = st.columns(3)
    w_weather = c1.slider("Port disruption weight", 0.0, 6.0, 2.0, 0.1)
    w_fx = c2.slider("Currency weight", 0.0, 0.2, 0.02, 0.005)
    w_delay = c3.slider("Delivery delay weight", 0.0, 0.2, 0.04, 0.005)

    sim = country.copy()
    sim["baseline_rank"] = sim.sourcing_score.rank(ascending=False).astype(int)
    sim["new_score"] = (
        sim.lpi_score
        - w_weather * sim.disruption_rate_pct.fillna(0) / 100
        - w_fx * sim.currency_move_30d.fillna(0).abs()
        - w_delay * sim.mean_delay_days.fillna(0).clip(lower=0)
    ).round(3)
    sim["new_rank"] = sim.new_score.rank(ascending=False).astype(int)
    sim["rank_change"] = sim.baseline_rank - sim.new_rank

    moved = sim[sim.rank_change != 0]
    if moved.empty:
        st.info("No rank changes at these weights.")
    else:
        st.success(
            "Ranking changes for: "
            + ", ".join(f"{r.country_name} {r.baseline_rank}→{r.new_rank}"
                        for r in moved.sort_values("new_rank").itertuples())
        )

    st.altair_chart(
        alt.Chart(sim).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4,
                                stroke=theme.SURFACE, strokeWidth=2).encode(
            x=alt.X("new_score:Q", title="Re-weighted score"),
            y=alt.Y("country_name:N", sort="-x", title=None),
            color=alt.Color("rank_change:Q", title="Rank change",
                            scale=alt.Scale(scheme="blueorange", domainMid=0)),
            tooltip=["country_name", "baseline_rank", "new_rank",
                     alt.Tooltip("new_score", format=".3f"),
                     alt.Tooltip("disruption_rate_pct", format=".1f"),
                     alt.Tooltip("currency_move_30d", format=".2f"),
                     alt.Tooltip("mean_delay_days", format=".1f")],
        ).properties(height=340),
        width="stretch",
    )
    st.dataframe(
        sim[["country_name", "port", "lpi_score", "disruption_rate_pct",
             "currency_move_30d", "mean_delay_days", "sourcing_score",
             "new_score", "baseline_rank", "new_rank"]].sort_values("new_rank"),
        hide_index=True, width="stretch",
    )

# ---------------------------------------------------------------- suppliers
with tabs[5]:
    only_bad = st.toggle("Only suppliers running late or deteriorating", value=False)
    view = suppliers.copy()
    if only_bad:
        view = view[(view.trend_flag == "deteriorating") | (view.otif_pct < 50)]

    st.markdown("**Service level against spend**")
    st.altair_chart(
        alt.Chart(view).mark_circle(opacity=0.85, stroke=theme.SURFACE, strokeWidth=2).encode(
            x=alt.X("spend_usd:Q", title="Spend (USD)", axis=alt.Axis(format="$~s")),
            y=alt.Y("otif_pct:Q", title="OTIF %"),
            size=alt.Size("critical_spend_usd:Q", title="Critical spend",
                          scale=alt.Scale(range=[60, 700])),
            color=alt.Color("trend_flag:N", title="Trend",
                            scale=alt.Scale(domain=list(theme.TREND_COLORS),
                                            range=list(theme.TREND_COLORS.values()))),
            tooltip=["supplier_name", "country_iso3", "tier",
                     alt.Tooltip("orders", format=","),
                     alt.Tooltip("spend_usd", format="$,.0f"),
                     alt.Tooltip("otif_pct", format=".1f"),
                     alt.Tooltip("mean_delay_days", format=".1f"),
                     alt.Tooltip("p95_delay_days", format=".1f"),
                     alt.Tooltip("delay_trend_days", format=".1f"), "trend_flag"],
        ).properties(height=380),
        width="stretch",
    )
    st.dataframe(
        view.sort_values("spend_usd", ascending=False)[
            ["supplier_name", "country_iso3", "tier", "orders", "spend_usd",
             "critical_spend_usd", "otif_pct", "mean_delay_days", "p95_delay_days",
             "delay_trend_days", "trend_flag"]],
        hide_index=True, width="stretch", height=360,
    )

# ---------------------------------------------------------------- switch
with tabs[6]:
    st.markdown("**Where could this book move, and what would it cost?**")
    alts = q("select * from main_marts.mart_sourcing_alternatives")

    c1, c2 = st.columns(2)
    min_otif = c1.slider("Minimum OTIF improvement (points)", 0, 60, 15)
    max_price = c2.slider("Maximum price increase (%)", -30, 30, 5)

    shortlist = alts[(alts.otif_delta_pts >= min_otif) & (alts.price_delta_pct <= max_price)]
    if shortlist.empty:
        st.info("Nothing clears those thresholds. Loosen one of them.")
    else:
        total_impact = shortlist.groupby("sku_id").price_impact_usd.min().sum()
        a, b = st.columns(2)
        a.metric("SKUs with a viable alternative", shortlist.sku_id.nunique())
        b.metric("Price impact if all moved", f"${total_impact/1e6:,.1f}M",
                 "negative is a saving", delta_color="off")

        st.altair_chart(
            alt.Chart(shortlist.nlargest(20, "sku_spend_usd"))
            .mark_circle(opacity=0.85, stroke=theme.SURFACE, strokeWidth=2)
            .encode(
                x=alt.X("price_delta_pct:Q", title="Price change on switch (%)"),
                y=alt.Y("otif_delta_pts:Q", title="OTIF gain (points)"),
                size=alt.Size("sku_spend_usd:Q", title="SKU spend",
                              scale=alt.Scale(range=[80, 800])),
                color=alt.Color("category:N", title="Category",
                                scale=alt.Scale(range=theme.SERIES)),
                tooltip=["sku_id", "category", "criticality", "from_supplier",
                         "from_country", "to_supplier", "to_country",
                         alt.Tooltip("sku_spend_usd", format="$,.0f"),
                         alt.Tooltip("price_delta_pct", format=".1f"),
                         alt.Tooltip("otif_delta_pts", format=".1f"),
                         alt.Tooltip("delay_saved_days", format=".1f"),
                         alt.Tooltip("price_impact_usd", format="$,.0f")],
            ).properties(height=360),
            width="stretch",
        )
        st.dataframe(
            shortlist.sort_values("sku_spend_usd", ascending=False)[
                ["sku_id", "category", "criticality", "from_supplier", "from_country",
                 "to_supplier", "to_country", "sku_spend_usd", "price_delta_pct",
                 "otif_delta_pts", "delay_saved_days", "price_impact_usd"]].head(40),
            hide_index=True, width="stretch", height=360,
        )
