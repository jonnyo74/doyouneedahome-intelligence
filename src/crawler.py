"""Respectful crawl of sitemap URLs + site-health aggregation.

Never treats sitemap presence or a 200 status as "indexed" — that claim
requires real indexing data, which this system does not have.
"""

import time
from collections import Counter
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


def crawl(
    urls: list[str],
    user_agent: str,
    requests_per_second: float = 1.5,
    timeout: int = 10,
    max_pages: int = 450,
) -> list[dict]:
    headers = {"User-Agent": user_agent}
    delay = 1.0 / requests_per_second if requests_per_second > 0 else 0
    results = []

    for url in urls[:max_pages]:
        result = {"url": url, "status": None, "error": None}
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            result["status"] = resp.status_code
            result["redirect_chain"] = [r.url for r in resp.history]
            result["final_url"] = resp.url

            if resp.status_code < 400 and "text/html" in resp.headers.get("Content-Type", ""):
                result.update(_parse_html(resp.text, url))
        except requests.RequestException as e:
            result["status"] = "error"
            result["error"] = str(e)
        results.append(result)
        if delay:
            time.sleep(delay)

    return results


def _parse_html(html: str, page_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = meta_desc_tag.get("content", "").strip() if meta_desc_tag else None

    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    canonical = canonical_tag.get("href") if canonical_tag else None

    robots_tag = soup.find("meta", attrs={"name": "robots"})
    robots_content = robots_tag.get("content", "").lower() if robots_tag else ""
    is_noindex = "noindex" in robots_content

    h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1")]

    has_jsonld = bool(soup.find("script", attrs={"type": "application/ld+json"}))

    page_host = urlparse(page_url).netloc
    internal_links = set()
    links_to_search = False
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urljoin(page_url, href)
        host = urlparse(absolute).netloc
        if "search.doyouneedahome.com" in host:
            links_to_search = True
        elif host == page_host:
            internal_links.add(absolute.split("#")[0])

    return {
        "title": title,
        "meta_description": meta_description,
        "canonical": canonical,
        "is_noindex": is_noindex,
        "h1_tags": h1_tags,
        "has_jsonld": has_jsonld,
        "internal_links": sorted(internal_links),
        "links_to_search_site": links_to_search,
        "body_text": soup.get_text(" ", strip=True)[:5000],
    }


def summarize_site_health(crawl_results: list[dict], weak_link_threshold: int = 2) -> dict:
    ok_pages = [r for r in crawl_results if isinstance(r["status"], int) and r["status"] < 400]
    broken = [r for r in crawl_results if r.get("error") or (isinstance(r["status"], int) and r["status"] >= 400)]
    redirects = [r for r in crawl_results if r.get("redirect_chain")]

    missing_titles = [r["url"] for r in ok_pages if not r.get("title")]
    missing_meta = [r["url"] for r in ok_pages if not r.get("meta_description")]
    noindex_pages = [r["url"] for r in ok_pages if r.get("is_noindex")]

    title_counts = Counter(r["title"] for r in ok_pages if r.get("title"))
    duplicate_titles = {t: c for t, c in title_counts.items() if c > 1}

    meta_counts = Counter(r["meta_description"] for r in ok_pages if r.get("meta_description"))
    duplicate_meta = {m: c for m, c in meta_counts.items() if c > 1}

    canonical_issues = [
        r["url"]
        for r in ok_pages
        if r.get("canonical") and r["canonical"].rstrip("/") != r["url"].rstrip("/")
    ]

    # inbound-link counts across the crawled set, to flag weakly-linked and orphan pages
    inbound_counts: Counter = Counter()
    all_internal_link_targets: set[str] = set()
    for r in ok_pages:
        for target in r.get("internal_links", []):
            inbound_counts[target.rstrip("/")] += 1
            all_internal_link_targets.add(target)

    crawled_urls = {r["url"].rstrip("/") for r in ok_pages}
    weak_internal_link_pages = [
        r["url"] for r in ok_pages if inbound_counts.get(r["url"].rstrip("/"), 0) <= weak_link_threshold
    ]
    broken_internal_links = sorted(
        {link for link in all_internal_link_targets if link.rstrip("/") not in crawled_urls}
    )

    return {
        "pages_crawled": len(crawl_results),
        "pages_ok": len(ok_pages),
        "broken_links": [(r["url"], r.get("error") or r["status"]) for r in broken],
        "redirects": [(r["url"], r["final_url"]) for r in redirects],
        "missing_titles": missing_titles,
        "missing_meta_descriptions": missing_meta,
        "duplicate_titles": duplicate_titles,
        "duplicate_meta_descriptions": duplicate_meta,
        "noindex_pages": noindex_pages,
        "canonical_issues": canonical_issues,
        "broken_internal_links": broken_internal_links,
        "weak_internal_link_pages": weak_internal_link_pages,
        "pages_linking_to_search_site": [r["url"] for r in ok_pages if r.get("links_to_search_site")],
    }
