# Sourcing control tower

![ci](https://github.com/gul-ahm/sourcing-control-tower/actions/workflows/ci.yml/badge.svg)

A pharma buyer runs $650M a year through 48 suppliers across ten countries.
Which lanes are quietly costing them delivery days, how much money sits behind
those lanes, and where could the book move instead?

Three live public feeds supply the external risk picture. A simulated order book
supplies the business grain. dbt turns both into marts, and a Streamlit app
answers the three questions above rather than listing metrics.

## What is real and what is not

| Layer | Source | Real? |
|---|---|---|
| Logistics Performance Index, GDP, imports | World Bank API | real |
| Daily FX vs USD | Frankfurter (ECB reference rates) | real |
| Daily port weather | Open-Meteo archive | real |
| Suppliers, SKUs, purchase orders | generated in `ingest/supply_book.py` | **simulated** |

The buyer does not exist. Everything downstream of the order book is therefore a
simulation, and it is labelled as one in the app's sidebar as well as here.

What makes the simulation worth analysing: the generator reads the **real**
weather extract and lets genuine storms at a supplier's origin port extend that
order's lead time. It does **not** write the storm count to the output. The
warehouse rediscovers the relationship by joining orders back to port weather,
and `mart_lead_time_drivers` fits it:

```
2.25 delivery days lost per anomalous port day   (R² 0.97)
```

The generator injects 2.8. The gap is the point — the percentile-based detector
in `int_port_weather_anomaly` is an imperfect proxy for the storms that actually
caused the delay, so the measured coefficient sits below ground truth. A model
that recovered 2.8 exactly would mean the answer had leaked into the inputs.

## The decisions it supports

**Where is money actually at risk.** "Exposed" is deliberately narrow. Nearly
every long-haul order touches some bad weather, so counting any storm day flags
88% of spend and says nothing. Exposure means an order that slipped more than
seven days late **and** had an anomalous port day in transit — late, with a
cause. That is 18% of recent spend, which is a number worth acting on.

**Why a country scores where it does.** The country score keeps each penalty as
its own column, so the app renders a waterfall from LPI through weather,
currency and delay rather than reporting a single unarguable number.

**What happens if the weights are wrong.** The simulator re-scores the same
components at weights the viewer picks and shows which countries change rank.
Nothing is written back to the warehouse.

**Where the book could move.** `mart_sourcing_alternatives` pairs every bought
SKU with every other supplier that offers it, carrying price delta, OTIF delta
and days saved, so a switch can be argued with numbers.

**What disruption actually costs.** Delay days are not a cost. Air freight paid
to rescue critical lines is, and so is the carrying cost of stock held only
because lead times move. `mart_disruption_cost` prices both: **$6.9M a year,
1.06% of spend**, with China carrying the largest share.

**How much buffer is the supplier's fault.** Safety stock is sized with

```
SS = Z * sqrt( L * sd_demand^2 + demand^2 * sd_lead^2 )
```

The second term is the one most buffers ignore. Across the book **70% of the
$14.9M held in safety stock exists because lead times are unreliable, not
because demand is volatile** — which makes it a supplier problem, not an
inventory problem.

**Where ABC classification stops being a label.** Criticality drives behaviour
in three places: A lines get expedited by air when they start slipping (22% of
A shipments, $1.6M of freight), A items are held to a 99% service level against
C's 90%, and concentration risk is weighted by it. The result is visible in the
book — A items run at 65% OTIF against B's 55%, and they cost more to keep
there.

## Statistical choices

- **Port anomalies are per-port percentiles, not a fixed millimetre cut-off.**
  50mm means something different in Hamburg and Nhava Sheva. Severity is scored
  against each port's own distribution; the 97th percentile is the flag.
- **FX moves are z-scored against each currency's own 60-day volatility.** A 1%
  day is noise for BRL and a shock for EUR.
- **OTIF, p95 delay and a recent-quarter trend** per supplier, because a mean
  delay hides the tail that actually breaks production schedules.
- **SKUs with fewer than 8 receipts get no lead-time statistics at all** rather
  than a standard deviation computed on three observations.
- **Two singular tests guard the analysis itself**, not just the data: one fails
  the build if the storm-to-delay slope goes flat or its R² drops below 0.5, the
  other if any safety stock comes out non-positive. A pipeline that silently
  stops measuring the thing it was built to measure is worse than one that
  breaks.

## Engineering

```bash
make all      # offline data -> warehouse -> every test
make lint     # ruff over python, sqlfluff over the models
make docs     # lineage site into target/
```

- **CI runs the whole thing on every push** — lint, unit tests, a full warehouse
  rebuild, and a headless render of the dashboard. It runs against the offline
  fixtures, so there are no keys to manage and nothing flaky to retry.
- **`fct_purchase_orders` is under an enforced dbt contract.** Every column's
  type is declared, and `on_schema_change: fail` stops an incremental run that
  would quietly drift. Changing a column type fails the build rather than the
  dashboard.
- **The dashboard is a declared dbt exposure**, so
  `dbt ls --select +exposure:sourcing_control_tower` answers "what does this
  chart depend on" from the lineage graph instead of from memory.
- **Python is unit tested, not just the SQL.** The tests assert the invariants
  the generator has to hold — orders never arrive before they are placed, only
  A lines get expedited, orders sit inside the weather window, and the storm
  signal survives into the book. One of them exists because the offline and
  live extracts can silently diverge if someone edits one and not the other.
- **A smoke test renders the dashboard headlessly in CI**, which catches the
  break a dbt test cannot: a renamed mart column the warehouse is happy with and
  the app is not.
- **ruff and sqlfluff are clean, enforced by pre-commit and again in CI.**

## Running it

```bash
pip install -r requirements.txt

python fetch.py                        # live APIs + generated order book
python fetch.py --offline              # generated weather/FX too, no network
python load.py
dbt build --profiles-dir .
streamlit run dashboard/app.py
```

**Regenerating the order book needs `--full-refresh`.** `fct_purchase_orders` is
incremental on `po_id` and only reloads a trailing 60-day window, which is right
for a real book where receipts get corrected after the fact. The generator
recycles PO ids, so without a full refresh the rows outside that window keep
values from the previous run — row counts and uniqueness tests still pass while
the totals are wrong. This cost an hour to find.

## Layout

```
config.yml                countries, ports, currencies
ingest/                   one module per feed + the order book simulator
load.py                   raw CSV -> DuckDB raw schema
models/staging/           typing, pivoting, null handling
models/intermediate/      weather anomalies, FX volatility, PO storm exposure,
                          per-SKU lead-time statistics
models/marts/             facts, dimensions and seven decision marts
models/exposures.yml      the dashboard, declared in the lineage graph
snapshots/                SCD-2 on supplier attributes
tests/                    singular tests on the analytical relationships
tests/unit/               pytest over the ingest layer
scripts/                  headless dashboard smoke test used by CI
dashboard/                Streamlit app + chart theme
```

24 models, 1 snapshot, 56 dbt tests and 8 Python unit tests. Staging and intermediate are views, marts are
tables, orders are incremental, supplier attributes are snapshotted.

## What it does not do

- **Weather is a proxy for disruption, not a measurement of it.** Real berth and
  dwell data would replace the column outright.
- **LPI refreshes every few years**, so the logistics term barely moves within a
  run. FX, weather and delivery performance carry the variation.
- **One port per country.** A country with several deep-water ports is
  represented by its largest, which understates its resilience.
- **Demand is modelled, not observed.** Weekly consumption comes from the
  generator, so the demand-variability half of the safety stock formula is as
  synthetic as the order book. The lead-time half is derived from the simulated
  receipts, which at least carry the real weather signal.
- **Carrying rate is a single assumption (22%/year).** It is a plausible
  mid-range figure for pharma, not a researched one, and it sits in
  `dbt_project.yml` where it can be argued with.
- **The switch analysis ignores qualification cost.** Moving an API supplier in
  pharma means regulatory filings and stability data, which dwarf the price
  delta shown. The view ranks candidates; it does not approve them.
