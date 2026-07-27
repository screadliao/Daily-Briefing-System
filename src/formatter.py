from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.sources import SOURCES

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")


def to_html_email(briefing: dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("email.html")
    sections = build_sections_for_view(briefing)
    return template.render(briefing=briefing, sections=sections)


def render_plain_text(briefing: dict[str, Any]) -> str:
    lines = [f"{briefing['date']} | {briefing['headline']}", ""]
    for section in build_sections_for_view(briefing):
        lines.append(section["label"])
        lines.extend(section["entries"])
        lines.append("")
    lines.append("關鍵字：" + "、".join(briefing.get("keywords", [])))
    return "\n".join(lines).strip()


def build_sections_for_view(briefing: dict[str, Any]) -> list[dict[str, Any]]:
    sections = []

    watchlist_entries = briefing.get("watchlist", [])
    if watchlist_entries:
        sections.append({
            "key": "watchlist",
            "label": "追蹤議題更新",
            "entries": [format_entry_html(item) for item in watchlist_entries],
        })

    industry_trends_entries = briefing.get("industry_trends", [])
    if industry_trends_entries:
        sections.append({
            "key": "industry_trends",
            "label": "AI 零售 / 餐飲 / Hotel 應用趨勢",
            "entries": [format_entry_html(item) for item in industry_trends_entries],
        })

    pos_competitors_entries = briefing.get("pos_competitors", [])
    if pos_competitors_entries:
        sections.append({
            "key": "pos_competitors",
            "label": "POS / Kiosk / Self-checkout 競品動態",
            "entries": [format_entry_html(item) for item in pos_competitors_entries],
        })

    section_payload = briefing.get("sections", {})
    sections.extend([
        {
            "key": key,
            "label": config["label"],
            "entries": [format_entry_html(item) for item in section_payload.get(key, [])],
        }
        for key, config in SOURCES.items()
    ])

    competitors_entries = section_payload.get("competitors", [])
    if competitors_entries:
        sections.append({
            "key": "competitors",
            "label": "競品 / 安防產業動態 (LinkedIn)",
            "entries": [format_entry_html(item) for item in competitors_entries],
        })

    return sections


def format_entry_html(item: str) -> str:
    escaped = html.escape(item)
    with_bold = BOLD_PATTERN.sub(r"<strong>\1</strong>", escaped)
    return LINK_PATTERN.sub(r'<a href="\2" target="_blank" rel="noopener">\1</a>', with_bold)
