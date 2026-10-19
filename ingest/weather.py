from datetime import date, timedelta

import pandas as pd

from .common import config, get_json, write


def run(days=365):
    cfg = config()
    # The archive endpoint lags live weather by about five days.
    end = date.today() - timedelta(days=6)
    start = end - timedelta(days=days)

    frames = []
    for iso3, c in cfg["countries"].items():
        url = (
            "https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={c['lat']}&longitude={c['lon']}"
            f"&start_date={start}&end_date={end}"
            "&daily=precipitation_sum,wind_speed_10m_max&timezone=UTC"
        )
        daily = get_json(url)["daily"]
        frames.append(
            pd.DataFrame(
                {
                    "country_iso3": iso3,
                    "port": c["port"],
                    "obs_date": daily["time"],
                    "precip_mm": daily["precipitation_sum"],
                    "wind_kmh": daily["wind_speed_10m_max"],
                }
            )
        )

    write(pd.concat(frames, ignore_index=True), "weather")
