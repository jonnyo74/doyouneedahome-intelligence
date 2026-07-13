"""New-development news monitoring via public RSS feeds.

Same technique as condowpb-intelligence's news_monitor.py: Google News RSS
search feeds per target market, filtered to residential-development
keywords, with a paywall/aggregator blocklist. Never invents a story —
articles come only from fetched feed content.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests

DEVELOPMENT_KEYWORDS = (
    "new construction",
    "new home",
    "new community",
    "development",
    "condominium",
    "condo",
    "site plan",
    "rezoning",
    "planning and zoning",
    "groundbreaking",
    "approved",
    "permit",
    "developer",
    "master-planned",
    "master planned",
    "golf community",
    "land purchase",
    "sales launch",
    "redevelopment",
    "mixed-use",
    "residences",
)

CONFIRMED_KEYWORDS = ("groundbreaking", "approved", "under construction", "now selling", "opens", "completed", "broke ground")
RUMOR_KEYWORDS = ("proposed", "rezoning request", "site plan application", "considering", "could bring", "may bring", "plans to")

BLOCKED_DOMAINS = (
    "palmbeachpost.com",
    "pbpost.com",
    "sun-sentinel.com",
    "miamiherald.com",
    "wsj.com",
    "bloomberg.com",
    "ft.com",
    "realtor.com",
    "zillow.com",
    "redfin.com",
    "trulia.com",
    "apartments.com",
    "rent.com",
    "hotpads.com",
    "homes.com",
)


def _feed_url(query: str) -> str:
    q = query.replace(" ", "+")
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def build_feeds(city_names: list[str]) -> list[dict]:
    feeds = [{"url": _feed_url("Palm Beach County new home community"), "city": None}]
    feeds.append({"url": _feed_url("site:bisnow.com Palm Beach County"), "city": None})
    feeds.append({"url": _feed_url("site:bizjournals.com Palm Beach County real estate"), "city": None})
    for city in city_names:
        feeds.append({"url": _feed_url(f"{city} Florida new development"), "city": city})
        feeds.append({"url": _feed_url(f"{city} Florida residential community"), "city": city})
    return feeds


def fetch_articles(feeds: list[dict], days: int, timeout: int = 10) -> list[dict]:
    articles = []
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)

    for feed in feeds:
        try:
            resp = requests.get(feed["url"], timeout=timeout)
            root = ElementTree.fromstring(resp.content)
        except Exception:
            continue

        for item in root.findall(".//item"):
            title = item.findtext("title", "") or ""
            link = item.findtext("link", "") or ""
            pub_date = item.findtext("pubDate", "") or ""
            source = item.findtext("source", "") or ""

            try:
                dt = parsedate_to_datetime(pub_date)
                if dt.timestamp() < cutoff:
                    continue
            except Exception:
                pass

            title_l = title.lower()
            if any(kw in title_l for kw in DEVELOPMENT_KEYWORDS):
                articles.append(
                    {"title": title, "link": link, "source": source, "date": pub_date, "matched_city": feed["city"]}
                )

    return _dedupe_and_filter(articles)


def _dedupe_and_filter(articles: list[dict]) -> list[dict]:
    seen_titles = set()
    unique = []
    for a in articles:
        if a["title"] in seen_titles:
            continue
        if any(d in a["link"] for d in BLOCKED_DOMAINS) or any(d in a.get("source", "") for d in BLOCKED_DOMAINS):
            continue
        seen_titles.add(a["title"])
        unique.append(a)
    return unique


def _story_key(article: dict) -> str:
    return article["title"].strip().lower()


def classify(article: dict) -> str:
    t = article["title"].lower()
    if any(kw in t for kw in CONFIRMED_KEYWORDS):
        return "confirmed"
    if any(kw in t for kw in RUMOR_KEYWORDS):
        return "rumor"
    return "unclear"


def recommended_action(article: dict, classification: str) -> str:
    if classification == "confirmed":
        return "Create a new development page or update the relevant city/new-construction hub"
    if classification == "rumor":
        return "Add to the development watch list — wait for more confirmation before publishing"
    return "Review manually — classification unclear from headline alone"


def filter_new_stories(articles: list[dict], seen: dict, dedupe_days: int, today: str) -> tuple[list[dict], dict]:
    """Drop stories already reported within `dedupe_days`, update the ledger."""
    today_dt = datetime.fromisoformat(today)
    new_articles = []
    updated_seen = dict(seen)

    for article in articles:
        key = _story_key(article)
        prior = seen.get(key)
        if prior:
            last_reported = datetime.fromisoformat(prior["last_reported"])
            if (today_dt - last_reported).days < dedupe_days:
                continue
        new_articles.append(article)
        updated_seen[key] = {
            "first_seen": prior["first_seen"] if prior else today,
            "last_reported": today,
            "title": article["title"],
        }

    return new_articles, updated_seen


def get_development_news(city_names: list[str], days: int, seen: dict, dedupe_days: int, today: str) -> tuple[list[dict], dict]:
    feeds = build_feeds(city_names)
    articles = fetch_articles(feeds, days)
    new_articles, updated_seen = filter_new_stories(articles, seen, dedupe_days, today)

    for a in new_articles:
        a["classification"] = classify(a)
        a["recommended_action"] = recommended_action(a, a["classification"])

    return new_articles, updated_seen
