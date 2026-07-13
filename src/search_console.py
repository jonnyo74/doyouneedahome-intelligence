"""Google Search Console access.

Every function here returns plain dicts (never raw API row objects) so the
rest of the codebase — and tests — never need to know the Search Console
API's row/`keys` shape.
"""

import json
import os
from dataclasses import dataclass
from datetime import date, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

from src import config_loader

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


class SearchConsoleAuthError(RuntimeError):
    pass


def get_service():
    """Build an authenticated Search Console API client.

    Reads credentials from GSC_SERVICE_ACCOUNT_JSON (full JSON as a string —
    used in CI) or falls back to the file at GSC_SERVICE_ACCOUNT_FILE
    (defaults to credentials.json — used for local runs).
    """
    raw_json = os.getenv("GSC_SERVICE_ACCOUNT_JSON")
    if raw_json:
        info = json.loads(raw_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds_file = os.getenv("GSC_SERVICE_ACCOUNT_FILE", "credentials.json")
        if not os.path.exists(creds_file):
            raise SearchConsoleAuthError(
                f"No Search Console credentials found. Set GSC_SERVICE_ACCOUNT_JSON "
                f"or place a service-account file at '{creds_file}'."
            )
        creds = service_account.Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    return build("searchconsole", "v1", credentials=creds)


def _site_url() -> str:
    return os.getenv("GSC_SITE_URL") or config_loader.load_site_config()["site"]["search_console_site_url"]


@dataclass(frozen=True)
class Period:
    label: str
    start: str
    end: str


def get_periods() -> dict[str, Period]:
    """Return the four standard comparison windows, all ending on the last
    *complete* day (today minus `complete_through_days_ago`)."""
    cfg = config_loader.load_site_config()["search_console"]
    end = date.today() - timedelta(days=cfg["complete_through_days_ago"])
    short = cfg["short_window_days"]
    long = cfg["long_window_days"]

    last7_start = end - timedelta(days=short - 1)
    prev7_end = last7_start - timedelta(days=1)
    prev7_start = prev7_end - timedelta(days=short - 1)

    last28_start = end - timedelta(days=long - 1)
    prev28_end = last28_start - timedelta(days=1)
    prev28_start = prev28_end - timedelta(days=long - 1)

    return {
        "last7": Period("last7", last7_start.isoformat(), end.isoformat()),
        "prev7": Period("prev7", prev7_start.isoformat(), prev7_end.isoformat()),
        "last28": Period("last28", last28_start.isoformat(), end.isoformat()),
        "prev28": Period("prev28", prev28_start.isoformat(), prev28_end.isoformat()),
    }


def _query(service, site_url: str, start: str, end: str, dimensions: list[str], row_limit: int) -> list[dict]:
    rows: list[dict] = []
    start_row = 0
    page_size = min(row_limit, 25000)
    while True:
        response = (
            service.searchanalytics()
            .query(
                siteUrl=site_url,
                body={
                    "startDate": start,
                    "endDate": end,
                    "dimensions": dimensions,
                    "rowLimit": page_size,
                    "startRow": start_row,
                },
            )
            .execute()
        )
        batch = response.get("rows", [])
        rows.extend(batch)
        if len(batch) < page_size or len(rows) >= row_limit:
            break
        start_row += page_size
    return rows[:row_limit]


def _normalize(rows: list[dict], dimensions: list[str]) -> list[dict]:
    out = []
    for row in rows:
        item = {dim: row["keys"][i] for i, dim in enumerate(dimensions)}
        item["clicks"] = row.get("clicks", 0.0)
        item["impressions"] = row.get("impressions", 0.0)
        item["ctr"] = row.get("ctr", 0.0)
        item["position"] = row.get("position", 0.0)
        out.append(item)
    return out


def get_pages(service, period: Period, site_url: str | None = None, row_limit: int | None = None) -> list[dict]:
    cfg = config_loader.load_site_config()["search_console"]
    rows = _query(service, site_url or _site_url(), period.start, period.end, ["page"], row_limit or cfg["row_limit"])
    return _normalize(rows, ["page"])


def get_queries(service, period: Period, site_url: str | None = None, row_limit: int | None = None) -> list[dict]:
    cfg = config_loader.load_site_config()["search_console"]
    rows = _query(service, site_url or _site_url(), period.start, period.end, ["query"], row_limit or cfg["row_limit"])
    return _normalize(rows, ["query"])


def get_query_pages(service, period: Period, site_url: str | None = None, row_limit: int | None = None) -> list[dict]:
    """Query+page dimensioned rows — used to find the best-ranking page for
    a given money keyword."""
    cfg = config_loader.load_site_config()["search_console"]
    rows = _query(
        service, site_url or _site_url(), period.start, period.end, ["query", "page"], row_limit or cfg["row_limit"]
    )
    return _normalize(rows, ["query", "page"])
