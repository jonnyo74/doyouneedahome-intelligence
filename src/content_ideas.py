"""Content-gap ideas, existing-content updates, internal linking, and
lead-magnet placement recommendations — all derived from real Search
Console / crawl / sitemap data, never invented.
"""

from src.rankings import clean_url

LEAD_MAGNET_KEYWORDS = ("relocation guide", "buyer guide", "seller guide", "download", "free guide")


def _find_best_position_for_query(query: str, query_pages: list[dict]) -> float | None:
    matches = [r["position"] for r in query_pages if r["query"].lower() == query.lower()]
    return min(matches) if matches else None


def generate_new_content_ideas(
    queries: list[dict],
    query_pages: list[dict],
    city_scorecards: list[dict],
    content_rules: dict,
    base_url: str,
) -> list[dict]:
    rules = content_rules["content_ideas"]
    ideas = []
    seen_keywords = set()

    candidates = [q for q in queries if q["impressions"] >= rules["min_query_impressions"]]
    candidates.sort(key=lambda r: r["impressions"], reverse=True)

    for q in candidates:
        if len(ideas) >= rules["max_new_ideas"]:
            break
        query = q["query"]
        if query in seen_keywords:
            continue
        best_position = _find_best_position_for_query(query, query_pages)
        if best_position is not None and best_position <= 15:
            continue  # already well served by an existing page — that's an "update" case, not "write"

        matched_city = next(
            (c for c in city_scorecards if c["city"].lower() in query.lower() or c["slug"] in query.lower().replace(" ", "-")),
            None,
        )
        ideas.append(
            {
                "proposed_title": query.title(),
                "target_keyword": query,
                "search_data": f"{q['impressions']:.0f} impressions, {q['clicks']:.0f} clicks, avg position {q['position']:.1f}",
                "city_or_category": matched_city["city"] if matched_city else "General",
                "buyer_or_seller_intent": "seller" if any(w in query.lower() for w in ("sell", "selling")) else "buyer",
                "content_angle": f"No page currently ranks well for '{query}' — write content that directly answers this search.",
                "link_to_existing_pages": (
                    [f"/communities/{matched_city['slug']}"] if matched_city else []
                ),
                "search_site_cta": (
                    f"View Current {matched_city['city']} Homes" if matched_city else "Browse Homes on search.doyouneedahome.com"
                ),
                "lead_magnet": "Seller Guide" if any(w in query.lower() for w in ("sell", "selling")) else "Palm Beach County Relocation Guide",
            }
        )
        seen_keywords.add(query)

    return ideas


def generate_update_ideas(opportunities: list[dict], content_rules: dict, base_url: str) -> list[dict]:
    rules = content_rules["content_ideas"]
    ideas = []
    for o in opportunities[: rules["max_update_ideas"]]:
        missing_section = "FAQ section" if o["ctr"] < 0.02 else "expanded content around top query"
        ideas.append(
            {
                "url": o["url"],
                "query_opportunity": o["primary_queries"][0] if o["primary_queries"] else None,
                "missing_section": missing_section,
                "suggested_internal_links": ["relevant community pages", "search.doyouneedahome.com"],
                "suggested_cta": "View Current Homes",
                "needs_freshness_update": o["impressions"] >= 30 and o["clicks"] == 0,
            }
        )
    return ideas


def generate_internal_link_opportunities(
    crawl_index: dict[str, dict],
    city_scorecards: list[dict],
    base_url: str,
    search_platform_url: str,
    content_rules: dict,
) -> list[dict]:
    max_suggestions = content_rules["internal_links"]["max_suggestions"]
    suggestions = []

    for city in city_scorecards:
        if len(suggestions) >= max_suggestions:
            break
        city_url = f"{base_url}/communities/{city['slug']}"
        city_page = crawl_index.get(city_url)
        if not city_page or city_page.get("status") != 200:
            continue
        existing_links = set(city_page.get("internal_links", []))

        for community in city["community_pages"]:
            if len(suggestions) >= max_suggestions:
                break
            community_url = f"{base_url}/communities/{community['slug']}"
            if community_url in existing_links:
                continue
            suggestions.append(
                {
                    "source": clean_url(city_url, base_url),
                    "destination": clean_url(community_url, base_url),
                    "anchor_text": f"{community['name']} homes for sale",
                    "reason": f"{city['city']} page doesn't yet link to its {community['name']} community page.",
                }
            )

        if not city_page.get("links_to_search_site") and len(suggestions) < max_suggestions:
            suggestions.append(
                {
                    "source": clean_url(city_url, base_url),
                    "destination": search_platform_url,
                    "anchor_text": f"View Current {city['city']} Homes",
                    "reason": f"{city['city']} page has no link to {search_platform_url}.",
                }
            )

    return suggestions[:max_suggestions]


def generate_lead_magnet_opportunities(
    city_scorecards: list[dict], crawl_index: dict[str, dict], site_cfg: dict, base_url: str
) -> list[dict]:
    magnets = site_cfg["lead_magnets"]
    opportunities = []

    for city in city_scorecards:
        city_url = f"{base_url}/communities/{city['slug']}"
        page = crawl_index.get(city_url)
        if not page or page.get("status") != 200:
            continue
        body = (page.get("body_text") or "").lower()
        has_magnet = any(k in body for k in LEAD_MAGNET_KEYWORDS)
        if has_magnet:
            continue
        magnet = magnets[0] if city["tier"] in (1, "1") else next((m for m in magnets if "relocation" in m["id"]), magnets[0])
        opportunities.append(
            {
                "url": clean_url(city_url, base_url),
                "recommended_guide": magnet["name"],
                "cta_copy": f"Get the Free {magnet['name']}",
                "placement": "Below the intro section, before the community list",
                "buyer_or_seller_intent": "buyer",
            }
        )

    return opportunities
