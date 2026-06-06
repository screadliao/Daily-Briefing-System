from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.sources import SOURCES

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")


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
    section_payload = briefing.get("sections", {})
    return [
        {
            "key": key,
            "label": config["label"],
            "entries": [format_entry_html(item) for item in section_payload.get(key, [])],
        }
        for key, config in SOURCES.items()
    ]


def format_entry_html(item: str) -> str:
    escaped = html.escape(item)
    return BOLD_PATTERN.sub(r"<strong>\1</strong>", escaped)
