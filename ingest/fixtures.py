"""Deterministic stand-in for the three APIs, so the warehouse can be built
and tested without network access. Same schemas as the real extracts."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .common import config, write

NAMES = {
    "IND": "India", "CHN": "China", "USA": "United States", "DEU": "Germany",
    "GBR": "United Kingdom", "JPN": "Japan", "BRA": "Brazil", "MEX": "Mexico",
    "ZAF": "South Africa", "THA": "Thailand",
}

# Rough real-world anchors so the generated numbers stay plausible.
LPI = {"IND": 3.4, "CHN": 3.7, "USA": 3.9, "DEU": 4.2, "GBR": 4.0,
       "JPN": 4.0, "BRA": 2.9, "MEX": 3.0, "ZAF": 3.3, "THA": 3.4}
RATE = {"INR": 83.0, "CNY": 7.2, "EUR": 0.92, "GBP": 0.79, "JPY": 150.0,
        "BRL": 5.0, "MXN": 17.5, "ZAR": 18.5, "THB": 35.5, "USD": 1.0}
RAIN = {"IND": 4.5, "CHN": 3.0, "USA": 0.8, "DEU": 2.0, "GBR": 2.2,
        "JPN": 3.5, "BRA": 3.8, "MEX": 2.5, "ZAF": 2.6, "THA": 5.0}


def run(days=365, seed=7):
    rng = np.random.default_rng(seed)
    cfg = config()
    start_year, end_year = cfg["years"]

    wb = []
    for iso3 in cfg["countries"]:
        for year in range(start_year, end_year + 1):
            drift = (year - start_year) * 0.02
            wb += [
                {"country_iso3": iso3, "country_name": NAMES[iso3], "year": year,
                 "metric": "lpi_score", "value": round(LPI[iso3] + drift + rng.normal(0, 0.08), 2)},
                {"country_iso3": iso3, "country_name": NAMES[iso3], "year": year,
                 "metric": "gdp_usd", "value": round(float(rng.uniform(3e11, 1.8e13)), 0)},
                {"country_iso3": iso3, "country_name": NAMES[iso3], "year": year,
                 "metric": "imports_pct_gdp", "value": round(float(rng.uniform(12, 55)), 2)},
            ]
    # The real API returns nulls for years a country has not reported.
    wb = pd.DataFrame(wb)
    gaps = rng.choice(wb.index, size=len(wb) // 25, replace=False)
    wb.loc[gaps, "value"] = np.nan
    write(wb, "worldbank")

    end = date.today()
    days_index = [end - timedelta(days=i) for i in range(days, -1, -1)]
    # Weekdays only, matching ECB publication.
    days_index = [d for d in days_index if d.weekday() < 5]

    fx = []
    for currency, base in RATE.items():
        walk = base * np.cumprod(1 + rng.normal(0, 0.003, len(days_index)))
        for d, rate in zip(days_index, walk, strict=True):
            fx.append({"rate_date": d.isoformat(), "currency": currency,
                       "units_per_usd": 1.0 if currency == "USD" else round(float(rate), 4)})
    write(pd.DataFrame(fx), "fx")

    wx_end = end - timedelta(days=6)
    wx_days = [wx_end - timedelta(days=i) for i in range(days, -1, -1)]
    wx = []
    for iso3, c in cfg["countries"].items():
        for d in wx_days:
            seasonal = 1 + 0.6 * np.sin(2 * np.pi * d.timetuple().tm_yday / 365)
            precip = rng.exponential(RAIN[iso3] * seasonal)
            wind = rng.gamma(9, 2.2)
            # Storms are what actually close a port, so the sample needs them:
            # roughly one disruptive day a month, more in the wet season.
            if rng.random() < 0.05 * seasonal:
                precip *= rng.uniform(8, 20)
                wind *= rng.uniform(2.4, 4.0)
            wx.append({
                "country_iso3": iso3,
                "port": c["port"],
                "obs_date": d.isoformat(),
                "precip_mm": round(float(max(0, precip)), 1),
                "wind_kmh": round(float(max(0, wind)), 1),
            })
    write(pd.DataFrame(wx), "weather")
