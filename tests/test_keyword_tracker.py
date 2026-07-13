from src import keyword_tracker

BASE_URL = "https://www.example.com"


def test_build_keyword_groups_excludes_explicit_cities():
    keywords_cfg = {
        "explicit_groups": {"JUPITER": ["jupiter homes for sale"]},
        "city_keyword_template": ["{city} homes for sale"],
        "template_excludes": ["jupiter"],
    }
    cities_cfg = {"cities": [{"slug": "jupiter", "name": "Jupiter"}, {"slug": "stuart", "name": "Stuart"}]}
    groups = keyword_tracker.build_keyword_groups(keywords_cfg, cities_cfg)
    assert groups["JUPITER"] == ["jupiter homes for sale"]
    assert groups["STUART"] == ["stuart homes for sale"]


def test_missing_keyword_reports_no_visibility_not_not_ranking():
    results = keyword_tracker.track_keyword_group(["ghost town homes for sale"], [], BASE_URL, {})
    assert results[0]["status"] == keyword_tracker.NO_VISIBILITY
    assert results[0]["current_position"] is None


def test_matched_keyword_picks_best_position_and_page():
    query_pages = [
        {"query": "jupiter homes for sale", "page": "https://www.example.com/communities/jupiter", "clicks": 5, "impressions": 100, "ctr": 0.05, "position": 12.0},
        {"query": "jupiter homes for sale", "page": "https://www.example.com/blog/jupiter", "clicks": 1, "impressions": 20, "ctr": 0.05, "position": 4.0},
    ]
    results = keyword_tracker.track_keyword_group(["jupiter homes for sale"], query_pages, BASE_URL, {})
    assert results[0]["current_position"] == 4.0
    assert results[0]["ranking_page"] == "/blog/jupiter"
    assert results[0]["status"] == "page 1"


def test_status_reflects_climbing_and_slipping():
    query_pages = [{"query": "x", "page": "https://www.example.com/x", "clicks": 0, "impressions": 10, "ctr": 0.0, "position": 5.0}]
    climbing = keyword_tracker.track_keyword_group(["x"], query_pages, BASE_URL, {"x": 9.0})
    assert climbing[0]["status"] == "climbing"

    query_pages_worse = [{"query": "x", "page": "https://www.example.com/x", "clicks": 0, "impressions": 10, "ctr": 0.0, "position": 15.0}]
    slipping = keyword_tracker.track_keyword_group(["x"], query_pages_worse, BASE_URL, {"x": 9.0})
    assert slipping[0]["status"] == "slipping"
