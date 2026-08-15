from src.formatter import render_plain_text, to_html_email


def test_bold_converted() -> None:
    briefing = {
        "date": "2026年06月06日 星期六",
        "headline": "Test",
        "sections": {
            "geo": ["• **AMD** momentum"],
            "finance": [],
            "tech": [],
            "ai_tech": [],
            "ai_tools": [],
            "social": [],
        },
        "keywords": ["AMD"],
    }

    html = to_html_email(briefing)
    assert "<strong>AMD</strong>" in html


def test_no_unsafe_html() -> None:
    briefing = {
        "date": "2026年06月06日 星期六",
        "headline": "Test",
        "sections": {
            "geo": ["• <script>alert(1)</script> **safe**"],
            "finance": [],
            "tech": [],
            "ai_tech": [],
            "ai_tools": [],
            "social": [],
        },
        "keywords": ["safe"],
    }

    html = to_html_email(briefing)
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_source_link_converted() -> None:
    briefing = {
        "date": "2026年06月06日 星期六",
        "headline": "Test",
        "sections": {
            "geo": ["• 全球市場更新 [來源](https://example.com/article)"],
            "finance": [],
            "tech": [],
            "ai_tech": [],
            "ai_tools": [],
            "social": [],
        },
        "keywords": ["source"],
    }

    html = to_html_email(briefing)
    assert '<a href="https://example.com/article"' in html


def test_javascript_url_not_linked() -> None:
    briefing = {
        "date": "2026年06月06日 星期六",
        "headline": "Test",
        "sections": {
            "geo": ["• 全球市場更新 [來源](javascript:alert(1))"],
            "finance": [],
            "tech": [],
            "ai_tech": [],
            "ai_tools": [],
            "social": [],
        },
        "keywords": ["source"],
    }

    html = to_html_email(briefing)
    assert 'href="javascript:alert(1)"' not in html
    assert "<a " not in html


def test_plain_text_keeps_markdown_bold_and_uses_bare_urls() -> None:
    briefing = {
        "date": "2026年06月06日 星期六",
        "headline": "Test",
        "watchlist": ["• **Watchlist** [來源](https://example.com/watchlist)"],
        "retail_hospitality_ai": ["• **Industry** [來源](https://example.com/industry)"],
        "pos_kiosk_dynamics": ["• **POS** [來源](https://example.com/pos)"],
        "sections": {
            "geo": ["• **Geo** [來源](https://example.com/geo)"],
            "finance": [],
            "tech": [],
            "ai_tech": [],
            "ai_tools": [],
            "social": [],
            "competitors": ["• **Competitor** [來源](https://example.com/competitor)"],
        },
        "keywords": ["source"],
    }

    plain_text = render_plain_text(briefing)

    assert "**Watchlist**" in plain_text
    assert "https://example.com/watchlist" in plain_text
    assert "[來源](https://example.com/watchlist)" not in plain_text
    assert "<strong>" not in plain_text
    assert "<a href" not in plain_text
    assert "</a>" not in plain_text
    assert 'target="_blank"' not in plain_text
