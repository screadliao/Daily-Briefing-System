from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import feedparser
from flask import Flask, jsonify, render_template, request

from src.sources import SOURCES_FILE, load_sources

app = Flask(__name__, template_folder="templates")
PROJECT_ROOT = Path(__file__).resolve().parent


@app.get("/")
def index() -> str:
    return render_template("manage.html")


@app.get("/api/sources")
def get_sources() -> Any:
    return jsonify(load_sources())


@app.post("/api/sources/<category>/add")
def add_source(category: str) -> Any:
    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url", "")).strip()
    source_type = str(payload.get("type", "")).strip()

    if not url or source_type not in {"feed", "scrape"}:
        return jsonify({"error": "Invalid url or type."}), 400

    sources = load_sources()
    if category not in sources:
        return jsonify({"error": "Unknown category."}), 404

    target_key = "feeds" if source_type == "feed" else "scrape"
    bucket = sources[category][target_key]
    if url not in bucket:
        bucket.append(url)
        save_sources(sources)
    return jsonify(sources[category])


@app.post("/api/sources/<category>/remove")
def remove_source(category: str) -> Any:
    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url", "")).strip()
    if not url:
        return jsonify({"error": "Missing url."}), 400

    sources = load_sources()
    if category not in sources:
        return jsonify({"error": "Unknown category."}), 404

    removed = False
    for target_key in ("feeds", "scrape"):
        bucket = sources[category][target_key]
        if url in bucket:
            bucket.remove(url)
            removed = True

    if removed:
        save_sources(sources)
    return jsonify({"removed": removed, "category": sources[category]})


@app.post("/api/test-fetch")
def test_fetch() -> Any:
    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url", "")).strip()
    if not url:
        return jsonify({"error": "Missing url."}), 400

    parsed = feedparser.parse(url)
    titles = [str(entry.get("title", "")).strip() for entry in parsed.entries[:3] if entry.get("title")]
    return jsonify({"titles": titles})


def save_sources(sources: dict[str, Any]) -> None:
    with SOURCES_FILE.open("w", encoding="utf-8") as handle:
        json.dump(sources, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
