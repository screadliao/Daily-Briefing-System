"""Briefing entry normalisation.

An entry is a dict: title, summary, source, url, published, why_it_matters.
Older briefings (and occasionally the LLM) emit plain strings such as
"• **標題**：內文 [來源](https://...)"; those are converted so every consumer
can rely on one shape.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

ENTRY_FIELDS = ("title", "summary", "source", "url", "published", "why_it_matters")

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
_BARE_URL = re.compile(r"https?://[^\s)\]>]+")
_LEAD_BOLD = re.compile(r"^\s*[•·]?\s*\*\*(.+?)\*\*\s*[：:]?\s*(.*)$", re.DOTALL)

ENTRY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "標題，簡短點出主體與事件"},
        "summary": {"type": "string", "description": "1–3 句摘要，含關鍵數字/主體，只能依來源內容"},
        "source": {"type": "string", "description": "來源名稱（媒體或機構）"},
        "url": {"type": "string", "description": "原始文章 URL，必須取自提供的文章，不可自行編造"},
        "published": {"type": "string", "description": "發布時間（來源有提供才填，否則空字串）"},
        "why_it_matters": {
            "type": "string",
            "description": "一句話：對零售 POS/Kiosk/SCO 硬體供應商的意涵，只能依該則內容推論",
        },
    },
    "required": ["title", "summary", "source", "url", "published", "why_it_matters"],
}


def safe_url(value: Any) -> str:
    """Only http(s) URLs survive (blocks javascript:, data:, etc.)."""
    text = str(value or "").strip()
    return text if re.match(r"^https?://\S+$", text, re.IGNORECASE) else ""


def source_from_url(url: str) -> str:
    host = urlsplit(url).netloc.lower() if url else ""
    return host[4:] if host.startswith("www.") else host


def _clean(value: Any) -> str:
    return _BOLD.sub(r"\1", str(value or "")).strip()


def normalize_entry(item: Any) -> dict[str, str] | None:
    """Coerce a string or dict to the entry shape; None when there is no content."""
    if isinstance(item, dict):
        entry = {field: _clean(item.get(field)) for field in ENTRY_FIELDS}
        entry["url"] = safe_url(item.get("url"))
        if not entry["title"] and entry["summary"]:
            entry["title"], entry["summary"] = entry["summary"], ""
        if not entry["title"]:
            return None
        if not entry["source"]:
            entry["source"] = source_from_url(entry["url"])
        return entry
    if isinstance(item, str) and item.strip():
        text = item.strip()
        link = _LINK.search(text)
        url = safe_url(link.group(2)) if link else ""
        text = _LINK.sub("", text)
        if not url:
            bare = _BARE_URL.search(text)
            if bare:
                url = safe_url(bare.group(0).rstrip(".,;，。；"))
        if url:
            text = text.replace(url, "")
        text = text.strip()
        lead = _LEAD_BOLD.match(text)
        if lead:
            title, summary = lead.group(1).strip(), lead.group(2).strip()
        else:
            title, summary = re.sub(r"^\s*[•·]\s*", "", text).strip(), ""
        title, summary = _clean(title), _clean(summary)
        if not title:
            return None
        return {
            "title": title,
            "summary": summary,
            "source": source_from_url(url),
            "url": url,
            "published": "",
            "why_it_matters": "",
        }
    return None


def normalize_entries(value: Any) -> list[dict[str, str]]:
    """Section value → list of entries, tolerating a bare string/dict from the LLM."""
    if isinstance(value, (str, dict)):
        value = [value]
    if not isinstance(value, list):
        return []
    return [entry for entry in (normalize_entry(item) for item in value) if entry]


def entry_text(entry: Any) -> str:
    """Flatten an entry (dict or legacy string) to one searchable string."""
    if isinstance(entry, dict):
        return " ".join(str(entry.get(field, "")) for field in ENTRY_FIELDS)
    return str(entry)


def entry_url(entry: Any) -> str | None:
    """First http(s) URL of an entry (dict or legacy string)."""
    if isinstance(entry, dict):
        return safe_url(entry.get("url")) or None
    match = re.search(r"https?://\S+", str(entry))
    return match.group(0) if match else None
