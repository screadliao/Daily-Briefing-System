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
    competitor_articles = [
        {"title": "Fresh competitor", "url": "https://fresh.example/competitor"},
    ]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["main.py", "--dry-run", "--save-html", "preview.html"])
    monkeypatch.setattr("main.fetch_all", lambda: raw_articles)
    monkeypatch.setattr("main.filter_articles", lambda articles, blocklist: articles)
    rotated_watchlists: list[list[str]] = []
    monkeypatch.setattr(
        "main.rotate_half",
        lambda topics: rotated_watchlists.append(topics) or topics,
    )

    def search_watchlist(watchlist: list[str]) -> list[dict]:
        if watchlist == main.SECURITY_ICG_COMPETITOR_WATCHLIST:
            return competitor_articles
        return brave_articles

    monkeypatch.setattr("main.search_watchlist", search_watchlist)
    monkeypatch.setattr(
        "main.load_seen_urls",
        lambda: {"https://seen.example/raw", "https://seen.example/brave"},
    )
    monkeypatch.setattr(
        "main.synthesize",
        lambda raw, brave, competitor_articles=None, retail_hospitality_articles=None, pos_competitor_articles=None: {
            "date": "2026年06月30日 星期二",
            "headline": "Test",
            "sections": {"geo": [], "finance": [], "tech": [], "ai_tech": [], "ai_tools": [], "social": []},
            "keywords": ["test"],
            "raw": raw,
            "brave": brave,
            "competitor_articles": competitor_articles,
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
    assert rotated_watchlists == [
        main.RETAIL_HOSPITALITY_WATCHLIST,
        main.POS_COMPETITOR_WATCHLIST,
        main.SECURITY_ICG_COMPETITOR_WATCHLIST,
    ]
    assert Path("preview.html").read_text(encoding="utf-8") == "<html>ok</html>"
    assert Path("latest.txt").read_text(encoding="utf-8") == (
        "2026年06月30日 星期二 | Test\n\n"
        "地緣政治\n\n"
        "金融市場\n\n"
        "科技產業（安防 / 半導體）\n\n"
        "醫療影像（ICG 螢光導引手術）\n\n"
        "AI 技術趨勢\n\n"
        "AI 應用實踐\n\n"
        "X / Reddit 熱議（科技 / 政治 / 世界）\n\n"
        "關鍵字：test"
    )

    captured = capsys.readouterr()
    assert "[dedup] filtered 4/10 articles already seen" in captured.out
    assert save_calls == [
        (
            {"https://seen.example/raw", "https://seen.example/brave"},
            [
                {"title": "Fresh raw", "url": "https://fresh.example/raw"},
                {"title": "No url raw"},
                {"title": "Fresh brave", "url": "https://fresh.example/brave"},
                {"title": "Fresh competitor", "url": "https://fresh.example/competitor"},
                {"title": "Fresh brave", "url": "https://fresh.example/brave"},
                {"title": "Fresh brave", "url": "https://fresh.example/brave"},
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
