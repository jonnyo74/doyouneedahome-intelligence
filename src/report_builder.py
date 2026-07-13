"""Assembles every computed section into TXT, Markdown, and JSON reports,
in the order specified by the DO Homes Group intelligence-report brief.
"""

import json
import os

DIVIDER = "=" * 55


def compute_totals(pages: list[dict]) -> dict:
    clicks = sum(p["clicks"] for p in pages)
    impressions = sum(p["impressions"] for p in pages)
    ctr = (clicks / impressions) if impressions else 0.0
    avg_position = sum(p["position"] for p in pages) / len(pages) if pages else 0.0
    return {"clicks": clicks, "impressions": impressions, "ctr": ctr, "avg_position": round(avg_position, 1)}


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def compute_wow_change(current: dict, previous: dict) -> dict:
    return {
        "clicks_pct": _pct_change(current["clicks"], previous["clicks"]),
        "impressions_pct": _pct_change(current["impressions"], previous["impressions"]),
        "avg_position_change": round(current["avg_position"] - previous["avg_position"], 1),
    }


def _count_technical_issues(site_health: dict) -> int:
    return (
        len(site_health.get("broken_links", []))
        + len(site_health.get("missing_titles", []))
        + len(site_health.get("missing_meta_descriptions", []))
        + len(site_health.get("duplicate_titles", {}))
        + len(site_health.get("duplicate_meta_descriptions", {}))
        + len(site_health.get("noindex_pages", []))
        + len(site_health.get("canonical_issues", []))
        + len(site_health.get("broken_internal_links", []))
    )


def build_monday_action_plan(report_data: dict) -> list[dict]:
    candidates = []

    for qw in report_data.get("quick_wins", [])[:3]:
        candidates.append(
            {
                "task": qw["recommended_action"],
                "url_or_city": qw["url"],
                "why": f"{qw['impressions']:.0f} impressions at position {qw['position']:.1f} with low CTR — a quick fix can convert visibility into clicks.",
                "estimated_effort": qw["estimated_effort"],
                "expected_seo_impact": qw["expected_impact"],
                "expected_lead_impact": qw["expected_impact"],
                "claude_code_can_implement": True,
                "_priority": qw["impressions"],
            }
        )

    for city in report_data.get("city_scorecards", []):
        if city.get("extra_detail") and city["score"] < 70:
            candidates.append(
                {
                    "task": city["highest_priority_action"],
                    "url_or_city": city["city"],
                    "why": f"{city['city']} authority score is {city['score']}/100 — a Tier 1 market with room to grow.",
                    "estimated_effort": 6,
                    "expected_seo_impact": "high",
                    "expected_lead_impact": "high",
                    "claude_code_can_implement": False,
                    "_priority": 100 - city["score"] + 20,
                }
            )
            break

    for idea in report_data.get("new_content_ideas", [])[:2]:
        candidates.append(
            {
                "task": f"Write: {idea['proposed_title']}",
                "url_or_city": idea["city_or_category"],
                "why": idea["search_data"],
                "estimated_effort": 6,
                "expected_seo_impact": "medium",
                "expected_lead_impact": "medium",
                "claude_code_can_implement": True,
                "_priority": 15,
            }
        )

    confirmed_news = [n for n in report_data.get("news", []) if n.get("classification") == "confirmed"]
    if confirmed_news:
        n = confirmed_news[0]
        candidates.append(
            {
                "task": n["recommended_action"],
                "url_or_city": n.get("matched_city") or "Palm Beach County",
                "why": n["title"],
                "estimated_effort": 7,
                "expected_seo_impact": "medium",
                "expected_lead_impact": "medium",
                "claude_code_can_implement": False,
                "_priority": 25,
            }
        )

    if report_data.get("internal_link_opportunities"):
        link = report_data["internal_link_opportunities"][0]
        candidates.append(
            {
                "task": f"Add internal link: {link['anchor_text']}",
                "url_or_city": link["source"],
                "why": link["reason"],
                "estimated_effort": 2,
                "expected_seo_impact": "low",
                "expected_lead_impact": "low",
                "claude_code_can_implement": True,
                "_priority": 5,
            }
        )

    candidates.sort(key=lambda c: c["_priority"], reverse=True)
    top5 = candidates[:5]
    for c in top5:
        c.pop("_priority", None)
    return top5


def compute_executive_summary(report_data: dict) -> dict:
    totals = report_data["totals_7d"]
    wow = compute_wow_change(totals, report_data["totals_prev7d"])
    return {
        "total_clicks": totals["clicks"],
        "total_impressions": totals["impressions"],
        "ctr": round(totals["ctr"] * 100, 2),
        "avg_position": totals["avg_position"],
        "week_over_week": wow,
        "sitemap_url_count": report_data["sitemap"]["total_urls"],
        "sitemap_new_this_week": len(report_data["sitemap"]["new_urls"]),
        "sitemap_removed_this_week": len(report_data["sitemap"]["removed_urls"]),
        "qualified_opportunities": len(report_data["opportunities"]),
        "technical_issues": _count_technical_issues(report_data["site_health"]),
        "new_development_stories": len(report_data["news"]),
    }


def _fmt_url_line(clicks, impressions, position, url) -> str:
    return f"  {clicks:5.0f} clicks  {impressions:6.0f} impr  pos {position:5.1f}  {url}"


def _txt_section(title: str) -> list[str]:
    return ["", DIVIDER, title, DIVIDER]


def render_txt(report_data: dict) -> str:
    lines = []
    lines.append(f"DOYouNeedAHome Intelligence Report — {report_data['meta']['date']}")
    lines.append(f"Data through {report_data['meta']['data_through']}")

    es = report_data["executive_summary"]
    lines += _txt_section("EXECUTIVE SUMMARY")
    lines.append(f"  Total clicks (7d):       {es['total_clicks']:.0f}  ({_fmt_pct(es['week_over_week']['clicks_pct'])} WoW)")
    lines.append(f"  Total impressions (7d):  {es['total_impressions']:.0f}  ({_fmt_pct(es['week_over_week']['impressions_pct'])} WoW)")
    lines.append(f"  CTR:                     {es['ctr']}%")
    lines.append(f"  Avg position:            {es['avg_position']}  ({es['week_over_week']['avg_position_change']:+.1f} WoW)")
    lines.append(f"  Sitemap URLs:            {es['sitemap_url_count']}  (+{es['sitemap_new_this_week']} / -{es['sitemap_removed_this_week']})")
    lines.append(f"  Qualified opportunities: {es['qualified_opportunities']}")
    lines.append(f"  Technical issues:        {es['technical_issues']}")
    lines.append(f"  New-development stories: {es['new_development_stories']}")
    lines.append("\n  TOP 5 ACTIONS THIS WEEK:")
    for i, a in enumerate(report_data["monday_action_plan"], 1):
        lines.append(f"    {i}. {a['task']} ({a['url_or_city']})")

    lines += _txt_section("OPPORTUNITIES — Almost on Page 1")
    if report_data["opportunities"]:
        for o in report_data["opportunities"]:
            lines.append(f"  {o['url']}")
            lines.append(f"    {o['clicks']:.0f} clicks · {o['impressions']:.0f} impressions · position {o['position']:.1f} · CTR {o['ctr']*100:.1f}%")
            if o["primary_queries"]:
                lines.append(f"    Queries: {', '.join(o['primary_queries'])}")
            lines.append(f"    → {o['recommended_action']}")
    else:
        lines.append("  No qualifying opportunities this period.")

    lines += _txt_section("WINS — Pages That Climbed")
    if report_data["wins"]:
        for w in report_data["wins"]:
            lines.append(f"  {w['url']}")
            lines.append(f"    Position {w['prev_position']} → {w['curr_position']} (up {w['position_improvement']}) · clicks {w['click_growth']:+.0f} · impressions {w['impression_growth']:+.0f}")
    else:
        lines.append("  No significant ranking improvements this period.")

    lines += _txt_section("LOSSES — Pages That Slipped")
    if report_data["losses"]:
        for loss in report_data["losses"]:
            lines.append(f"  {loss['url']}")
            lines.append(f"    Position {loss['prev_position']} → {loss['curr_position']} (down {loss['position_decline']}) · clicks {-loss['click_decline']:+.0f} · impressions {-loss['impression_decline']:+.0f}")
            lines.append(f"    {loss['note']}")
    else:
        lines.append("  No significant ranking declines this period.")

    lines += _txt_section("TOP PAGES BY CLICKS — Last 28 Days")
    for p in report_data["top_pages"]:
        lines.append(_fmt_url_line(p["clicks"], p["impressions"], p["position"], p["url"]))

    lines += _txt_section("TOP QUERIES BY IMPRESSIONS")
    for q in report_data["top_queries"]:
        lines.append(f"  {q['clicks']:5.0f} clicks  {q['impressions']:6.0f} impr  pos {q['position']:5.1f}  '{q['query']}'  → {q['best_ranking_page']}")

    lines += _txt_section("FIX THESE FIRST — Quick Wins")
    if report_data["quick_wins"]:
        for qw in report_data["quick_wins"]:
            lines.append(f"  {qw['url']}")
            lines.append(f"    {qw['impressions']:.0f} impr · pos {qw['position']:.1f} · CTR {qw['ctr']*100:.1f}%")
            lines.append(f"    → {qw['recommended_action']}")
            lines.append(f"    Expected impact: {qw['expected_impact']} · Effort: {qw['estimated_effort']}/10")
    else:
        lines.append("  No quick wins identified this period.")

    lines += _txt_section("CITY AUTHORITY SCORECARDS")
    for city in report_data["city_scorecards"]:
        lines.append(f"\n  {city['city']} (Tier {city['tier']}) — {city['score']}/100")
        lines.append(f"    Main city page present: {city['main_city_page_present']}")
        lines.append(f"    Community pages: {len(city['community_pages'])} · Blog coverage: {city['blog_coverage']}")
        if city["communities_with_no_dedicated_page"]:
            lines.append(f"    No dedicated page yet: {', '.join(city['communities_with_no_dedicated_page'])}")
        lines.append(f"    → {city['highest_priority_action']}")
        if "extra_detail" in city:
            ed = city["extra_detail"]
            lines.append(f"    Percent complete: {ed['percent_complete']}%")
            lines.append(f"    Top gaps: {', '.join(ed['top_5_gaps']) if ed['top_5_gaps'] else 'none'}")
    if report_data.get("unmapped_communities"):
        lines.append("\n  UNMAPPED COMMUNITY PAGES (need manual classification in config/cities.yaml):")
        for u in report_data["unmapped_communities"]:
            lines.append(f"    /communities/{u['slug']}  (candidates: {', '.join(u['candidate_cities']) or 'none detected'})")

    lines += _txt_section("WRITE THESE — Content Ideas From Search Data")
    if report_data["new_content_ideas"]:
        for i, idea in enumerate(report_data["new_content_ideas"], 1):
            lines.append(f"  {i}. {idea['proposed_title']}")
            lines.append(f"     Keyword: {idea['target_keyword']} — {idea['search_data']}")
            lines.append(f"     Angle: {idea['content_angle']}")
            lines.append(f"     CTA: {idea['search_site_cta']} · Lead magnet: {idea['lead_magnet']}")
    else:
        lines.append("  No new content ideas generated this period.")

    lines += _txt_section("UPDATE THESE — Existing Content Opportunities")
    if report_data["update_content_ideas"]:
        for u in report_data["update_content_ideas"]:
            lines.append(f"  {u['url']}")
            lines.append(f"    Missing: {u['missing_section']} · CTA: {u['suggested_cta']} · Freshness update needed: {u['needs_freshness_update']}")
    else:
        lines.append("  No update opportunities identified this period.")

    lines += _txt_section("INTERNAL LINKING OPPORTUNITIES")
    if report_data["internal_link_opportunities"]:
        for link in report_data["internal_link_opportunities"]:
            lines.append(f"  {link['source']}  →  {link['destination']}")
            lines.append(f"    Anchor: \"{link['anchor_text']}\" — {link['reason']}")
    else:
        lines.append("  No internal linking gaps identified this period.")

    lines += _txt_section("LEAD-MAGNET OPPORTUNITIES")
    if report_data["lead_magnet_opportunities"]:
        for lm in report_data["lead_magnet_opportunities"]:
            lines.append(f"  {lm['url']}")
            lines.append(f"    Guide: {lm['recommended_guide']} · CTA: \"{lm['cta_copy']}\" · Placement: {lm['placement']}")
    else:
        lines.append("  No lead-magnet placement gaps identified this period.")
    lines.append(f"\n  {report_data['lead_source_integration_note']}")

    sh = report_data["site_health"]
    lines += _txt_section(f"SITE HEALTH — {report_data['sitemap']['total_urls']} sitemap URLs")
    lines.append(f"  Pages crawled: {sh['pages_crawled']} · OK: {sh['pages_ok']}")
    lines.append(f"  Broken links: {len(sh['broken_links'])}")
    lines.append(f"  Redirects: {len(sh['redirects'])}")
    lines.append(f"  Missing titles: {len(sh['missing_titles'])} · Missing meta descriptions: {len(sh['missing_meta_descriptions'])}")
    lines.append(f"  Duplicate titles: {len(sh['duplicate_titles'])} · Duplicate meta descriptions: {len(sh['duplicate_meta_descriptions'])}")
    lines.append(f"  Noindex pages: {len(sh['noindex_pages'])} · Canonical issues: {len(sh['canonical_issues'])}")
    lines.append(f"  Broken internal links: {len(sh['broken_internal_links'])} · Weakly-linked pages: {len(sh['weak_internal_link_pages'])}")
    lines.append(f"  New sitemap URLs: {len(report_data['sitemap']['new_urls'])} · Removed: {len(report_data['sitemap']['removed_urls'])}")
    lines.append("  Note: sitemap presence is not the same as being indexed by Google.")

    lines += _txt_section("NEW-DEVELOPMENT WATCH")
    if report_data["news"]:
        for n in report_data["news"]:
            lines.append(f"  [{n['classification'].upper()}] {n['title']}")
            lines.append(f"    Location: {n.get('matched_city') or 'Palm Beach County region'} · {n['date']}")
            lines.append(f"    → {n['recommended_action']}")
            lines.append(f"    {n['link']}")
    else:
        lines.append("  No meaningful development stories in the last 7 days.")

    lines += _txt_section("MONEY-KEYWORD TRACKER")
    for group, rows in report_data["keyword_tracker"].items():
        lines.append(f"\n  {group.replace('_', ' ').title()}:")
        for r in rows:
            pos = f"{r['current_position']}" if r["current_position"] is not None else "—"
            lines.append(f"    {pos:>6}  {r['status']:<28}  '{r['keyword']}'")

    lines += _txt_section("MONDAY ACTION PLAN")
    for i, a in enumerate(report_data["monday_action_plan"], 1):
        lines.append(f"\n  {i}. {a['task']}")
        lines.append(f"     Where: {a['url_or_city']}")
        lines.append(f"     Why: {a['why']}")
        lines.append(f"     Effort: {a['estimated_effort']}/10 · SEO impact: {a['expected_seo_impact']} · Lead impact: {a['expected_lead_impact']}")
        lines.append(f"     Claude Code can implement: {'Yes' if a['claude_code_can_implement'] else 'No — requires manual/business judgment'}")

    lines.append("")
    lines.append("-" * 55)
    lines.append("DOYouNeedAHome Intelligence System")

    return "\n".join(lines)


def _fmt_pct(pct: float | None) -> str:
    return "n/a" if pct is None else f"{pct:+.1f}%"


def render_markdown(d: dict) -> str:
    md = [f"# DOYouNeedAHome Intelligence Report — {d['meta']['date']}", "", f"_Data through {d['meta']['data_through']}_", ""]
    es = d["executive_summary"]
    md.append("## Executive Summary")
    md.append(f"- **Total clicks (7d):** {es['total_clicks']:.0f} ({_fmt_pct(es['week_over_week']['clicks_pct'])} WoW)")
    md.append(f"- **Total impressions (7d):** {es['total_impressions']:.0f} ({_fmt_pct(es['week_over_week']['impressions_pct'])} WoW)")
    md.append(f"- **CTR:** {es['ctr']}% · **Avg position:** {es['avg_position']} ({es['week_over_week']['avg_position_change']:+.1f} WoW)")
    md.append(f"- **Sitemap URLs:** {es['sitemap_url_count']} (+{es['sitemap_new_this_week']} / -{es['sitemap_removed_this_week']})")
    md.append(f"- **Qualified opportunities:** {es['qualified_opportunities']} · **Technical issues:** {es['technical_issues']} · **New-development stories:** {es['new_development_stories']}")
    md.append("")
    md.append("**Top 5 actions this week:**")
    for i, a in enumerate(d["monday_action_plan"], 1):
        md.append(f"{i}. {a['task']} ({a['url_or_city']})")
    md.append("")

    md.append("## Opportunities — Almost on Page 1")
    if d["opportunities"]:
        md.append("| URL | Clicks | Impr | CTR | Pos | Queries | Action |")
        md.append("|---|---|---|---|---|---|---|")
        for o in d["opportunities"]:
            md.append(
                f"| {o['url']} | {o['clicks']:.0f} | {o['impressions']:.0f} | {o['ctr']*100:.1f}% | {o['position']:.1f} | "
                f"{', '.join(o['primary_queries'])} | {o['recommended_action']} |"
            )
    else:
        md.append("No qualifying opportunities this period.")
    md.append("")

    md.append("## Wins — Pages That Climbed")
    if d["wins"]:
        md.append("| URL | Prev pos | Curr pos | Δ | Click growth | Impr growth |")
        md.append("|---|---|---|---|---|---|")
        for w in d["wins"]:
            md.append(f"| {w['url']} | {w['prev_position']} | {w['curr_position']} | {w['position_improvement']} | {w['click_growth']:+.0f} | {w['impression_growth']:+.0f} |")
    else:
        md.append("No significant ranking improvements this period.")
    md.append("")

    md.append("## Losses — Pages That Slipped")
    if d["losses"]:
        md.append("| URL | Prev pos | Curr pos | Δ | Click decline | Impr decline |")
        md.append("|---|---|---|---|---|---|")
        for loss in d["losses"]:
            md.append(f"| {loss['url']} | {loss['prev_position']} | {loss['curr_position']} | {loss['position_decline']} | {-loss['click_decline']:+.0f} | {-loss['impression_decline']:+.0f} |")
    else:
        md.append("No significant ranking declines this period.")
    md.append("")

    md.append("## Top Pages by Clicks (Last 28 Days)")
    md.append("| Clicks | Impressions | Pos | URL |")
    md.append("|---|---|---|---|")
    for p in d["top_pages"]:
        md.append(f"| {p['clicks']:.0f} | {p['impressions']:.0f} | {p['position']} | {p['url']} |")
    md.append("")

    md.append("## Top Queries by Impressions")
    md.append("| Clicks | Impressions | Pos | Query | Best page |")
    md.append("|---|---|---|---|---|")
    for q in d["top_queries"]:
        md.append(f"| {q['clicks']:.0f} | {q['impressions']:.0f} | {q['position']} | {q['query']} | {q['best_ranking_page']} |")
    md.append("")

    md.append("## Fix These First — Quick Wins")
    if d["quick_wins"]:
        for qw in d["quick_wins"]:
            md.append(f"- **{qw['url']}** — {qw['impressions']:.0f} impr, pos {qw['position']:.1f}, CTR {qw['ctr']*100:.1f}%. "
                       f"{qw['recommended_action']} _(impact: {qw['expected_impact']}, effort: {qw['estimated_effort']}/10)_")
    else:
        md.append("No quick wins identified this period.")
    md.append("")

    md.append("## City Authority Scorecards")
    for city in d["city_scorecards"]:
        md.append(f"### {city['city']} (Tier {city['tier']}) — {city['score']}/100")
        md.append(f"- Main city page present: {city['main_city_page_present']}")
        md.append(f"- Community pages: {len(city['community_pages'])} · Blog coverage: {city['blog_coverage']}")
        if city["communities_with_no_dedicated_page"]:
            md.append(f"- No dedicated page yet: {', '.join(city['communities_with_no_dedicated_page'])}")
        md.append(f"- **Next action:** {city['highest_priority_action']}")
        if "extra_detail" in city:
            ed = city["extra_detail"]
            md.append(f"- Percent complete: {ed['percent_complete']}%")
            md.append(f"- Top gaps: {', '.join(ed['top_5_gaps']) if ed['top_5_gaps'] else 'none'}")
        md.append("")
    if d.get("unmapped_communities"):
        md.append("**Unmapped community pages** (need manual classification in `config/cities.yaml`):")
        for u in d["unmapped_communities"]:
            md.append(f"- `/communities/{u['slug']}` — candidates: {', '.join(u['candidate_cities']) or 'none detected'}")
    md.append("")

    md.append("## Write These — Content Ideas From Search Data")
    if d["new_content_ideas"]:
        for i, idea in enumerate(d["new_content_ideas"], 1):
            md.append(f"{i}. **{idea['proposed_title']}** — keyword: `{idea['target_keyword']}` ({idea['search_data']})")
            md.append(f"   - Angle: {idea['content_angle']}")
            md.append(f"   - CTA: {idea['search_site_cta']} · Lead magnet: {idea['lead_magnet']}")
    else:
        md.append("No new content ideas generated this period.")
    md.append("")

    md.append("## Update These — Existing Content Opportunities")
    if d["update_content_ideas"]:
        for u in d["update_content_ideas"]:
            md.append(f"- **{u['url']}** — missing {u['missing_section']}, CTA: {u['suggested_cta']}, freshness update needed: {u['needs_freshness_update']}")
    else:
        md.append("No update opportunities identified this period.")
    md.append("")

    md.append("## Internal Linking Opportunities")
    if d["internal_link_opportunities"]:
        for link in d["internal_link_opportunities"]:
            md.append(f"- `{link['source']}` → `{link['destination']}` — anchor: \"{link['anchor_text']}\" ({link['reason']})")
    else:
        md.append("No internal linking gaps identified this period.")
    md.append("")

    md.append("## Lead-Magnet Opportunities")
    if d["lead_magnet_opportunities"]:
        for lm in d["lead_magnet_opportunities"]:
            md.append(f"- **{lm['url']}** — {lm['recommended_guide']}, CTA: \"{lm['cta_copy']}\", placement: {lm['placement']}")
    else:
        md.append("No lead-magnet placement gaps identified this period.")
    md.append(f"\n_{d['lead_source_integration_note']}_")
    md.append("")

    sh = d["site_health"]
    md.append(f"## Site Health — {d['sitemap']['total_urls']} sitemap URLs")
    md.append(f"- Pages crawled: {sh['pages_crawled']} · OK: {sh['pages_ok']}")
    md.append(f"- Broken links: {len(sh['broken_links'])} · Redirects: {len(sh['redirects'])}")
    md.append(f"- Missing titles: {len(sh['missing_titles'])} · Missing meta descriptions: {len(sh['missing_meta_descriptions'])}")
    md.append(f"- Duplicate titles: {len(sh['duplicate_titles'])} · Duplicate meta descriptions: {len(sh['duplicate_meta_descriptions'])}")
    md.append(f"- Noindex pages: {len(sh['noindex_pages'])} · Canonical issues: {len(sh['canonical_issues'])}")
    md.append(f"- Broken internal links: {len(sh['broken_internal_links'])} · Weakly-linked pages: {len(sh['weak_internal_link_pages'])}")
    md.append(f"- New sitemap URLs: {len(d['sitemap']['new_urls'])} · Removed: {len(d['sitemap']['removed_urls'])}")
    md.append("- _Sitemap presence is not the same as being indexed by Google._")
    md.append("")

    md.append("## New-Development Watch")
    if d["news"]:
        for n in d["news"]:
            md.append(f"- **[{n['classification'].upper()}] {n['title']}** — {n.get('matched_city') or 'Palm Beach County region'}, {n['date']}")
            md.append(f"  - {n['recommended_action']}")
            md.append(f"  - [{n['link']}]({n['link']})")
    else:
        md.append("No meaningful development stories in the last 7 days.")
    md.append("")

    md.append("## Money-Keyword Tracker")
    for group, rows in d["keyword_tracker"].items():
        md.append(f"### {group.replace('_', ' ').title()}")
        md.append("| Position | Status | Keyword |")
        md.append("|---|---|---|")
        for r in rows:
            pos = r["current_position"] if r["current_position"] is not None else "—"
            md.append(f"| {pos} | {r['status']} | {r['keyword']} |")
    md.append("")

    md.append("## Monday Action Plan")
    for i, a in enumerate(d["monday_action_plan"], 1):
        md.append(f"{i}. **{a['task']}**")
        md.append(f"   - Where: {a['url_or_city']}")
        md.append(f"   - Why: {a['why']}")
        md.append(f"   - Effort: {a['estimated_effort']}/10 · SEO impact: {a['expected_seo_impact']} · Lead impact: {a['expected_lead_impact']}")
        md.append(f"   - Claude Code can implement: {'Yes' if a['claude_code_can_implement'] else 'No'}")
    md.append("")
    md.append("---")
    md.append("_DOYouNeedAHome Intelligence System_")

    return "\n".join(md)


def build_report(report_data: dict) -> dict:
    report_data["executive_summary"] = compute_executive_summary(report_data)
    report_data["monday_action_plan"] = build_monday_action_plan(report_data)
    # exec summary references monday_action_plan for the "top 5 actions" callout,
    # so recompute after it exists.
    return {
        "txt": render_txt(report_data),
        "md": render_markdown(report_data),
        "json": report_data,
    }


def write_report_files(rendered: dict, reports_dir: str, date_str: str) -> dict:
    os.makedirs(reports_dir, exist_ok=True)
    base = f"{date_str}-doyouneedahome-intelligence"
    paths = {
        "txt": os.path.join(reports_dir, f"{base}.txt"),
        "md": os.path.join(reports_dir, f"{base}.md"),
        "json": os.path.join(reports_dir, f"{base}.json"),
    }
    with open(paths["txt"], "w", encoding="utf-8") as f:
        f.write(rendered["txt"])
    with open(paths["md"], "w", encoding="utf-8") as f:
        f.write(rendered["md"])
    with open(paths["json"], "w", encoding="utf-8") as f:
        json.dump(rendered["json"], f, indent=2, sort_keys=True, default=str)
    return paths
