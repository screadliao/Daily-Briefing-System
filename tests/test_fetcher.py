from src.fetcher import RawArticle, clean_text, fetch_all, is_probably_article


def test_clean_text_removes_html_noise() -> None:
    assert clean_text("<p>Hello <b>World</b></p>") == "Hello World"


def test_is_probably_article_rejects_common_noise_paths() -> None:
    assert not is_probably_article("https://example.com/privacy", "example.com")
    assert not is_probably_article("mailto:test@example.com", "example.com")


def test_is_probably_article_accepts_deep_content_paths() -> None:
    assert is_probably_article("https://example.com/news/today-market-wrap", "example.com")


def test_fetch_all_deduplicates(monkeypatch) -> None:
    sources = {
        "geo": {
            "label": "Geo",
            "feeds": ["https://feed-one.example/rss", "https://feed-two.example/rss"],
            "scrape": [],
        }
    }

    def fake_fetch_feed(feed_url: str, category: str, limit: int = 5) -> list[RawArticle]:
        return [
            RawArticle(category=category, source=feed_url, title="One", url="https://same.example/item"),
            RawArticle(category=category, source=feed_url, title="Two", url=f"{feed_url}/unique"),
        ]

    monkeypatch.setattr("src.fetcher.fetch_feed", fake_fetch_feed)

    result = fetch_all(sources=sources, client=object())

    urls = [item["url"] for item in result["geo"]]
    assert urls.count("https://same.example/item") == 1
    assert len(urls) == 3
