"""Generates the supplier book: suppliers, SKUs, and two years of purchase
orders for a mid-size pharma buyer.

This layer is simulated — the buyer does not exist. The external risk feeds
(World Bank, FX, weather) are real, and the simulation reads the real weather
extract so that port disruption genuinely moves lead times. That relationship
is injected here and measured independently in the dbt models, which is the
point: the marts discover the effect rather than assert it.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .common import RAW, config, write

CATEGORIES = {
    "API": (180, 2400, 0.35),
    "Excipient": (12, 180, 0.20),
    "Primary packaging": (4, 60, 0.18),
    "Cold chain device": (300, 5200, 0.12),
    "Lab reagent": (40, 700, 0.15),
}

# Base ocean transit in days from each country to the buyer's EU distribution hub.
TRANSIT = {"IND": 24, "CHN": 30, "USA": 18, "DEU": 3, "GBR": 4,
           "JPN": 32, "BRA": 21, "MEX": 26, "ZAF": 19, "THA": 29}

SUFFIX = ["Pharma", "Life Sciences", "BioChem", "Labs", "Healthcare",
          "Sciences", "Biotech", "Chemworks", "Medisys", "Formulations"]
PREFIX = ["Arcadia", "Benton", "Caldera", "Dovetail", "Everline", "Fairmont",
          "Granite", "Halcyon", "Ironwood", "Juniper", "Kestrel", "Lantern",
          "Meridian", "Northvale", "Oakridge", "Pinnacle", "Quarry", "Redwood",
          "Summit", "Thornfield", "Umbra", "Vantage", "Westbrook", "Yarrow"]


def _suppliers(rng, cfg):
    rows = []
    iso3s = list(cfg["countries"])
    # China and India carry more of the book, as they do in real pharma sourcing.
    weights = np.array([3.0 if c in ("CHN", "IND") else 1.0 for c in iso3s])
    weights = weights / weights.sum()

    for i in range(48):
        iso3 = rng.choice(iso3s, p=weights)
        name = f"{PREFIX[i % len(PREFIX)]} {SUFFIX[rng.integers(len(SUFFIX))]}"
        rows.append({
            "supplier_id": f"SUP{i + 1:03d}",
            "supplier_name": name,
            "country_iso3": iso3,
            "tier": int(rng.choice([1, 2], p=[0.35, 0.65])),
            "onboarded_on": (date(2019, 1, 1)
                             + timedelta(days=int(rng.integers(0, 2000)))).isoformat(),
            "quality_rating": round(float(np.clip(rng.normal(3.9, 0.5), 2.0, 5.0)), 2),
            "payment_terms_days": int(rng.choice([30, 45, 60, 90], p=[0.2, 0.4, 0.3, 0.1])),
            "incoterm": str(rng.choice(["FOB", "CIF", "EXW"], p=[0.5, 0.35, 0.15])),
        })
    return pd.DataFrame(rows)


def _skus(rng):
    rows = []
    for i in range(240):
        category = str(rng.choice(list(CATEGORIES)))
        lo, hi, _ = CATEGORIES[category]
        # Criticality drives how much a late delivery actually hurts.
        criticality = str(rng.choice(["A", "B", "C"], p=[0.2, 0.45, 0.35]))
        rows.append({
            "sku_id": f"SKU{i + 1:04d}",
            "sku_name": f"{category} grade {rng.integers(100, 999)}",
            "category": category,
            "criticality": criticality,
            "unit_cost_usd": round(float(rng.uniform(lo, hi)), 2),
            "shelf_life_days": int(rng.choice([180, 365, 540, 730, 1095])),
        })
    return pd.DataFrame(rows)


def _disrupted_days():
    """Port-days from the weather extract that cleared the storm thresholds,
    plus the window the extract actually covers."""
    wx = pd.read_csv(RAW / "weather.csv", parse_dates=["obs_date"])
    wx["is_disrupted"] = (wx.precip_mm >= 50) | (wx.wind_kmh >= 62)
    hit = wx[wx.is_disrupted]
    days = {iso3: set(g.obs_date.dt.date) for iso3, g in hit.groupby("country_iso3")}
    return days, wx.obs_date.min().date(), wx.obs_date.max().date()


def run(seed=11):
    rng = np.random.default_rng(seed)
    cfg = config()

    suppliers = _suppliers(rng, cfg)
    skus = _skus(rng)
    write(suppliers, "suppliers")
    write(skus, "skus")

    # Each supplier carries a slice of the catalogue.
    catalogue = []
    for s in suppliers.itertuples():
        picks = rng.choice(skus.sku_id.values, size=int(rng.integers(4, 14)), replace=False)
        for sku_id in picks:
            base = skus.loc[skus.sku_id == sku_id, "unit_cost_usd"].iloc[0]
            price = float(base * rng.uniform(0.88, 1.22))
            # Expensive items move in small lots; cheap consumables in pallets.
            if price > 1000:
                moq = int(rng.choice([1, 2, 5]))
            elif price > 100:
                moq = int(rng.choice([10, 25, 50]))
            else:
                moq = int(rng.choice([100, 250, 500]))
            catalogue.append({
                "supplier_id": s.supplier_id,
                "sku_id": sku_id,
                "contract_price_usd": round(price, 2),
                "moq_units": moq,
                "promised_lead_days": TRANSIT[s.country_iso3] + int(rng.integers(5, 22)),
            })
    catalogue = pd.DataFrame(catalogue)
    write(catalogue, "supplier_catalogue")

    sku_criticality = dict(zip(skus.sku_id, skus.criticality, strict=True))
    disrupted, wx_start, wx_end = _disrupted_days()
    supplier_country = dict(zip(suppliers.supplier_id, suppliers.country_iso3, strict=True))

    # Some suppliers quietly degrade over the two years, others improve.
    drift = {s: float(rng.normal(0, 0.9)) for s in suppliers.supplier_id}

    # Orders only span the window the weather extract covers, otherwise half
    # the book would carry no disruption signal at all.
    start, end = wx_start, wx_end
    span = (end - start).days

    orders = []
    for i in range(9000):
        row = catalogue.iloc[int(rng.integers(len(catalogue)))]
        supplier_id = row.supplier_id
        iso3 = supplier_country[supplier_id]
        order_date = start + timedelta(days=int(rng.integers(0, span - 60)))
        promised = int(row.promised_lead_days)
        promised_date = order_date + timedelta(days=promised)

        # Lead time = promise + supplier drift over time + seasonal congestion
        # + the cost of storms that hit the port while the order was in transit.
        # The storm term is deliberately not written to the output: the marts
        # rediscover it by joining orders back to the weather fact.
        months_in = (order_date - start).days / 30.0
        drift_days = drift[supplier_id] * months_in / max(span / 30.0, 1) * 4
        seasonal = 2.5 * np.sin(2 * np.pi * (order_date.timetuple().tm_yday - 40) / 365)
        storms = sum(
            1 for d in (order_date + timedelta(days=k) for k in range(promised))
            if d in disrupted.get(iso3, ())
        )
        noise = rng.normal(0, 3.2)
        # Suppliers quote with a buffer, so a clean lane normally lands early.
        actual = max(3, promised - 4 + drift_days + seasonal + 2.8 * storms + noise)

        # A critical line that is slipping gets pulled forward by air freight.
        # It recovers most of the delay and costs a multiple of ocean rate.
        criticality = sku_criticality[row.sku_id]
        expedited = criticality == "A" and actual > promised + 3 and rng.random() < 0.7
        if expedited:
            actual = max(3, promised + 1 + rng.normal(0, 1.5))

        # Order sizes are driven by what a line is worth, not by a flat
        # multiplier, so a $4 excipient and a $5k cold-chain unit do not end up
        # on the same order value.
        target_value = float(rng.lognormal(mean=10.9, sigma=0.75))
        lots = max(1, round(target_value / (row.contract_price_usd * row.moq_units)))
        qty = int(row.moq_units * lots)
        line_value = qty * row.contract_price_usd
        # Air freight on a rescued line runs 4-6x the ocean rate it replaced.
        expedite_cost = round(line_value * rng.uniform(0.04, 0.09), 2) if expedited else 0.0
        orders.append({
            "po_id": f"PO{i + 1:06d}",
            "supplier_id": supplier_id,
            "sku_id": row.sku_id,
            "order_date": order_date.isoformat(),
            "promised_date": promised_date.isoformat(),
            "received_date": (order_date + timedelta(days=round(actual))).isoformat(),
            "qty_units": qty,
            "unit_price_usd": round(float(row.contract_price_usd * rng.uniform(0.97, 1.06)), 2),
            "shipped_mode": "Air" if expedited else "Ocean",
            "expedite_cost_usd": expedite_cost,
        })

    orders = pd.DataFrame(orders)
    orders["line_value_usd"] = (orders.qty_units * orders.unit_price_usd).round(2)
    write(orders, "purchase_orders")

    # Weekly consumption per SKU. Safety stock needs demand variability as well
    # as lead-time variability, so this carries its own noise and seasonality.
    weeks = pd.date_range(start, end, freq="W-MON")
    demand = []
    for sku in skus.itertuples():
        # Base rate scales inversely with unit cost: cheap consumables move fast.
        base = max(2.0, 4000.0 / (sku.unit_cost_usd ** 0.65))
        volatility = {"A": 0.18, "B": 0.28, "C": 0.40}[sku.criticality]
        for w in weeks:
            seasonal = 1 + 0.15 * np.sin(2 * np.pi * w.dayofyear / 365)
            units = max(0, rng.normal(base * seasonal, base * volatility))
            demand.append({
                "sku_id": sku.sku_id,
                "week_start": w.date().isoformat(),
                "units_consumed": int(round(units)),
            })
    write(pd.DataFrame(demand), "demand")
