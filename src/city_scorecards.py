"""Per-city authority scorecards.

Every category scored is backed by real evidence gathered from the sitemap,
the crawl, and Search Console — never a blanket "every city needs golf
content" checklist. A category only counts toward a city's score if it's
actually applicable to that city (e.g. "community coverage" is skipped,
not penalized, for a city with zero configured communities).
"""

from urllib.parse import urlparse

CATEGORY_WEIGHTS = {
    "main_city_page": 20,
    "community_coverage": 20,
    "blog_lifestyle_coverage": 20,
    "organic_visibility": 15,
    "internal_linking": 15,
    "search_site_integration": 10,
}

CATEGORY_LABELS = {
    "main_city_page": "Main city page",
    "community_coverage": "Community/neighborhood coverage",
    "blog_lifestyle_coverage": "Blog & lifestyle content coverage",
    "organic_visibility": "Organic visibility (Search Console activity)",
    "internal_linking": "Internal linking",
    "search_site_integration": "search.doyouneedahome.com integration",
}


def _community_url(base_url: str, slug: str) -> str:
    return f"{base_url}/communities/{slug}"


def _blog_url(base_url: str, slug: str) -> str:
    return f"{base_url}/blog/{slug}"


def classify_communities(cities_cfg: dict, sitemap_urls: list[str], crawl_index: dict[str, dict], base_url: str):
    """Map every /communities/{slug} sitemap URL to a city.

    Returns (assignments: dict[city_slug -> list[dict]], unmapped: list[dict]).
    """
    cities = cities_cfg["cities"]
    city_slugs = {c["slug"] for c in cities}
    known_owner = {}  # community slug -> (city_slug, community dict)
    for city in cities:
        for community in city.get("known_communities", []):
            known_owner[community["slug"]] = (city["slug"], community)

    prefix = f"{base_url}/communities/"
    community_pages = [u for u in sitemap_urls if u.startswith(prefix) and u.rstrip("/") != prefix.rstrip("/")]

    assignments: dict[str, list[dict]] = {c["slug"]: [] for c in cities}
    unmapped: list[dict] = []

    for url in community_pages:
        slug = url[len(prefix):].strip("/")
        if slug in city_slugs:
            continue  # this is a main city page, not a community page

        if slug in known_owner:
            city_slug, community = known_owner[slug]
            assignments.setdefault(city_slug, []).append(
                {**community, "url": url, "confidence": community.get("confidence", "seed")}
            )
            continue

        # auto-detect: does the crawled page's title/H1/body mention exactly one city by name?
        page = crawl_index.get(url, {})
        text = " ".join(
            filter(None, [page.get("title", ""), " ".join(page.get("h1_tags", [])), page.get("body_text", "")])
        ).lower()
        matches = [c for c in cities if text and c["name"].lower() in text]
        if len(matches) == 1:
            city = matches[0]
            assignments.setdefault(city["slug"], []).append(
                {"slug": slug, "name": slug.replace("-", " ").title(), "tags": [], "url": url, "confidence": "auto"}
            )
        else:
            unmapped.append({"slug": slug, "url": url, "candidate_cities": [c["name"] for c in matches]})

    return assignments, unmapped


def _blog_coverage(city: dict, blog_template: list[str], sitemap_urls: list[str], base_url: str) -> dict:
    sitemap_set = set(sitemap_urls)
    covered, missing = [], []
    for template in blog_template:
        slug = template.format(city=city["slug"])
        url = _blog_url(base_url, slug)
        (covered if url in sitemap_set else missing).append(slug)
    return {"covered": covered, "missing": missing, "total": len(blog_template)}


def _gsc_activity(city: dict, communities: list[dict], blog_coverage: dict, pages_gsc: list[dict], base_url: str) -> dict:
    relevant_prefixes = [_community_url(base_url, city["slug"])] + [
        _community_url(base_url, c["slug"]) for c in communities
    ]
    relevant_blog_urls = {_blog_url(base_url, slug) for slug in blog_coverage["covered"]}

    clicks = impressions = 0.0
    for row in pages_gsc:
        url = row["page"]
        if url in relevant_blog_urls or any(url.rstrip("/") == p.rstrip("/") for p in relevant_prefixes):
            clicks += row["clicks"]
            impressions += row["impressions"]
    return {"clicks": clicks, "impressions": impressions, "has_activity": impressions > 0}


def _relative(url: str, base_url: str) -> str:
    return url.replace(base_url, "") or "/"


def _score_city(
    city: dict,
    communities: list[dict],
    blog_coverage: dict,
    gsc_activity: dict,
    main_page_present: bool,
    main_page_crawl: dict | None,
    weak_internal_link_pages: set[str],
    search_platform_host: str,
) -> dict:
    scores: dict[str, float] = {}
    applicable = dict(CATEGORY_WEIGHTS)

    scores["main_city_page"] = 1.0 if main_page_present else 0.0

    known_total = len(city.get("known_communities", []))
    if known_total == 0:
        del applicable["community_coverage"]
    else:
        matched = len([c for c in communities if c.get("confidence") != "auto"])
        scores["community_coverage"] = min(matched / known_total, 1.0)

    scores["blog_lifestyle_coverage"] = len(blog_coverage["covered"]) / blog_coverage["total"]

    scores["organic_visibility"] = 1.0 if gsc_activity["has_activity"] else 0.0

    if main_page_crawl and main_page_crawl.get("status") == 200:
        internal_link_count = len(main_page_crawl.get("internal_links", []))
        scores["internal_linking"] = 0.0 if internal_link_count == 0 else min(internal_link_count / 5, 1.0)
        scores["search_site_integration"] = 1.0 if main_page_crawl.get("links_to_search_site") else 0.0
    else:
        del applicable["internal_linking"]
        del applicable["search_site_integration"]

    total_weight = sum(applicable.values())
    score_100 = sum(scores[k] * applicable[k] for k in applicable) / total_weight * 100 if total_weight else 0.0

    weak_categories = [CATEGORY_LABELS[k] for k in applicable if scores[k] < 0.5]

    return {"score": round(score_100, 1), "category_scores": scores, "applicable_categories": list(applicable), "weak_categories": weak_categories}


def _highest_priority_action(city: dict, weak_categories: list[str], communities_missing: list[str]) -> str:
    if "Main city page" in weak_categories:
        return f"Publish (or fix) a live main city page for {city['name']} — none was found live in the crawl."
    if communities_missing:
        return f"Create a dedicated community page for {communities_missing[0]} — highest-traffic gap in {city['name']}."
    if weak_categories:
        return f"Improve {weak_categories[0].lower()} for {city['name']}."
    return f"{city['name']} is in good shape — focus on freshness updates and internal linking."


def build_city_scorecards(
    cities_cfg: dict,
    sitemap_urls: list[str],
    crawl_index: dict[str, dict],
    pages_gsc: list[dict],
    opportunities: list[dict],
    weak_internal_link_pages: list[str],
    base_url: str,
    search_platform_url: str,
) -> tuple[list[dict], list[dict]]:
    search_platform_host = urlparse(search_platform_url).netloc
    assignments, unmapped = classify_communities(cities_cfg, sitemap_urls, crawl_index, base_url)
    weak_set = set(weak_internal_link_pages)
    sitemap_set = set(sitemap_urls)

    scorecards = []
    for city in cities_cfg["cities"]:
        communities = assignments.get(city["slug"], [])
        blog_coverage = _blog_coverage(city, cities_cfg["blog_template"], sitemap_urls, base_url)
        gsc_activity = _gsc_activity(city, communities, blog_coverage, pages_gsc, base_url)

        main_url = _community_url(base_url, city["slug"])
        main_page_crawl = crawl_index.get(main_url)
        # Sitemap membership alone isn't good enough — a URL can be listed
        # but 404 in practice. Trust the crawl's live status when we have
        # one; fall back to sitemap presence only if it wasn't crawled.
        if main_page_crawl is not None:
            main_page_present = main_page_crawl.get("status") == 200
        else:
            main_page_present = main_url in sitemap_set

        scoring = _score_city(
            city, communities, blog_coverage, gsc_activity, main_page_present, main_page_crawl, weak_set, search_platform_host
        )

        known_slugs = {c["slug"] for c in city.get("known_communities", [])}
        matched_slugs = {c["slug"] for c in communities}
        communities_missing = sorted(known_slugs - matched_slugs)

        city_opportunities = [
            o for o in opportunities if f"/communities/{city['slug']}" in o["url"] or f"-{city['slug']}-florida" in o["url"]
        ]

        city_weak_links = [
            u for u in weak_internal_link_pages if f"/communities/{city['slug']}" in u or f"-{city['slug']}-florida" in u
        ]

        card = {
            "city": city["name"],
            "slug": city["slug"],
            "tier": city["tier"],
            "score": scoring["score"],
            "main_city_page_present": main_page_present,
            "community_pages": [{"name": c["name"], "slug": c["slug"], "confidence": c.get("confidence")} for c in communities],
            "communities_with_no_dedicated_page": communities_missing,
            "blog_coverage": f"{len(blog_coverage['covered'])}/{blog_coverage['total']}",
            "blog_missing_topics": blog_coverage["missing"],
            "search_console_activity": gsc_activity,
            "weak_categories": scoring["weak_categories"],
            "highest_priority_action": _highest_priority_action(city, scoring["weak_categories"], communities_missing),
        }

        if city.get("extra_detail"):
            card["extra_detail"] = {
                "percent_complete": scoring["score"],
                "top_5_gaps": (scoring["weak_categories"] + [f"No page for {s}" for s in communities_missing])[:5],
                "top_5_ranking_opportunities": city_opportunities[:5],
                "communities_with_no_dedicated_page": communities_missing,
                "pages_needing_stronger_internal_links": city_weak_links[:5],
            }

        scorecards.append(card)

    return scorecards, unmapped
