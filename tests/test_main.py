from pathlib import Path

import main


def test_main_filters_seen_urls_and_writes_state(monkeypatch, tmp_path, capsys) -> None:
    raw_articles = {
        "geo": [
            {"title": "Seen raw", "url": "https://seen.example/raw"},
            {"title": "Fresh raw", "url": "https://fresh.example/raw"},
            {"title": "No url raw"},
        ],
        "finance": [],
    }
    brave_articles = [
        {"title": "Seen brave", "url": "https://seen.example/brave"},
        {"title": "Fresh brave", "url": "https://fresh.example/brave"},
    ]
    linkedin_articles = [
        {"title": "Fresh linkedin", "url": "https://fresh.example/linkedin"},
    ]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["main.py", "--dry-run", "--save-html", "preview.html"])
    monkeypatch.setattr("main.fetch_all", lambda: raw_articles)
    monkeypatch.setattr("main.filter_articles", lambda articles, blocklist: articles)
    monkeypatch.setattr("main.search_watchlist", lambda watchlist: brave_articles)
    monkeypatch.setattr("main.search_linkedin", lambda: linkedin_articles)
    monkeypatch.setattr(
        "main.load_seen_urls",
        lambda: {"https://seen.example/raw", "https://seen.example/brave"},
    )
    monkeypatch.setattr(
        "main.synthesize",
        lambda raw, brave, linkedin: {
            "date": "2026年06月30日 星期二",
            "headline": "Test",
            "sections": {"geo": [], "finance": [], "tech": [], "ai_tech": [], "ai_tools": [], "social": []},
            "keywords": ["test"],
            "raw": raw,
            "brave": brave,
            "linkedin": linkedin,
        },
    )
    monkeypatch.setattr("main.to_html_email", lambda briefing: "<html>ok</html>")
    save_calls: list[tuple[set[str], list[dict], Path]] = []
    monkeypatch.setattr(
        "main.save_seen_urls",
        lambda seen, new_articles, site_dir: save_calls.append((set(seen), list(new_articles), site_dir)),
    )

    result = main.main()

    assert result == 0
    assert Path("preview.html").read_text(encoding="utf-8") == "<html>ok</html>"

    captured = capsys.readouterr()
    assert "[dedup] filtered 2/6 articles already seen" in captured.out
    assert save_calls == [
        (
            {"https://seen.example/raw", "https://seen.example/brave"},
            [
                {"title": "Fresh raw", "url": "https://fresh.example/raw"},
                {"title": "No url raw"},
                {"title": "Fresh brave", "url": "https://fresh.example/brave"},
                {"title": "Fresh linkedin", "url": "https://fresh.example/linkedin"},
            ],
            Path("_site"),
        )
    ]


def test_filter_article_list_keeps_missing_url() -> None:
    kept, removed, total = main._filter_article_list(
        [{"title": "A"}, {"title": "B", "url": "https://seen.example"}],
        {"https://seen.example"},
    )

    assert kept == [{"title": "A"}]
    assert removed == 1
    assert total == 2
