import pandas as pd

from .common import config, get_json, write

INDICATORS = {
    "LP.LPI.OVRL.XQ": "lpi_score",
    "NY.GDP.MKTP.CD": "gdp_usd",
    "NE.IMP.GNFS.ZS": "imports_pct_gdp",
}


def run():
    cfg = config()
    codes = ";".join(cfg["countries"])
    start, end = cfg["years"]

    rows = []
    for indicator, label in INDICATORS.items():
        url = (
            f"https://api.worldbank.org/v2/country/{codes}/indicator/{indicator}"
            f"?format=json&per_page=5000&date={start}:{end}"
        )
        payload = get_json(url)
        if len(payload) < 2 or not payload[1]:
            raise RuntimeError(f"no data returned for {indicator}")

        for item in payload[1]:
            rows.append(
                {
                    "country_iso3": item["countryiso3code"],
                    "country_name": item["country"]["value"],
                    "year": int(item["date"]),
                    "metric": label,
                    "value": item["value"],
                }
            )

    write(pd.DataFrame(rows), "worldbank")
