"""Historical snapshot storage under data/historical/.

Committed JSON was chosen over GitHub Actions artifacts: artifacts expire
(90 days by default) and require extra API calls to read back from a later
run. Small JSON files committed alongside the code are durable, diffable in
git history, and load in a single file read next run. The trade-off is a
slowly growing repo — acceptable at one snapshot/week of a few hundred KB.
"""

import json
import os
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORICAL_DIR = os.path.join(_ROOT, "data", "historical")
SNAPSHOTS_DIR = os.path.join(HISTORICAL_DIR, "snapshots")

RANK_HISTORY_FILE = "rank_history.json"
NEWS_SEEN_FILE = "news_seen.json"
SITEMAP_BASELINE_FILE = "sitemap_last.json"


def _ensure_dirs() -> None:
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)


def load_json(filename: str, default: Any = None) -> Any:
    path = os.path.join(HISTORICAL_DIR, filename)
    if not os.path.exists(path):
        return {} if default is None else default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename: str, data: Any) -> None:
    _ensure_dirs()
    path = os.path.join(HISTORICAL_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def save_run_snapshot(run_date: str, data: dict) -> str:
    _ensure_dirs()
    path = os.path.join(SNAPSHOTS_DIR, f"{run_date}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    return path


def list_run_dates() -> list[str]:
    if not os.path.isdir(SNAPSHOTS_DIR):
        return []
    dates = [f[:-5] for f in os.listdir(SNAPSHOTS_DIR) if f.endswith(".json")]
    return sorted(dates)


def load_run_snapshot(run_date: str) -> dict | None:
    path = os.path.join(SNAPSHOTS_DIR, f"{run_date}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_previous_run_snapshot(before_date: str) -> dict | None:
    """Most recent snapshot strictly before `before_date` (ISO date string)."""
    earlier = [d for d in list_run_dates() if d < before_date]
    if not earlier:
        return None
    return load_run_snapshot(earlier[-1])


def load_rank_history() -> dict:
    return load_json(RANK_HISTORY_FILE, default={})


def save_rank_history(history: dict) -> None:
    save_json(RANK_HISTORY_FILE, history)


def load_news_seen() -> dict:
    return load_json(NEWS_SEEN_FILE, default={})


def save_news_seen(seen: dict) -> None:
    save_json(NEWS_SEEN_FILE, seen)


def load_sitemap_baseline() -> list[str]:
    return load_json(SITEMAP_BASELINE_FILE, default={}).get("urls", [])


def save_sitemap_baseline(urls: list[str]) -> None:
    save_json(SITEMAP_BASELINE_FILE, {"urls": sorted(urls)})
