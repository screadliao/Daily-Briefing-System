from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from src.sources import SOURCES
from src.watchlist import WATCHLIST

try:
    import openai
except ImportError:  # pragma: no cover
    openai = None


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONTEXT_FILE = _PROJECT_ROOT / "context.md"

_FALLBACK_PROMPT = """你是一個專業早報撰稿人，為台灣科技公司 PM Head 提供每日簡報。請只輸出符合指定 schema 的 JSON。"""


def load_context_md() -> str:
    if _CONTEXT_FILE.exists():
        return _CONTEXT_FILE.read_text(encoding="utf-8").strip()
    return _FALLBACK_PROMPT


SYSTEM_PROMPT = load_context_md()

BRIEFING_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "produce_briefing",
        "description": "產出今日早報結構化資料",
        "parameters": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "日期，格式 YYYY年MM月DD日 星期X",
            },
            "headline": {
                "type": "string",
                "description": "今日最重要一件事，15字內",
            },
            "watchlist": {
                "type": "array",
                "items": {"type": "string"},
                "description": "追蹤議題更新，每條「• **議題**：動向 [來源](URL)」",
            },
            "industry_trends": {
                "type": "array",
                "items": {"type": "string"},
                "description": "重點版面：AI 在零售 / 餐飲 / Hotel 應用趨勢分析（self-checkout、AI kiosk、電腦視覺防損、AI 點餐、飯店自助入住、個人化行銷、無人商店、供應鏈 AI 等），聚焦趨勢解讀，至少 4-6 條，每條「• **主題**：趨勢說明 [來源](URL)」，無資料則輸出空陣列",
            },
            "pos_competitors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "POS / Kiosk / Self-checkout 競品動態（Partner Tech、Elo、Zebra、商米、Flytech、Posiflex、NCR、Toshiba Tec 在 AI 應用上的更新），獨立版面，每條「• **公司**：動向 [來源](URL)」，無資料則輸出空陣列",
            },
            "sections": {
                "type": "object",
                "properties": {
                    "geo":         {"type": "array", "items": {"type": "string"}},
                    "finance":     {"type": "array", "items": {"type": "string"}},
                    "ai_tech":     {"type": "array", "items": {"type": "string"}},
                    "ai_tools":    {"type": "array", "items": {"type": "string"}},
                    "social":      {"type": "array", "items": {"type": "string"}},
                    "pos_retail": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "POS / 零售科技與 Kiosk 競品動態（Partner Tech、Elo、Zebra、商米、Flytech、Posiflex、NCR、Toshiba Tec、零售科技/kiosk 應用），每條「• **公司/主題**：動向 [來源](URL)」，無資料則輸出空陣列",
                    },
                },
                "required": ["geo", "finance", "ai_tech", "ai_tools", "social", "pos_retail"],
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "4個關鍵字",
            },
        },
        "required": ["date", "headline", "watchlist", "industry_trends", "pos_competitors", "sections", "keywords"],
        },
    },
}

WEEKDAYS = "一二三四五六日"


def extract_schema(tool: dict[str, Any]) -> dict[str, Any]:
    """Extract the plain JSON schema from an OpenAI function tool def."""
    return tool.get("function", tool).get("parameters", tool)


def synthesize(
    raw_articles: dict[str, list[dict[str, str]]],
    brave_articles: list[dict[str, str]] | None = None,
    competitor_articles: list[dict[str, str]] | None = None,
    today: datetime | None = None,
    retail_hospitality_articles: list[dict[str, str]] | None = None,
    pos_competitor_articles: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    today = today or datetime.now()
    today_str = format_tw_date(today)
    article_dump = format_articles_for_prompt(raw_articles)

    api_key = os.getenv("OPENAI_API_KEY")
    if openai is None or not api_key:
        return build_fallback_briefing(raw_articles, today_str)

    client = openai.OpenAI(api_key=api_key, timeout=60.0)
    watchlist_line = f"追蹤議題：{' / '.join(WATCHLIST)}\n\n" if WATCHLIST else ""
    brave_section = _format_brave_for_prompt(brave_articles) if brave_articles else ""
    competitor_section = (
        _format_topic_search_for_prompt(
            competitor_articles,
            "【競品 / 安防產業動態 - 新聞與公開報導】",
        )
        if competitor_articles
        else ""
    )
    retail_hospitality_section = (
        _format_topic_search_for_prompt(
            retail_hospitality_articles,
            "【AI 零售 / 餐飲 / Hotel 應用趨勢 - 獨立版面】",
        )
        if retail_hospitality_articles
        else ""
    )
    pos_competitor_section = (
        _format_topic_search_for_prompt(
            pos_competitor_articles,
            "【POS / Kiosk / Self-checkout 競品動態 - 獨立版面】",
        )
        if pos_competitor_articles
        else ""
    )
    prompt = (
        f"今天是 {today_str}。{watchlist_line}{brave_section}{competitor_section}"
        f"{retail_hospitality_section}{pos_competitor_section}"
        f"以下是今日抓取的文章，請產出早報 JSON：\n\n{article_dump}"
    )

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            # GPT-5.6 Terra 支援 JSON 輸出模式（不支援 function calling + reasoning）。
            # 用 system prompt 給 schema + response_format 強制 JSON。
            system_msg = SYSTEM_PROMPT + (
                "\n\n請只輸出一個符合下列 schema 的 JSON 物件（不要有 markdown、不要說明文字）：\n"
                + json.dumps(extract_schema(BRIEFING_TOOL), ensure_ascii=False, indent=2)
            )
            message = client.chat.completions.create(
                model="gpt-5.6-terra",
                max_completion_tokens=8192,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ],
            )
            msg = message.choices[0].message if message.choices else None
            raw_text = (getattr(msg, "content", None) or "").strip()
            if not raw_text:
                raise ValueError(
                    f"Empty response from API (finish_reason={message.choices[0].finish_reason if message.choices else None})"
                )
            return extract_json(raw_text)
        except Exception as exc:  # pragma: no cover
            last_error = exc
            if attempt < 2:
                time.sleep(2**attempt)

    print(f"[synthesizer] Claude API failed after retries, falling back: {last_error}")
    return build_fallback_briefing(raw_articles, today_str)


def _is_fallback(briefing: dict[str, Any]) -> bool:
    """Detect a degraded fallback briefing (LLM failed → truncated titles, empty sections)."""
    if not isinstance(briefing, dict):
        return True
    # Fallback 產物特徵：watchlist/industry_trends/pos_competitors 全空且 sections 用截斷標題
    empty_llm_boards = not (briefing.get("watchlist") or briefing.get("industry_trends")
                            or briefing.get("pos_competitors"))
    if not empty_llm_boards:
        return False
    for cat_items in (briefing.get("sections") or {}).values():
        for item in cat_items or []:
            if "建議追蹤原文與後續市場反應" in str(item):
                return True
    return False


def _format_topic_search_for_prompt(articles: list[dict[str, str]], header: str) -> str:
    lines = [header]
    for item in articles:
        topic = item.get("source", "").replace("brave:", "")
        title = item.get("title", "").strip()
        url = item.get("url", "").strip()
        summary = item.get("summary", "").strip()
        line = f"- [{topic}] {title} | {url}"
        if summary:
            line += f" | {summary[:180]}"
        lines.append(line)
    lines.append("")
    return "\n".join(lines) + "\n"


def _format_brave_for_prompt(brave_articles: list[dict[str, str]]) -> str:
    lines = ["【即時搜尋補充 - Watchlist 議題】"]
    for item in brave_articles:
        topic = item.get("source", "").replace("brave:", "")
        title = item.get("title", "").strip()
        url = item.get("url", "").strip()
        summary = item.get("summary", "").strip()
        line = f"- [{topic}] {title} | {url}"
        if summary:
            line += f" | {summary[:180]}"
        lines.append(line)
    lines.append("")
    return "\n".join(lines) + "\n"


def format_articles_for_prompt(raw_articles: dict[str, list[dict[str, str]]]) -> str:
    lines: list[str] = []
    for category, config in SOURCES.items():
        label = config["label"]
        items = raw_articles.get(category, [])
        lines.append(f"[{category}] {label}")
        if not items:
            lines.append("- 無新資訊")
            continue
        for item in items[:20]:
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            summary = item.get("summary", "").strip()
            if summary:
                lines.append(f"- {title} | {url} | {summary[:180]}")
            else:
                lines.append(f"- {title} | {url}")
        lines.append("")
    return "\n".join(lines).strip()


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(raw_text: str) -> dict[str, Any]:
    candidate = raw_text.strip()
    parsed = _try_json_loads(candidate)
    if parsed is not None:
        return parsed

    fence_match = _CODE_FENCE_RE.search(candidate)
    if fence_match:
        parsed = _try_json_loads(fence_match.group(1).strip())
        if parsed is not None:
            return parsed

    balanced = _extract_balanced_object(candidate)
    if balanced is not None:
        parsed = _try_json_loads(balanced)
        if parsed is not None:
            return parsed

    repaired = _try_repair_truncated_json(candidate)
    if repaired is not None:
        return repaired
    raise ValueError("Model response does not contain valid JSON object.")


def _try_json_loads(text: str) -> dict[str, Any] | None:
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        return None
    return result if isinstance(result, dict) else None


def _extract_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _try_repair_truncated_json(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    if start == -1:
        return None
    truncated = text[start:]
    if truncated.count('"') % 2:
        truncated += '"'
    open_braces = truncated.count("{") - truncated.count("}")
    open_brackets = truncated.count("[") - truncated.count("]")
    truncated = truncated.rstrip().rstrip(",")
    return _try_json_loads(truncated + "]" * max(open_brackets, 0) + "}" * max(open_braces, 0))


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
        "watchlist": [],
        "industry_trends": [],
        "pos_competitors": [],
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
