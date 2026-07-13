from src import rankings

SITE_CFG = {
    "thresholds": {
        "opportunity_min_impressions": 15,
        "opportunity_position_min": 8,
        "opportunity_position_max": 30,
        "wins_losses_min_impressions": 15,
        "wins_losses_min_position_delta": 3,
    }
}
BASE_URL = "https://www.example.com"


def test_find_opportunities_filters_by_impressions_and_position():
    pages = [
        {"page": "https://www.example.com/a", "clicks": 0, "impressions": 50, "ctr": 0.0, "position": 12.0},
        {"page": "https://www.example.com/b", "clicks": 5, "impressions": 10, "ctr": 0.5, "position": 12.0},  # too few impressions
        {"page": "https://www.example.com/c", "clicks": 0, "impressions": 50, "ctr": 0.0, "position": 3.0},  # already page 1
    ]
    result = rankings.find_opportunities(pages, [], SITE_CFG, BASE_URL)
    assert len(result) == 1
    assert result[0]["url"] == "/a"


def test_find_wins_requires_min_delta_and_impressions():
    pages = [{"page": "https://www.example.com/a", "clicks": 10, "impressions": 100, "ctr": 0.1, "position": 5.0}]
    prev = [{"page": "https://www.example.com/a", "clicks": 2, "impressions": 90, "ctr": 0.02, "position": 10.0}]
    wins = rankings.find_wins(pages, prev, SITE_CFG, BASE_URL)
    assert len(wins) == 1
    assert wins[0]["position_improvement"] == 5.0
    assert wins[0]["click_growth"] == 8


def test_find_wins_ignores_small_improvements():
    pages = [{"page": "https://www.example.com/a", "clicks": 10, "impressions": 100, "ctr": 0.1, "position": 8.5}]
    prev = [{"page": "https://www.example.com/a", "clicks": 9, "impressions": 95, "ctr": 0.09, "position": 9.5}]
    assert rankings.find_wins(pages, prev, SITE_CFG, BASE_URL) == []


def test_find_losses_never_states_a_cause_beyond_the_note():
    pages = [{"page": "https://www.example.com/a", "clicks": 1, "impressions": 40, "ctr": 0.025, "position": 20.0}]
    prev = [{"page": "https://www.example.com/a", "clicks": 8, "impressions": 60, "ctr": 0.13, "position": 8.0}]
    losses = rankings.find_losses(pages, prev, SITE_CFG, BASE_URL)
    assert len(losses) == 1
    assert losses[0]["position_decline"] == 12.0
    assert "review the page" in losses[0]["note"]


def test_top_queries_filters_noise():
    queries = [
        {"query": "jupiter homes for sale", "clicks": 5, "impressions": 100, "ctr": 0.05, "position": 6.0},
        {"query": "free jupiter pdf download", "clicks": 0, "impressions": 200, "ctr": 0.0, "position": 40.0},
    ]
    content_rules = {"noise_query_patterns": ["free download", "pdf"], "min_query_length": 3}
    result = rankings.top_queries_by_impressions(queries, [], BASE_URL, content_rules, limit=10)
    assert len(result) == 1
    assert result[0]["query"] == "jupiter homes for sale"


def test_quick_wins_respects_max_ctr_and_cap():
    content_rules = {
        "quick_wins": {"max_items": 1, "min_impressions": 10, "position_min": 8, "position_max": 30, "max_ctr": 0.02},
        "effort_scale": {"title_meta_rewrite": 2, "add_internal_links": 2},
    }
    opportunities = [
        {"url": "/communities/high-impressions", "clicks": 0, "impressions": 100, "ctr": 0.0, "position": 12.0, "primary_queries": [], "recommended_action": "Rewrite the page title"},
        {"url": "/communities/low-impressions", "clicks": 0, "impressions": 20, "ctr": 0.01, "position": 15.0, "primary_queries": [], "recommended_action": "Expand content"},
        {"url": "/communities/high-ctr", "clicks": 5, "impressions": 50, "ctr": 0.1, "position": 10.0, "primary_queries": [], "recommended_action": "Expand content"},
    ]
    result = rankings.find_quick_wins(opportunities, content_rules)
    # high-ctr is excluded by the max_ctr filter; the cap keeps only the
    # higher-impression survivor of the two that qualify.
    assert len(result) == 1
    assert result[0]["url"] == "/communities/high-impressions"
