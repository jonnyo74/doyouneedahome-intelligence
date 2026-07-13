from src import report_builder


def _minimal_report_data():
    return {
        "meta": {"date": "January 05, 2026", "data_through": "2026-01-03"},
        "totals_7d": {"clicks": 100, "impressions": 1000, "ctr": 0.1, "avg_position": 8.0},
        "totals_prev7d": {"clicks": 80, "impressions": 900, "ctr": 0.089, "avg_position": 9.0},
        "sitemap": {"total_urls": 300, "new_urls": ["/a"], "removed_urls": [], "duplicates": [], "invalid": []},
        "site_health": {
            "pages_crawled": 300, "pages_ok": 298, "broken_links": [], "redirects": [],
            "missing_titles": [], "missing_meta_descriptions": [], "duplicate_titles": {},
            "duplicate_meta_descriptions": {}, "noindex_pages": [], "canonical_issues": [],
            "broken_internal_links": [], "weak_internal_link_pages": [], "pages_linking_to_search_site": [],
        },
        "opportunities": [], "wins": [], "losses": [], "top_pages": [], "top_queries": [],
        "quick_wins": [], "city_scorecards": [], "unmapped_communities": [],
        "new_content_ideas": [], "update_content_ideas": [], "internal_link_opportunities": [],
        "lead_magnet_opportunities": [], "keyword_tracker": {}, "news": [],
        "lead_source_integration_note": "Lead-source integration not configured.",
        "market_data_note": "Market-data integration not configured.",
        "stage_errors": {},
    }


def test_compute_totals():
    pages = [
        {"page": "/a", "clicks": 10, "impressions": 100, "ctr": 0.1, "position": 5.0},
        {"page": "/b", "clicks": 0, "impressions": 50, "ctr": 0.0, "position": 15.0},
    ]
    totals = report_builder.compute_totals(pages)
    assert totals["clicks"] == 10
    assert totals["impressions"] == 150
    assert totals["avg_position"] == 10.0


def test_compute_wow_change_handles_zero_previous():
    current = {"clicks": 10, "impressions": 100, "avg_position": 5.0}
    previous = {"clicks": 0, "impressions": 0, "avg_position": 6.0}
    change = report_builder.compute_wow_change(current, previous)
    assert change["clicks_pct"] is None
    assert change["avg_position_change"] == -1.0


def test_build_report_caps_monday_action_plan_at_five():
    data = _minimal_report_data()
    data["quick_wins"] = [
        {"url": f"/qw{i}", "clicks": 0, "impressions": 50, "ctr": 0.0, "position": 12.0, "recommended_action": "Fix it",
         "expected_impact": "high", "estimated_effort": 2, "primary_queries": []}
        for i in range(5)
    ]
    rendered = report_builder.build_report(data)
    assert len(rendered["json"]["monday_action_plan"]) <= 5
    assert "MONDAY ACTION PLAN" in rendered["txt"]
    assert "## Monday Action Plan" in rendered["md"]


def test_render_txt_shows_no_qualifying_opportunities_when_empty():
    data = _minimal_report_data()
    rendered = report_builder.build_report(data)
    assert "No qualifying opportunities this period." in rendered["txt"]


def test_write_report_files_creates_three_formats(tmp_path):
    data = _minimal_report_data()
    rendered = report_builder.build_report(data)
    report_builder.write_report_files(rendered, str(tmp_path), "2026-01-05")
    for fmt in ("txt", "md", "json"):
        assert (tmp_path / f"2026-01-05-doyouneedahome-intelligence.{fmt}").exists()
