from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.fetcher import RawArticle, fetch_issue_page, parse_issue_page


FIXTURE = Path(__file__).parent / "fixtures" / "fuly_issue.html"
ISSUE_URL = "https://news.fuly.ai/ai-news-2026-11-08"


def test_parse_issue_page_returns_each_story_and_lead() -> None:
    articles = parse_issue_page(FIXTURE.read_text(encoding="utf-8"), ISSUE_URL, "ai_tech")

    assert len(articles) >= 10
    assert articles[0].url == ISSUE_URL
    for article in articles[1:]:
        assert article.title and article.summary
        assert article.url.startswith("http") and "news.fuly.ai" not in article.url
        assert article.source.startswith("FulyAI / ")


def test_fetch_issue_page_falls_back_to_rss_when_no_stories(monkeypatch) -> None:
    fallback = RawArticle("ai_tech", "https://news.fuly.ai/feed.xml", "當期標題", ISSUE_URL, "RSS 一行摘要")

    class Response:
        text = "<html><body>no stories</body></html>"

        def raise_for_status(self) -> None:
            pass

    class Client:
        def get(self, url: str) -> Response:
            return Response()

    monkeypatch.setattr("src.fetcher.fetch_feed", lambda *args: [fallback])

    assert fetch_issue_page(Client(), "https://news.fuly.ai/feed.xml", "ai_tech") == [fallback]
