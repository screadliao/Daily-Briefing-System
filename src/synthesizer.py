from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from typing import Any

from src.sources import SOURCES

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None


SYSTEM_PROMPT = """你是一個專業早報撰稿人，為台灣科技公司 PM Head 提供每日簡報。
讀者背景：
- 任職安防監控 IP Camera ODM（Ambarella CV72/CV75 平台），客戶為歐美日安防大廠
- 同時負責 ICG 醫療螢光影像新創，規劃全球市場進入
- 核心關注：台灣科技、半導體供應鏈、中美台地緣、安防/AI視覺、Ambarella / NVIDIA 動態

輸出規則：
1. 繁體中文，英文技術名詞保留英文
2. 每個分類 2–4 條，每條 25–50 字，以「•」開頭
3. 重點名詞用 **XXX** 標記
4. 只輸出 JSON，不加 markdown code block 或任何說明文字

JSON schema：
{
  "date": "YYYY年MM月DD日 星期X",
  "headline": "今日最重要一件事（15字內）",
  "sections": {
    "geo":      ["• ...", "• ..."],
    "finance":  ["• ...", "• ..."],
    "tech":     ["• ...", "• ..."],
    "ai_tech":  ["• ...", "• ..."],
    "ai_tools": ["• ...", "• ..."],
    "social":   ["• ...", "• ..."]
  },
  "keywords": ["關鍵字1", "關鍵字2", "關鍵字3", "關鍵字4"]
}"""

WEEKDAYS = "一二三四五六日"


def synthesize(raw_articles: dict[str, list[dict[str, str]]], today: datetime | None = None) -> dict[str, Any]:
    today = today or datetime.now()
    today_str = format_tw_date(today)
    article_dump = format_articles_for_prompt(raw_articles)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic is None or not api_key:
        return build_fallback_briefing(raw_articles, today_str)

    client = anthropic.Anthropic(api_key=api_key)
    prompt = f"今天是 {today_str}。以下是今日抓取的文章，請產出早報 JSON：\n\n{article_dump}"

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2500,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = message.content[0].text
            return extract_json(raw_text)
        except Exception as exc:  # pragma: no cover
            last_error = exc
            if attempt < 2:
                time.sleep(2**attempt)

    if last_error is not None and os.getenv("DRY_RUN", "").lower() == "true":
        return build_fallback_briefing(raw_articles, today_str)
    raise RuntimeError(f"Claude API failed after retries: {last_error}") from last_error


def format_articles_for_prompt(raw_articles: dict[str, list[dict[str, str]]]) -> str:
    lines: list[str] = []
    for category, config in SOURCES.items():
        label = config["label"]
        items = raw_articles.get(category, [])
        lines.append(f"[{category}] {label}")
        if not items:
            lines.append("- 無新資訊")
            continue
        for item in items[:12]:
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            summary = item.get("summary", "").strip()
            if summary:
                lines.append(f"- {title} | {url} | {summary[:180]}")
            else:
                lines.append(f"- {title} | {url}")
        lines.append("")
    return "\n".join(lines).strip()


def extract_json(raw_text: str) -> dict[str, Any]:
    candidate = raw_text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if not match:
            raise ValueError("Model response does not contain JSON object.")
        return json.loads(match.group(0))


def format_tw_date(today: datetime) -> str:
    weekday = WEEKDAYS[today.weekday()]
    return f"{today:%Y年%m月%d日} 星期{weekday}"


def build_fallback_briefing(
    raw_articles: dict[str, list[dict[str, str]]],
    today_str: str,
) -> dict[str, Any]:
    sections: dict[str, list[str]] = {}
    keyword_seed: list[str] = []

    for category in SOURCES:
        items = raw_articles.get(category, [])
        bullets: list[str] = []
        for item in items[:3]:
            title = item.get("title", "未命名文章")
            source = item.get("source", "")
            source_name = source.split("/")[2] if "://" in source else source
            bullets.append(f"• **{title[:28]}**；來源 {source_name}，建議追蹤原文與後續市場反應。")
            keyword_seed.extend(extract_keywords(title))
        if not bullets:
            bullets = ["• 今日此分類暫無明顯新訊，可延續觀察既有議題與主要供應鏈動態。"]
        sections[category] = bullets

    keywords = unique_preserve_order(keyword_seed)[:4] or ["台灣科技", "半導體", "AI", "供應鏈"]
    headline = pick_headline(raw_articles)
    return {
        "date": today_str,
        "headline": headline,
        "sections": sections,
        "keywords": keywords,
    }


def extract_keywords(title: str) -> list[str]:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff ]+", " ", title)
    tokens = [token for token in cleaned.split() if len(token) >= 2]
    return tokens[:3]


def unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def pick_headline(raw_articles: dict[str, list[dict[str, str]]]) -> str:
    for category in ("tech", "ai_tech", "finance", "geo", "ai_tools", "social"):
        items = raw_articles.get(category, [])
        if items:
            return items[0].get("title", "今日重點整理")[:15]
    return "今日重點整理"
