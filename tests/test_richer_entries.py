import json

from discord_send import build_embeds
from src.entries import normalize_entry
from src.formatter import build_sections_for_plain_text, render_plain_text, to_html_email
from src.synthesizer import collect_prompt_articles, ground_briefing

ENTRY = {
    "title": "Zebra 發表新一代 SCO",
    "summary": "Zebra 推出自助結帳機，主打 AI 防損。",
    "source": "Retail Tech",
    "url": "https://news.example/zebra?utm_source=x",
    "published": "model-invented",
    "why_it_matters": "競品進入同一 SCO 市場。",
}
BRIEFING = {
    "date": "2026年11月02日 星期一",
    "headline": "H",
    "keywords": ["k"],
    "pos_kiosk_dynamics": [ENTRY],
    "sections": {"geo": [], "finance": [], "ai_tech": [], "ai_tools": [], "social": []},
}


def test_normalize_legacy_string() -> None:
    entry = normalize_entry("• **AMD**：動能 [來源](https://a.example/x)")
    assert entry["title"] == "AMD" and entry["summary"] == "動能"
    assert entry["url"] == "https://a.example/x" and entry["why_it_matters"] == ""


def test_normalize_drops_unsafe_url_and_empty() -> None:
    assert normalize_entry({"title": "t", "url": "javascript:alert(1)"})["url"] == ""
    assert normalize_entry({"title": "", "summary": ""}) is None


def test_object_entries_render_everywhere() -> None:
    sections = build_sections_for_plain_text(BRIEFING)
    assert sections[0]["key"] == "pos_kiosk_dynamics"
    assert set(sections[0]["entries"][0]) == {"title", "summary", "source", "url", "published", "why_it_matters"}
    text = render_plain_text(BRIEFING)
    assert "競品進入同一 SCO 市場" in text and "https://news.example/zebra" in text
    html = to_html_email(BRIEFING)
    assert 'href="https://news.example/zebra' in html and "section--pos_kiosk_dynamics" in html
    json.dumps(sections, ensure_ascii=False)


def test_ground_drops_fabricated_urls_and_takes_published_from_article() -> None:
    known = collect_prompt_articles(
        {"geo": [{"url": "https://news.example/zebra", "published": "2 hours ago", "title": "t"}]}
    )
    fake = dict(ENTRY, url="https://invented.example/nope")
    briefing = {"pos_kiosk_dynamics": [ENTRY, fake], "sections": {"geo": ["• **x** https://nowhere.example/z"]}}
    out = ground_briefing(briefing, known)
    assert [e["url"] for e in out["pos_kiosk_dynamics"]] == ["https://news.example/zebra?utm_source=x"]
    assert out["pos_kiosk_dynamics"][0]["published"] == "2 hours ago"
    assert out["sections"]["geo"] == []


def test_discord_accepts_object_entries_and_distinct_colors() -> None:
    sections = build_sections_for_plain_text(BRIEFING)
    embeds = build_embeds({"date": "d", "headline": "H", "keywords": [], "sections": sections})
    assert "**Zebra 發表新一代 SCO**" in embeds[1]["description"]
    assert "https://news.example/zebra" in embeds[1]["description"]
    from discord_send import SECTION_COLORS
    assert len(set(SECTION_COLORS.values())) == len(SECTION_COLORS)
