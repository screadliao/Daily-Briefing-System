from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.entries import normalize_entries
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
    for section in build_sections_for_plain_text(briefing):
        lines.append(section["label"])
        for entry in section["entries"]:
            lines.extend(format_entry_lines(entry))
        lines.append("")
    lines.append("關鍵字：" + "、".join(briefing.get("keywords", [])))
    return "\n".join(lines).strip()


def format_entry_lines(entry: dict[str, str]) -> list[str]:
    """Plain-text rendering of one entry; keeps **bold** title and a bare URL."""
    lines = [f"• **{entry['title']}**"]
    if entry.get("summary"):
        lines.append(f"  {entry['summary']}")
    if entry.get("why_it_matters"):
        lines.append(f"  → 對 POS/Kiosk/SCO 的意涵：{entry['why_it_matters']}")
    meta = " ｜ ".join(part for part in (entry.get("source"), entry.get("published")) if part)
    if meta:
        lines.append(f"  來源：{meta}")
    if entry.get("url"):
        lines.append(f"  {entry['url']}")
    return lines


def build_sections_for_view(briefing: dict[str, Any]) -> list[dict[str, Any]]:
    """Sections with entry dicts (template escapes them; only http(s) URLs are kept)."""
    return _build_sections(briefing)


def build_sections_for_plain_text(briefing: dict[str, Any]) -> list[dict[str, Any]]:
    """Sections with entry dicts; also the shape written to latest.json."""
    return _build_sections(briefing)


_TOP_LEVEL_BOARDS = (
    ("watchlist", "追蹤議題更新"),
    ("retail_hospitality_ai", "場域AI應用"),
    ("pos_kiosk_dynamics", "硬體/競品"),
    ("retail_market_data", "市場研調數據"),
)


def _build_sections(briefing: dict[str, Any]) -> list[dict[str, Any]]:
    sections = []

    for key, label in _TOP_LEVEL_BOARDS:
        entries = normalize_entries(briefing.get(key, []))
        if entries:
            sections.append({"key": key, "label": label, "entries": entries})

    section_payload = briefing.get("sections", {})
    if not isinstance(section_payload, dict):
        section_payload = {}
    sections.extend([
        {
            "key": key,
            "label": config["label"],
            "entries": normalize_entries(section_payload.get(key)),
        }
        for key, config in SOURCES.items()
        if key != "pos_kiosk_dynamics"
    ])

    return sections


def format_entry_html(item: str) -> str:
    escaped = html.escape(item)
    with_bold = BOLD_PATTERN.sub(r"<strong>\1</strong>", escaped)
    return LINK_PATTERN.sub(r'<a href="\2" target="_blank" rel="noopener">\1</a>', with_bold)


def format_entry_plain_text(item: str) -> str:
    return LINK_PATTERN.sub(r"\2", item)
