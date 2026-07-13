from src import city_scorecards

BASE_URL = "https://www.example.com"
SEARCH_PLATFORM = "https://search.example.com"

CITIES_CFG = {
    "blog_template": ["local-guide-to-{city}-florida"],
    "cities": [
        {
            "name": "Jupiter",
            "slug": "jupiter",
            "tier": 1,
            "extra_detail": True,
            "known_communities": [{"slug": "abacoa", "name": "Abacoa", "tags": ["master-planned"], "confidence": "high"}],
        },
        {"name": "Stuart", "slug": "stuart", "tier": 3, "extra_detail": False, "known_communities": []},
    ],
}


def test_classify_communities_uses_known_mapping():
    sitemap_urls = [f"{BASE_URL}/communities/abacoa"]
    crawl_index = {}
    assignments, unmapped = city_scorecards.classify_communities(CITIES_CFG, sitemap_urls, crawl_index, BASE_URL)
    assert len(assignments["jupiter"]) == 1
    assert assignments["jupiter"][0]["slug"] == "abacoa"
    assert unmapped == []


def test_classify_communities_auto_detects_single_city_match():
    url = f"{BASE_URL}/communities/some-new-place"
    sitemap_urls = [url]
    crawl_index = {url: {"title": "Some New Place in Stuart, FL", "h1_tags": [], "body_text": ""}}
    assignments, unmapped = city_scorecards.classify_communities(CITIES_CFG, sitemap_urls, crawl_index, BASE_URL)
    assert len(assignments["stuart"]) == 1
    assert assignments["stuart"][0]["confidence"] == "auto"
    assert unmapped == []


def test_classify_communities_flags_ambiguous_as_unmapped():
    url = f"{BASE_URL}/communities/ambiguous-place"
    sitemap_urls = [url]
    crawl_index = {url: {"title": "A community near Jupiter and Stuart, FL", "h1_tags": [], "body_text": ""}}
    assignments, unmapped = city_scorecards.classify_communities(CITIES_CFG, sitemap_urls, crawl_index, BASE_URL)
    assert assignments["jupiter"] == []
    assert assignments["stuart"] == []
    assert len(unmapped) == 1
    assert set(unmapped[0]["candidate_cities"]) == {"Jupiter", "Stuart"}


def test_broken_main_page_is_not_counted_as_present_or_scored():
    sitemap_urls = [f"{BASE_URL}/communities/jupiter", f"{BASE_URL}/communities/abacoa"]
    crawl_index = {f"{BASE_URL}/communities/jupiter": {"status": 404}}
    scorecards, _ = city_scorecards.build_city_scorecards(
        CITIES_CFG, sitemap_urls, crawl_index, [], [], [], BASE_URL, SEARCH_PLATFORM
    )
    jupiter = next(c for c in scorecards if c["slug"] == "jupiter")
    # Sitemap listing alone isn't enough — the crawl confirms this URL 404s,
    # so it must not be reported as a live main city page...
    assert jupiter["main_city_page_present"] is False
    assert "Main city page" in jupiter["weak_categories"]
    # ...and a broken page must not be scored (credited OR penalized) for
    # internal linking / search-site integration — those aren't evaluable
    # without a real page to inspect, so they're excluded, not zeroed out.
    assert "Internal linking" not in jupiter["weak_categories"]
    assert "search.doyouneedahome.com integration" not in jupiter["weak_categories"]
