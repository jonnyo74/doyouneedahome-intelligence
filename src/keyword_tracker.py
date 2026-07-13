"""Money-keyword tracker.

Uses Search Console query/page data only — never scrapes Google search
results. A keyword with zero matching GSC rows is reported as "No
measurable Search Console visibility during this period," never
"not ranking" (the site may still rank; GSC simply recorded no impressions).
"""

NO_VISIBILITY = "No measurable Search Console visibility during this period."


def build_keyword_groups(keywords_cfg: dict, cities_cfg: dict) -> dict[str, list[str]]:
    groups = dict(keywords_cfg["explicit_groups"])

    excluded_slugs = set(keywords_cfg.get("template_excludes", []))
    template = keywords_cfg["city_keyword_template"]

    for city in cities_cfg["cities"]:
        if city["slug"] in excluded_slugs:
            continue
        city_name = city["name"].lower()
        group_name = city["name"].upper().replace(" ", "_").replace(".", "")
        groups[group_name] = [t.format(city=city_name) for t in template]

    return groups


def _match_rows(keyword: str, query_pages: list[dict]) -> list[dict]:
    kl = keyword.lower()
    return [r for r in query_pages if r["query"].lower() == kl]


def _status(position: float | None, prev_position: float | None) -> str:
    if position is None:
        return "not enough data"
    if prev_position is not None:
        if position < prev_position - 0.5:
            return "climbing"
        if position > prev_position + 0.5:
            return "slipping"
    return "page 1" if position <= 10 else "page 2" if position <= 20 else f"position {round(position)}"


def track_keyword_group(
    keywords: list[str], query_pages: list[dict], base_url: str, last_recorded: dict
) -> list[dict]:
    from src.rankings import clean_url

    results = []
    for keyword in keywords:
        matches = _match_rows(keyword, query_pages)
        if not matches:
            results.append(
                {
                    "keyword": keyword,
                    "current_position": None,
                    "previous_position": last_recorded.get(keyword),
                    "clicks": 0,
                    "impressions": 0,
                    "ranking_page": None,
                    "status": NO_VISIBILITY,
                }
            )
            continue

        total_clicks = sum(r["clicks"] for r in matches)
        total_impressions = sum(r["impressions"] for r in matches)
        best = min(matches, key=lambda r: r["position"])
        position = round(best["position"], 1)
        prev = last_recorded.get(keyword)

        results.append(
            {
                "keyword": keyword,
                "current_position": position,
                "previous_position": prev,
                "clicks": total_clicks,
                "impressions": total_impressions,
                "ranking_page": clean_url(best["page"], base_url),
                "status": _status(position, prev),
            }
        )
    return results


def track_all_groups(
    keyword_groups: dict[str, list[str]], query_pages: list[dict], base_url: str, rank_history: dict
) -> dict[str, list[dict]]:
    dates = sorted(rank_history.keys())
    last_recorded = rank_history[dates[-1]] if dates else {}

    return {
        group: track_keyword_group(keywords, query_pages, base_url, last_recorded)
        for group, keywords in keyword_groups.items()
    }


def flatten_current_positions(tracked: dict[str, list[dict]]) -> dict[str, float | None]:
    flat = {}
    for rows in tracked.values():
        for r in rows:
            flat[r["keyword"]] = r["current_position"]
    return flat
