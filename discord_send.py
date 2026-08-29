#!/usr/bin/env python3
"""Send the Daily Briefing to a Discord channel as structured Embed cards.

Reads latest.json (the structured briefing output) and posts it to the
configured Discord webhook. Each section becomes its own Embed so every
category gets its own accent color on the left-hand color bar.

Layout: one section per Embed (a "wide" stacked card list). Discord does NOT
support per-field colors inside a single embed, so giving each section its own
color requires one embed per section (Discord allows up to 10 embeds per
message).

Usage:
    python3 discord_send.py [--webhook URL] [--json PATH] [--preview-json OUT]

Discord rejects python-urllib's default User-Agent (Cloudflare 1010), so we
send a browser-like User-Agent header.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_JSON = PROJECT_ROOT / "latest.json"
DEFAULT_ENV = PROJECT_ROOT / ".env"

BOLD_RE = re.compile(r"\*\*(.+?)\*\*")

# Discord limits
MAX_TITLE = 256
MAX_DESC = 4096
MAX_NAME = 256
MAX_FIELD_VALUE = 1024
MAX_EMBEDS = 9

# Default accent (used for the header embed and any uncategorized section).
ACCENT_BLUE = 3447003

# Per-category accent colors (see https://gist.github.com/thomasbnt/b6f455e2c7d743b796917fa3c637f3c7)
SECTION_COLORS = {
    "watchlist": 15844367,          # orange
    "geo": 15548997,                # red
    "finance": 3066993,             # green
    "tech": 3447003,                # blue
    "medical_imaging": 10181046,    # purple
    "ai_tech": 1752220,             # teal
    "ai_tools": 15105570,           # pink
    "social": 15844367,             # yellow
    "competitors": 15158332,        # gray
    "retail_hospitality_ai": 15844367,  # orange
    "pos_kiosk_dynamics": 15105570,     # pink
    "retail_market_data": 3066993,      # green
}


def _strip_md(text: str) -> str:
    return BOLD_RE.sub(r"\1", text)


def _extract_url(entry: str) -> str | None:
    m = re.search(r"https?://\S+", entry)
    return m.group(0).rstrip(".,;，。；)】") if m else None


def _format_entry(entry: str, max_len: int = 520) -> str:
    text = entry.strip()
    text = re.sub(r"^\s*[•·]\s*", "", text)
    text = re.sub(r"\[([^\]]*)\]\((https?://[^)]+)\)", r"\1 \2", text)
    url = _extract_url(text)
    if url:
        text = text.replace(url, "").replace("  ", " ").strip()
    clean = text
    if len(clean) > max_len:
        clean = clean[: max_len - 1].rstrip() + "…"
    return f"{clean}\n{url}" if url else clean


def _section_color(section: dict) -> int:
    key = section.get("key")
    return SECTION_COLORS.get(key or "", ACCENT_BLUE)


def build_embeds(briefing: dict) -> list[dict]:
    """Return one embed per section, each with its own accent color."""
    date = briefing.get("date") or ""
    embeds: list[dict] = []

    # Header embed: headline + keywords
    headline = _strip_md(briefing.get("headline", "")).strip()
    title = headline[:MAX_TITLE] if headline else "Daily Briefing"
    header_desc_parts = []
    if headline:
        header_desc_parts.append(f"**{title}**")
    keywords = briefing.get("keywords") or []
    if keywords:
        header_desc_parts.append("關鍵字：`" + "`、`".join(keywords[:4]) + "`")
    header_desc = "\n".join(header_desc_parts)[:MAX_DESC]
    header: dict = {
        "title": title,
        "color": ACCENT_BLUE,
        "footer": {"text": date},
    }
    if header_desc:
        header["description"] = header_desc
    embeds.append(header)

    # One embed per non-empty section
    for section in briefing.get("sections", []):
        label = section.get("label") or section.get("key") or "Section"
        entries = section.get("entries") or []
        if not entries:
            continue
        if len(embeds) >= MAX_EMBEDS:
            logging.warning("embed 數量已達上限，捨棄版面：%s", label)
            break
        # Keep each section's embed under Discord's 6000-char limit: cap the
        # number of bullets and their length.
        value_lines = [_format_entry(e, max_len=180) for e in entries[:4]]
        value = "\n".join(value_lines)[:MAX_FIELD_VALUE]
        embeds.append({
            "title": label[:MAX_NAME],
            "description": value or "—",
            "color": _section_color(section),
            "footer": {"text": date},
        })

    return embeds


def send_embeds(url: str, embeds: list[dict]) -> int:
    payload = {"embeds": embeds}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            ),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Discord webhook HTTP {e.code}: {e.read().decode()[:300]}") from e


def main() -> int:
    if load_dotenv is not None:
        load_dotenv(DEFAULT_ENV)
    parser = argparse.ArgumentParser(description="Post Daily Briefing as Discord embeds.")
    parser.add_argument("--webhook", default=os.getenv("DISCORD_WEBHOOK_URL"))
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="Path to latest.json")
    parser.add_argument("--preview-json", type=Path, help="Write embed payload to this file instead of sending")
    args = parser.parse_args()

    if not args.json.exists():
        print(f"briefing json not found: {args.json}", file=sys.stderr)
        return 1

    briefing = json.loads(args.json.read_text(encoding="utf-8"))
    embeds = build_embeds(briefing)

    if args.preview_json:
        args.preview_json.write_text(
            json.dumps({"embeds": embeds}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"preview written to {args.preview_json} (embeds: {len(embeds)})")
        return 0

    if not args.webhook:
        print("no webhook URL (set --webhook or DISCORD_WEBHOOK_URL)", file=sys.stderr)
        return 1

    status = send_embeds(args.webhook, embeds)
    print(f"sent: HTTP {status} (embeds: {len(embeds)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
