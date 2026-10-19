import urllib.error
from io import BytesIO
from unittest.mock import patch

import pandas as pd
import pytest

from ingest import common, fixtures, supply_book

RAW_SCHEMAS = {
    "worldbank": {"country_iso3", "country_name", "year", "metric", "value"},
    "fx": {"rate_date", "currency", "units_per_usd"},
    "weather": {"country_iso3", "port", "obs_date", "precip_mm", "wind_kmh"},
}


@pytest.fixture(scope="module")
def book(tmp_path_factory):
    """Generate one small book and reuse it across the assertions."""
    out = tmp_path_factory.mktemp("raw")
    with patch.object(common, "RAW", out), patch.object(supply_book, "RAW", out):
        fixtures.run(days=240, seed=3)
        supply_book.run(seed=5)
    return {p.stem: pd.read_csv(p) for p in out.glob("*.csv")}


def test_offline_extracts_match_the_live_schemas(book):
    # If someone edits worldbank.py or fx.py without touching fixtures.py, the
    # offline path silently diverges and CI stops testing the real shape.
    for name, columns in RAW_SCHEMAS.items():
        assert set(book[name].columns) == columns, name


def test_orders_never_arrive_before_they_are_placed(book):
    po = book["purchase_orders"]
    assert (pd.to_datetime(po.received_date) >= pd.to_datetime(po.order_date)).all()
    assert (po.qty_units > 0).all()
    assert (po.line_value_usd > 0).all()


def test_only_critical_lines_get_expedited(book):
    po = book["purchase_orders"].merge(book["skus"][["sku_id", "criticality"]], on="sku_id")
    air = po[po.shipped_mode == "Air"]
    assert not air.empty, "expedite path never fired"
    assert set(air.criticality) == {"A"}
    assert (air.expedite_cost_usd > 0).all()
    assert (po[po.shipped_mode == "Ocean"].expedite_cost_usd == 0).all()


def test_orders_sit_inside_the_weather_window(book):
    # Orders outside the weather extract carry no disruption signal at all,
    # which would quietly halve the dataset the analysis runs on.
    po = pd.to_datetime(book["purchase_orders"].order_date)
    wx = pd.to_datetime(book["weather"].obs_date)
    assert po.min() >= wx.min()
    assert po.max() <= wx.max()


def test_storm_signal_survives_into_the_order_book(book):
    po = book["purchase_orders"].merge(
        book["suppliers"][["supplier_id", "country_iso3"]], on="supplier_id")
    for col in ("order_date", "promised_date", "received_date"):
        po[col] = pd.to_datetime(po[col])

    wx = book["weather"].copy()
    wx["obs_date"] = pd.to_datetime(wx.obs_date)
    wx["hit"] = (wx.precip_mm >= 50) | (wx.wind_kmh >= 62)
    storm_days = {
        iso3: set(g.obs_date.dt.date)
        for iso3, g in wx[wx.hit].groupby("country_iso3")
    }

    po["delay"] = (po.received_date - po.promised_date).dt.days
    po["storms"] = [
        sum(1 for k in range((r.promised_date - r.order_date).days)
            if (r.order_date + pd.Timedelta(days=k)).date() in storm_days.get(r.country_iso3, ()))
        for r in po.itertuples()
    ]
    # The whole analysis rests on this. Ocean lines only: expedited A lines are
    # rescued by air freight and deliberately break the relationship.
    ocean = po[po.shipped_mode == "Ocean"]
    assert ocean.storms.corr(ocean.delay) > 0.3


def test_demand_covers_every_sku(book):
    assert set(book["demand"].sku_id) == set(book["skus"].sku_id)
    assert (book["demand"].units_consumed >= 0).all()


def test_get_json_sends_a_user_agent():
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["agent"] = req.get_header("User-agent")
        return _Response(b'{"ok": true}')

    with patch("urllib.request.urlopen", fake_urlopen):
        assert common.get_json("https://example.test/x") == {"ok": True}
    assert captured["agent"] and "urllib" not in captured["agent"].lower()


def test_get_json_names_the_failing_endpoint():
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    with patch("urllib.request.urlopen", fake_urlopen), \
         pytest.raises(RuntimeError, match="403"):
        common.get_json("https://example.test/blocked")


class _Response:
    def __init__(self, payload):
        self._buf = BytesIO(payload)

    def read(self, *a):
        return self._buf.read(*a)

    def __enter__(self):
        return self._buf

    def __exit__(self, *a):
        return False
