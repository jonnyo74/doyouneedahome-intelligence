"""Opportunities, wins, losses, and top pages/queries from GSC page/query data.

All functions take already-normalized dict lists (see search_console.py) so
they're trivial to unit test with fixtures — no live API calls here.
"""

def clean_url(url: str, base_url: str) -> str:
    path = url.replace(base_url, "").replace("https://www.doyouneedahome.com", "").replace(
        "https://doyouneedahome.com", ""
    )
    return path or "/"


def _index_by_key(rows: list[dict], key: str) -> dict[str, dict]:
    return {r[key]: r for r in rows}


def primary_queries_for_page(page_url: str, query_pages: list[dict], limit: int = 3) -> list[dict]:
    matches = [r for r in query_pages if r["page"] == page_url]
    matches.sort(key=lambda r: r["impressions"], reverse=True)
    return matches[:limit]


BUYER_INTENT_HINTS = ("homes for sale", "moving to", "neighborhoods", "communities", "condos", "new construction")
SELLER_INTENT_HINTS = ("sell", "selling", "value", "worth", "list my home")


def _classify_intent(text: str) -> str:
    t = text.lower()
    if any(h in t for h in SELLER_INTENT_HINTS):
        return "seller"
    if any(h in t for h in BUYER_INTENT_HINTS):
        return "buyer"
    return "informational"


def _recommend_action(page: dict, top_queries: list[dict], min_impressions_for_title_change: int = 30) -> str:
    if page["clicks"] == 0 and page["impressions"] >= min_impressions_for_title_change:
        return "Rewrite the page title and meta description to earn clicks at this position"
    if page["clicks"] == 0:
        return "Add stronger internal links and an FAQ section — not enough data yet to justify a title rewrite"
    if top_queries:
        query = top_queries[0]["query"]
        return f"Expand on-page content around '{query}' and add a CTA to search.doyouneedahome.com"
    return "Add a relevant FAQ section and strengthen internal links to this page"


def find_opportunities(pages: list[dict], query_pages: list[dict], site_cfg: dict, base_url: str) -> list[dict]:
    thresholds = site_cfg["thresholds"]
    out = []
    for page in pages:
        if page["impressions"] < thresholds["opportunity_min_impressions"]:
            continue
        if not (thresholds["opportunity_position_min"] <= page["position"] <= thresholds["opportunity_position_max"]):
            continue
        top_queries = primary_queries_for_page(page["page"], query_pages)
        out.append(
            {
                "url": clean_url(page["page"], base_url),
                "clicks": page["clicks"],
                "impressions": page["impressions"],
                "ctr": page["ctr"],
                "position": page["position"],
                "primary_queries": [q["query"] for q in top_queries],
                "recommended_action": _recommend_action(page, top_queries),
            }
        )
    out.sort(key=lambda r: r["impressions"], reverse=True)
    return out


def find_wins(pages: list[dict], pages_prev: list[dict], site_cfg: dict, base_url: str) -> list[dict]:
    thresholds = site_cfg["thresholds"]
    prev_by_url = _index_by_key(pages_prev, "page")
    out = []
    for page in pages:
        prev = prev_by_url.get(page["page"])
        if not prev or page["impressions"] < thresholds["wins_losses_min_impressions"]:
            continue
        delta = prev["position"] - page["position"]
        if delta >= thresholds["wins_losses_min_position_delta"]:
            out.append(
                {
                    "url": clean_url(page["page"], base_url),
                    "prev_position": round(prev["position"], 1),
                    "curr_position": round(page["position"], 1),
                    "position_improvement": round(delta, 1),
                    "click_growth": page["clicks"] - prev["clicks"],
                    "impression_growth": page["impressions"] - prev["impressions"],
                }
            )
    out.sort(key=lambda r: r["position_improvement"], reverse=True)
    return out


def find_losses(pages: list[dict], pages_prev: list[dict], site_cfg: dict, base_url: str) -> list[dict]:
    thresholds = site_cfg["thresholds"]
    prev_by_url = _index_by_key(pages_prev, "page")
    out = []
    for page in pages:
        prev = prev_by_url.get(page["page"])
        if not prev:
            continue
        if max(page["impressions"], prev["impressions"]) < thresholds["wins_losses_min_impressions"]:
            continue
        delta = page["position"] - prev["position"]
        if delta >= thresholds["wins_losses_min_position_delta"]:
            out.append(
                {
                    "url": clean_url(page["page"], base_url),
                    "prev_position": round(prev["position"], 1),
                    "curr_position": round(page["position"], 1),
                    "position_decline": round(delta, 1),
                    "click_decline": prev["clicks"] - page["clicks"],
                    "impression_decline": prev["impressions"] - page["impressions"],
                    "note": "Data shows a ranking decline; review the page for content or technical changes before assuming a cause.",
                }
            )
    out.sort(key=lambda r: r["position_decline"], reverse=True)
    return out


def top_pages_by_clicks(pages: list[dict], base_url: str, limit: int = 15) -> list[dict]:
    ranked = sorted(pages, key=lambda r: r["clicks"], reverse=True)[:limit]
    return [
        {
            "url": clean_url(p["page"], base_url),
            "clicks": p["clicks"],
            "impressions": p["impressions"],
            "ctr": p["ctr"],
            "position": round(p["position"], 1),
        }
        for p in ranked
    ]


def top_queries_by_impressions(
    queries: list[dict], query_pages: list[dict], base_url: str, content_rules: dict, limit: int = 15
) -> list[dict]:
    noise = [p.lower() for p in content_rules["noise_query_patterns"]]
    min_len = content_rules["min_query_length"]

    def is_meaningful(q: str) -> bool:
        ql = q.lower()
        if len(q) < min_len or not any(c.isalpha() for c in q):
            return False
        return not any(pattern in ql for pattern in noise)

    meaningful = [q for q in queries if is_meaningful(q["query"])]
    meaningful.sort(key=lambda r: r["impressions"], reverse=True)

    out = []
    for q in meaningful[:limit]:
        best_pages = [qp for qp in query_pages if qp["query"] == q["query"]]
        best_page = max(best_pages, key=lambda r: r["clicks"], default=None)
        out.append(
            {
                "query": q["query"],
                "clicks": q["clicks"],
                "impressions": q["impressions"],
                "ctr": q["ctr"],
                "position": round(q["position"], 1),
                "best_ranking_page": clean_url(best_page["page"], base_url) if best_page else None,
            }
        )
    return out


def find_quick_wins(opportunities: list[dict], content_rules: dict) -> list[dict]:
    rules = content_rules["quick_wins"]
    effort_scale = content_rules["effort_scale"]
    candidates = [
        o
        for o in opportunities
        if o["impressions"] >= rules["min_impressions"]
        and rules["position_min"] <= o["position"] <= rules["position_max"]
        and o["ctr"] <= rules["max_ctr"]
    ]

    out = []
    for o in candidates:
        intent = _classify_intent(o["url"] + " " + " ".join(o["primary_queries"]))
        if intent == "informational":
            continue
        is_title_rewrite = "title" in o["recommended_action"].lower()
        impact = "high" if o["impressions"] >= 50 else "medium" if o["impressions"] >= 25 else "low"
        effort = effort_scale["title_meta_rewrite"] if is_title_rewrite else effort_scale["add_internal_links"]
        out.append(
            {
                **o,
                "intent": intent,
                "expected_impact": impact,
                "estimated_effort": effort,
                "suggested_title_meta": o["recommended_action"] if is_title_rewrite else None,
            }
        )

    out.sort(key=lambda r: r["impressions"], reverse=True)
    return out[: content_rules["quick_wins"]["max_items"]]
