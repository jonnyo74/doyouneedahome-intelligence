"""Orchestrator. Wraps every data-source stage in its own try/except so one
failing integration never takes down the whole report (spec rule: one
failed data source must not destroy the whole report).

Usage:
    python -m src.main                # live run (needs GSC credentials)
    python -m src.main --fixtures      # offline dry run against tests/fixtures/
"""

import argparse
import json
import logging
import os
from datetime import date, timedelta

from dotenv import load_dotenv

from src import (
    city_scorecards,
    config_loader,
    content_ideas,
    crawler,
    keyword_tracker,
    news_monitor,
    notifications,
    rankings,
    report_builder,
    search_console,
    sitemap,
    storage,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("main")

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
FIXTURES_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "fixtures", "sample_data.json"
)


def _load_fixtures() -> dict:
    with open(FIXTURES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _gsc_stage(use_fixtures: bool) -> dict:
    if use_fixtures:
        fx = _load_fixtures()
        return {
            "pages_last7": fx["pages_last7"],
            "pages_prev7": fx["pages_prev7"],
            "pages_last28": fx["pages_last28"],
            "pages_prev28": fx["pages_prev28"],
            "queries_last28": fx["queries_last28"],
            "query_pages_last28": fx["query_pages_last28"],
            "available": True,
            "error": None,
        }
    try:
        service = search_console.get_service()
        periods = search_console.get_periods()
        return {
            "pages_last7": search_console.get_pages(service, periods["last7"]),
            "pages_prev7": search_console.get_pages(service, periods["prev7"]),
            "pages_last28": search_console.get_pages(service, periods["last28"]),
            "pages_prev28": search_console.get_pages(service, periods["prev28"]),
            "queries_last28": search_console.get_queries(service, periods["last28"]),
            "query_pages_last28": search_console.get_query_pages(service, periods["last28"]),
            "available": True,
            "error": None,
        }
    except Exception as e:
        log.error("Search Console stage failed: %s", e)
        empty = {"pages_last7": [], "pages_prev7": [], "pages_last28": [], "pages_prev28": [], "queries_last28": [], "query_pages_last28": []}
        return {**empty, "available": False, "error": str(e)}


def _sitemap_and_crawl_stage(use_fixtures: bool, site_cfg: dict) -> dict:
    if use_fixtures:
        fx = _load_fixtures()
        return {
            "sitemap_urls": fx["sitemap_urls"],
            "duplicates": [],
            "invalid": [],
            "crawl_results": fx["crawl_results"],
            "error": None,
        }
    try:
        crawl_cfg = site_cfg["crawl"]
        urls = sitemap.fetch_sitemap_urls(site_cfg["site"]["sitemap_url"], user_agent=crawl_cfg["user_agent"])
        duplicates = sitemap.find_duplicates(urls)
        invalid = sitemap.find_invalid_urls(urls, site_cfg["site"]["base_url"])
        unique_urls = sorted(set(urls) - set(invalid))
        crawl_results = crawler.crawl(
            unique_urls,
            user_agent=crawl_cfg["user_agent"],
            requests_per_second=crawl_cfg["requests_per_second"],
            timeout=crawl_cfg["request_timeout_seconds"],
            max_pages=crawl_cfg["max_pages_per_run"],
        )
        return {"sitemap_urls": urls, "duplicates": duplicates, "invalid": invalid, "crawl_results": crawl_results, "error": None}
    except Exception as e:
        log.error("Sitemap/crawl stage failed: %s", e)
        return {"sitemap_urls": [], "duplicates": [], "invalid": [], "crawl_results": [], "error": str(e)}


def _news_stage(use_fixtures: bool, cities_cfg: dict, content_rules: dict, today: str) -> tuple[list, dict]:
    seen = storage.load_news_seen()
    dedupe_days = content_rules["news"]["dedupe_days"]
    try:
        if use_fixtures:
            fx = _load_fixtures()
            raw = fx.get("news_raw", [])
            for a in raw:
                a["classification"] = news_monitor.classify(a)
                a["recommended_action"] = news_monitor.recommended_action(a, a["classification"])
            new_articles, updated_seen = news_monitor.filter_new_stories(raw, seen, dedupe_days, today)
        else:
            city_names = [c["name"] for c in cities_cfg["cities"]]
            new_articles, updated_seen = news_monitor.get_development_news(
                city_names, content_rules["news"]["lookback_days"], seen, dedupe_days, today
            )
        return new_articles, updated_seen
    except Exception as e:
        log.error("News monitor stage failed: %s", e)
        return [], seen


def run(use_fixtures: bool = False) -> dict:
    load_dotenv()
    site_cfg = config_loader.load_site_config()
    cities_cfg = config_loader.load_cities_config()
    keywords_cfg = config_loader.load_keywords_config()
    content_rules = config_loader.load_content_rules()

    base_url = site_cfg["site"]["base_url"]
    search_platform_url = site_cfg["site"]["search_platform_url"]
    today = date.today().isoformat()
    data_through = (date.today() - timedelta(days=site_cfg["search_console"]["complete_through_days_ago"])).isoformat()

    log.info("Pulling Search Console data...")
    gsc = _gsc_stage(use_fixtures)

    log.info("Fetching sitemap and crawling...")
    site_data = _sitemap_and_crawl_stage(use_fixtures, site_cfg)
    crawl_index = {r["url"]: r for r in site_data["crawl_results"]}

    baseline = storage.load_sitemap_baseline()
    sitemap_diff = sitemap.diff_urls(site_data["sitemap_urls"], baseline)
    if site_data["sitemap_urls"]:
        storage.save_sitemap_baseline(site_data["sitemap_urls"])

    site_health = crawler.summarize_site_health(
        site_data["crawl_results"], weak_link_threshold=site_cfg["thresholds"]["weak_internal_link_count"]
    )

    log.info("Computing rankings...")
    opportunities = rankings.find_opportunities(gsc["pages_last28"], gsc["query_pages_last28"], site_cfg, base_url)
    wins = rankings.find_wins(gsc["pages_last28"], gsc["pages_prev28"], site_cfg, base_url)
    losses = rankings.find_losses(gsc["pages_last28"], gsc["pages_prev28"], site_cfg, base_url)
    top_pages = rankings.top_pages_by_clicks(gsc["pages_last28"], base_url)
    top_queries = rankings.top_queries_by_impressions(gsc["queries_last28"], gsc["query_pages_last28"], base_url, content_rules)
    quick_wins = rankings.find_quick_wins(opportunities, content_rules)

    log.info("Tracking money keywords...")
    rank_history = storage.load_rank_history()
    keyword_groups = keyword_tracker.build_keyword_groups(keywords_cfg, cities_cfg)
    tracked = keyword_tracker.track_all_groups(keyword_groups, gsc["query_pages_last28"], base_url, rank_history)
    rank_history[today] = keyword_tracker.flatten_current_positions(tracked)
    storage.save_rank_history(rank_history)

    log.info("Building city scorecards...")
    scorecards, unmapped = city_scorecards.build_city_scorecards(
        cities_cfg,
        site_data["sitemap_urls"],
        crawl_index,
        gsc["pages_last28"],
        opportunities,
        site_health["weak_internal_link_pages"],
        base_url,
        search_platform_url,
    )

    log.info("Generating content ideas...")
    new_ideas = content_ideas.generate_new_content_ideas(gsc["queries_last28"], gsc["query_pages_last28"], scorecards, content_rules, base_url)
    update_ideas = content_ideas.generate_update_ideas(opportunities, content_rules, base_url)
    internal_links = content_ideas.generate_internal_link_opportunities(crawl_index, scorecards, base_url, search_platform_url, content_rules)
    lead_magnets = content_ideas.generate_lead_magnet_opportunities(scorecards, crawl_index, site_cfg, base_url)

    log.info("Checking development news...")
    news, updated_seen = _news_stage(use_fixtures, cities_cfg, content_rules, today)
    storage.save_news_seen(updated_seen)

    report_data = {
        "meta": {"date": date.today().strftime("%B %d, %Y"), "data_through": data_through},
        "totals_7d": report_builder.compute_totals(gsc["pages_last7"]),
        "totals_prev7d": report_builder.compute_totals(gsc["pages_prev7"]),
        "sitemap": {
            "total_urls": len(site_data["sitemap_urls"]),
            "new_urls": sitemap_diff["new"],
            "removed_urls": sitemap_diff["removed"],
            "duplicates": site_data["duplicates"],
            "invalid": site_data["invalid"],
        },
        "site_health": site_health,
        "opportunities": opportunities,
        "wins": wins,
        "losses": losses,
        "top_pages": top_pages,
        "top_queries": top_queries,
        "quick_wins": quick_wins,
        "city_scorecards": scorecards,
        "unmapped_communities": unmapped,
        "new_content_ideas": new_ideas,
        "update_content_ideas": update_ideas,
        "internal_link_opportunities": internal_links,
        "lead_magnet_opportunities": lead_magnets,
        "keyword_tracker": tracked,
        "news": news,
        "lead_source_integration_note": "Lead-source integration not configured.",
        "market_data_note": "Market-data integration not configured.",
        "stage_errors": {"search_console": gsc["error"], "sitemap_crawl": site_data["error"]},
    }

    rendered = report_builder.build_report(report_data)
    paths = report_builder.write_report_files(rendered, REPORTS_DIR, today)

    snapshot = {k: v for k, v in report_data.items() if k not in ("site_health",)}
    storage.save_run_snapshot(today, snapshot)

    log.info("Report written: %s", paths)

    subject = f"DOYouNeedAHome Intelligence Report — {report_data['meta']['date']}"
    notifications.send_report(subject, rendered["txt"])

    return paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", action="store_true", help="Run offline against tests/fixtures/sample_data.json")
    args = parser.parse_args()
    run(use_fixtures=args.fixtures)


if __name__ == "__main__":
    main()
