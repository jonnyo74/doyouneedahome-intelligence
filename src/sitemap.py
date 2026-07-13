"""Sitemap / sitemap-index discovery and parsing."""

from urllib.parse import urlparse
from xml.etree import ElementTree

import requests

_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def fetch_sitemap_urls(sitemap_url: str, timeout: int = 10, user_agent: str = "") -> list[str]:
    """Fetch a sitemap, following one level of sitemap-index nesting."""
    headers = {"User-Agent": user_agent} if user_agent else {}
    resp = requests.get(sitemap_url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)

    urls = [loc.text.strip() for loc in root.findall(".//sm:url/sm:loc", _NS) if loc.text]
    if urls:
        return urls

    # sitemap index — fetch each nested sitemap
    nested = [loc.text.strip() for loc in root.findall(".//sm:sitemap/sm:loc", _NS) if loc.text]
    all_urls: list[str] = []
    for nested_url in nested:
        try:
            sub_resp = requests.get(nested_url, headers=headers, timeout=timeout)
            sub_resp.raise_for_status()
            sub_root = ElementTree.fromstring(sub_resp.content)
            all_urls.extend(loc.text.strip() for loc in sub_root.findall(".//sm:url/sm:loc", _NS) if loc.text)
        except requests.RequestException:
            continue
    return all_urls


def find_duplicates(urls: list[str]) -> list[str]:
    seen = set()
    dupes = set()
    for u in urls:
        if u in seen:
            dupes.add(u)
        seen.add(u)
    return sorted(dupes)


def find_invalid_urls(urls: list[str], base_url: str) -> list[str]:
    base_host = urlparse(base_url).netloc
    invalid = []
    for u in urls:
        parsed = urlparse(u)
        if not parsed.scheme or not parsed.netloc:
            invalid.append(u)
        elif parsed.netloc != base_host:
            invalid.append(u)
    return invalid


def diff_urls(current: list[str], baseline: list[str]) -> dict:
    current_set, baseline_set = set(current), set(baseline)
    return {
        "new": sorted(current_set - baseline_set),
        "removed": sorted(baseline_set - current_set),
    }
