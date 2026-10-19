import json
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"


def config():
    return yaml.safe_load((ROOT / "config.yml").read_text())


def get_json(url, retries=3):
    # Some of these hosts sit behind Cloudflare and reject the default
    # Python-urllib agent with a 403.
    req = urllib.request.Request(url, headers={"User-Agent": "sourcing-risk/1.0"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{e.code} from {url}") from e
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
    raise RuntimeError("unreachable")


def write(df, name):
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"{name}.csv"
    df.to_csv(path, index=False)
    shown = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    print(f"{name}: {len(df)} rows -> {shown}")
