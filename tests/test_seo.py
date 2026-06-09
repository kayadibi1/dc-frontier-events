from aggregator.seo import ROBOTS_TXT, render_sitemap


def test_robots_allows_crawl_but_blocks_api_and_email():
    assert "User-agent: *" in ROBOTS_TXT
    assert "Disallow: /api/" in ROBOTS_TXT
    assert "Disallow: /email/" in ROBOTS_TXT
    assert "Sitemap: https://events.emersus.ai/sitemap.xml" in ROBOTS_TXT


def test_sitemap_lists_real_pages_with_lastmod():
    xml = render_sitemap("2026-06-09")
    assert xml.startswith("<?xml")
    for loc in ("https://events.emersus.ai/",
                "https://events.emersus.ai/map.html",
                "https://events.emersus.ai/digest.html",
                "https://events.emersus.ai/credentials.html"):
        assert f"<loc>{loc}</loc>" in xml
    assert xml.count("<lastmod>2026-06-09</lastmod>") == 4
    assert "status.html" not in xml                  # ops page stays out
