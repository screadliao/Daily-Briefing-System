from src.formatter import to_html_email


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
