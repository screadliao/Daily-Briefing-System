#!/usr/bin/env python3
"""Send the Daily Briefing to a Discord channel as a structured Embed card.

Reads latest.json (the structured briefing output) and posts it to the
configured Discord webhook as an Embed with one field per section.

Usage:
    python3 discord_send.py [--webhook URL] [--json PATH] [--preview-json OUT]

If --webhook is omitted, the DISCORD_WEBHOOK_URL env var is used. If neither
is present, and --preview-json is given, the embed payload is written to that
file instead of being sent (used for local preview without network).

Discord rejects python-urllib's default User-Agent (Cloudflare 1010), so we
send a browser-like User-Agent header.
"""
from __future__ import annotations

import argparse
import json
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

# Discord embed limits
MAX_FIELDS = 25
MAX_TITLE = 256
MAX_DESC = 4096
MAX_NAME = 256
MAX_FIELD_VALUE = 1024

ACCENT_BLUE = 3447003


def _strip_md(text: str) -> str:
    """Remove bold markers; keep it readable for embed titles."""
    return BOLD_RE.sub(r"\1", text)


def _extract_url(entry: str) -> str | None:
    m = re.search(r"https?://\S+", entry)
    return m.group(0).rstrip(".,;，。；)】") if m else None


def _format_entry(entry: str, max_len: int = 900) -> str:
    """Convert a briefing bullet into a clean embed field value.

    Removes the leading bullet, keeps bold, and appends the source link as a
    plain URL (Discord auto-links URLs in embed fields).
    """
    text = entry.strip()
    text = re.sub(r"^\s*[•·]\s*", "", text)
    url = _extract_url(text)
    if url:
        text = text.replace(url, "").replace("  ", " ").strip()
    # Render bold as Discord reads **...** fine inside embed values; keep them.
    clean = text
    if len(clean) > max_len:
        clean = clean[: max_len - 1].rstrip() + "…"
    if url:
        return f"{clean}\n{url}"
    return clean


def build_embed(briefing: dict) -> dict:
    headline = _strip_md(briefing.get("headline", "")).strip()
    title = headline[:MAX_TITLE] if headline else "Daily Briefing"

    description_lines = []
    if headline:
        description_lines.append(f"**{title}**")
    keywords = briefing.get("keywords") or []
    if keywords:
        description_lines.append("關鍵字：`" + "`、`".join(keywords[:4]) + "`")
    description = "\n".join(description_lines)[:MAX_DESC]

    embed: dict = {
        "title": title,
        "description": description or None,
        "color": ACCENT_BLUE,
        "footer": {"text": briefing.get("date") or ""},
        "fields": [],
    }
    # drop empty title/description to keep payload clean
    if not description:
        embed.pop("description", None)

    for section in briefing.get("sections", []):
        label = section.get("label") or section.get("key") or "Section"
        entries = section.get("entries") or []
        if not entries:
            continue
        if len(embed["fields"]) >= MAX_FIELDS:
            break
        value_lines = [_format_entry(e, max_len=220) for e in entries]
        value = "\n".join(value_lines)[:MAX_FIELD_VALUE]
        # Wide layout: mark every field inline so Discord packs adjacent
        # sections side-by-side (roughly 2-3 columns wide) instead of one
        # long vertical stack.
        embed["fields"].append({
            "name": label[:MAX_NAME],
            "value": value or "—",
            "inline": True,
        })

    return embed


def send_embed(url: str, embed: dict) -> int:
    payload = {"embeds": [embed]}
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
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Discord webhook HTTP {e.code}: {e.read().decode()[:300]}") from e


def main() -> int:
    if load_dotenv is not None:
        load_dotenv(DEFAULT_ENV)
    parser = argparse.ArgumentParser(description="Post Daily Briefing as Discord embed.")
    parser.add_argument("--webhook", default=os.getenv("DISCORD_WEBHOOK_URL"))
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="Path to latest.json")
    parser.add_argument("--preview-json", type=Path, help="Write embed payload to this file instead of sending")
    args = parser.parse_args()

    if not args.json.exists():
        print(f"briefing json not found: {args.json}", file=sys.stderr)
        return 1

    briefing = json.loads(args.json.read_text(encoding="utf-8"))
    embed = build_embed(briefing)

    if args.preview_json:
        args.preview_json.write_text(
            json.dumps({"embeds": [embed]}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"preview written to {args.preview_json}")
        return 0

    if not args.webhook:
        print("no webhook URL (set --webhook or DISCORD_WEBHOOK_URL)", file=sys.stderr)
        return 1

    status = send_embed(args.webhook, embed)
    print(f"sent: HTTP {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
