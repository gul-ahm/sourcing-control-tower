from datetime import date, timedelta

import pandas as pd

from .common import config, get_json, write


# Frankfurter serves ECB reference rates, so USD is the base and never a symbol.
def run(days=365):
    cfg = config()
    symbols = sorted({c["currency"] for c in cfg["countries"].values()} - {"USD"})
    end = date.today()
    start = end - timedelta(days=days)

    url = (
        f"https://api.frankfurter.dev/v1/{start}..{end}"
        f"?from=USD&to={','.join(symbols)}"
    )
    payload = get_json(url)

    rows = [
        {"rate_date": day, "currency": currency, "units_per_usd": rate}
        for day, rates in payload["rates"].items()
        for currency, rate in rates.items()
    ]
    rows += [{"rate_date": day, "currency": "USD", "units_per_usd": 1.0}
             for day in payload["rates"]]

    write(pd.DataFrame(rows).sort_values(["rate_date", "currency"]), "fx")
