from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any, Callable

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
    for section in build_sections_for_plain_text(briefing):
        lines.append(section["label"])
        lines.extend(section["entries"])
        lines.append("")
    lines.append("關鍵字：" + "、".join(briefing.get("keywords", [])))
    return "\n".join(lines).strip()


def build_sections_for_view(briefing: dict[str, Any]) -> list[dict[str, Any]]:
    return _build_sections(briefing, format_entry_html)


def build_sections_for_plain_text(briefing: dict[str, Any]) -> list[dict[str, Any]]:
    return _build_sections(briefing, format_entry_plain_text)


def _build_sections(
    briefing: dict[str, Any], format_entry: Callable[[str], str]
) -> list[dict[str, Any]]:
    sections = []

    watchlist_entries = briefing.get("watchlist", [])
    if watchlist_entries:
        sections.append({
            "key": "watchlist",
            "label": "追蹤議題更新",
            "entries": [format_entry(item) for item in watchlist_entries],
        })

    retail_hospitality_ai_entries = briefing.get("retail_hospitality_ai", [])
    if retail_hospitality_ai_entries:
        sections.append({
            "key": "retail_hospitality_ai",
            "label": "場域AI應用",
            "entries": [format_entry(item) for item in retail_hospitality_ai_entries],
        })

    pos_kiosk_dynamics_entries = briefing.get("pos_kiosk_dynamics", [])
    if pos_kiosk_dynamics_entries:
        sections.append({
            "key": "pos_kiosk_dynamics",
            "label": "硬體/競品",
            "entries": [format_entry(item) for item in pos_kiosk_dynamics_entries],
        })

    retail_market_data_entries = briefing.get("retail_market_data", [])
    if retail_market_data_entries:
        sections.append({
            "key": "retail_market_data",
            "label": "市場研調數據",
            "entries": [format_entry(item) for item in retail_market_data_entries],
        })

    section_payload = briefing.get("sections", {})
    if not isinstance(section_payload, dict):
        section_payload = {}
    sections.extend([
        {
            "key": key,
            "label": config["label"],
            "entries": [format_entry(item) for item in _as_entries(section_payload.get(key))],
        }
        for key, config in SOURCES.items()
        if key != "pos_kiosk_dynamics"
    ])

    return sections


def _as_entries(value) -> list:
    """Coerce a section value to a list of strings, tolerating LLM quirks
    (occasionally a section is a plain string instead of a list)."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, str) and value.strip():
        # Some model outputs put a single bullet in a string; normalize it.
        return [value]
    return []


def format_entry_html(item: str) -> str:
    escaped = html.escape(item)
    with_bold = BOLD_PATTERN.sub(r"<strong>\1</strong>", escaped)
    return LINK_PATTERN.sub(r'<a href="\2" target="_blank" rel="noopener">\1</a>', with_bold)


def format_entry_plain_text(item: str) -> str:
    return LINK_PATTERN.sub(r"\2", item)
