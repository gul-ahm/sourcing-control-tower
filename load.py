from pathlib import Path

import duckdb
import pandas as pd
import yaml

HERE = Path(__file__).parent
RAW = HERE / "data" / "raw"
DB = HERE / "data" / "warehouse.duckdb"

con = duckdb.connect(DB)
con.execute("create schema if not exists raw")

# config.yml is the single source of truth for which countries we track.
cfg = yaml.safe_load((HERE / "config.yml").read_text())
countries = pd.DataFrame(
    [{"country_iso3": k, **v} for k, v in cfg["countries"].items()]
)
con.execute("create or replace table raw.countries as select * from countries")
print(f"raw.countries: {len(countries)} rows")

for csv in sorted(RAW.glob("*.csv")):
    con.execute(f"create or replace table raw.{csv.stem} as select * from read_csv_auto('{csv}')")
    n = con.sql(f"select count(*) from raw.{csv.stem}").fetchone()[0]
    print(f"raw.{csv.stem}: {n} rows")

con.close()
