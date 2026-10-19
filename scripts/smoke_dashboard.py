"""Run the Streamlit app headlessly and fail on any exception it raises.

Catches the class of break a dbt test cannot: a renamed mart column that the
warehouse is perfectly happy with and the dashboard is not.
"""

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

app = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
at = AppTest.from_file(str(app), default_timeout=300).run()

for e in at.exception:
    print(f"dashboard raised: {e.value}", file=sys.stderr)

if at.exception:
    sys.exit(1)

print(f"dashboard ok - {len(at.tabs)} tabs, {len(at.metric)} metrics rendered")
