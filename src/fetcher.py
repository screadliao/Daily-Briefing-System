from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urljoin, urlparse
import urllib.request

import feedparser
import httpx
from bs4 import BeautifulSoup

from src.sources import SOURCES

MAX_ITEMS_PER_SOURCE = 5
MAX_ITEMS_PER_ISSUE_PAGE = 30
MAX_TOTAL_ITEMS = 200
DEFAULT_TIMEOUT = 15.0
USER_AGENT = "DailyBriefingBot/1.0 (+https://github.com/screadliao)"
MAX_WORKERS = 10
TITLE_DEDUPE_THRESHOLD = 0.82
SUMMARY_PROMPT_CHARS = 300


@dataclass
class RawArticle:
    category: str
    source: str
    title: str
    url: str
    summary: str = ""
    published: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "category": self.category,
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "published": self.published,
        }


def fetch_all(
    sources: dict[str, dict[str, Any]] | None = None,
    client: httpx.Client | None = None,
) -> dict[str, list[dict[str, str]]]:
    sources = sources or SOURCES
    own_client = client is None
    client = client or build_http_client()
    seen_urls: set[str] = set()
    seen_titles: dict[str, list[str]] = {category: [] for category in sources}
    total = 0
    result: dict[str, list[dict[str, str]]] = {category: [] for category in sources}

    try:
        task_specs: list[tuple[str, str, Any]] = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for category, config in sources.items():
                for feed_url in config.get("feeds", []):
                    future = executor.submit(fetch_feed, feed_url, category, MAX_ITEMS_PER_SOURCE)
                    task_specs.append((category, "feed", future))
                for scrape_url in config.get("scrape", []):
                    future = executor.submit(scrape_page, client, scrape_url, category, MAX_ITEMS_PER_SOURCE)
                    task_specs.append((category, "scrape", future))
                for feed_url in config.get("issue_pages", []):
                    future = executor.submit(fetch_issue_page, client, feed_url, category, MAX_ITEMS_PER_ISSUE_PAGE)
                    task_specs.append((category, "issue_page", future))

            for category, _task_type, future in task_specs:
                if total >= MAX_TOTAL_ITEMS:
                    break
                try:
                    articles = future.result(timeout=25)
                except Exception:
                    articles = []
                for article in articles:
                    if total >= MAX_TOTAL_ITEMS:
                        break
                    if article.url in seen_urls:
                        continue
                    if is_duplicate_title(article.title, seen_titles[category]):
                        continue
                    seen_urls.add(article.url)
                    seen_titles[category].append(normalize_title(article.title))
                    result[category].append(article.to_dict())
                    total += 1
        return result
    finally:
        if own_client:
            client.close()


def build_http_client() -> httpx.Client:
    return httpx.Client(
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


def fetch_feed(feed_url: str, category: str, limit: int = MAX_ITEMS_PER_SOURCE) -> list[RawArticle]:
    try:
        req = urllib.request.Request(feed_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read()
        parsed = feedparser.parse(raw)
    except Exception:
        return []

    if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", None):
        return []

    items: list[RawArticle] = []
    for entry in parsed.entries[:limit]:
        title = clean_text(entry.get("title", ""))
        url = pick_entry_url(entry)
        if not title or not url:
            continue
        items.append(
            RawArticle(
                category=category,
                source=feed_url,
                title=title,
                url=url,
                summary=clean_text(entry.get("summary", "") or entry.get("description", "")),
                published=entry.get("published", "") or entry.get("updated", ""),
            )
        )
    return items


def scrape_page(
    client: httpx.Client,
    page_url: str,
    category: str,
    limit: int = MAX_ITEMS_PER_SOURCE,
) -> list[RawArticle]:
    try:
        response = client.get(page_url)
        response.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(response.text, "lxml")
    domain = urlparse(page_url).netloc
    seen: set[str] = set()
    items: list[RawArticle] = []

    for anchor in soup.select("a[href]"):
        if len(items) >= limit:
            break
        href = anchor.get("href", "").strip()
        title = clean_text(anchor.get_text(" ", strip=True))
        if not href or len(title) < 8:
            continue
        url = urljoin(page_url, href)
        if not is_probably_article(url, domain) or url in seen:
            continue
        seen.add(url)
        items.append(
            RawArticle(
                category=category,
                source=page_url,
                title=title,
                url=url,
            )
        )
    return items


def fetch_issue_page(
    client: httpx.Client,
    feed_url: str,
    category: str,
    limit: int = MAX_ITEMS_PER_ISSUE_PAGE,
) -> list[RawArticle]:
    fallback = fetch_feed(feed_url, category, 1)
    if not fallback:
        return []

    issue_url = fallback[0].url
    try:
        response = client.get(issue_url)
        response.raise_for_status()
    except Exception:
        return fallback

    articles = parse_issue_page(response.text, issue_url, category, limit)
    return articles or fallback


def parse_issue_page(
    html: str,
    issue_url: str,
    category: str,
    limit: int = MAX_ITEMS_PER_ISSUE_PAGE,
) -> list[RawArticle]:
    soup = BeautifulSoup(html, "lxml")
    stories = soup.select("article.p-story")
    if not stories:
        return []

    items: list[RawArticle] = []
    lead = soup.select_one("section#article")
    if lead:
        lead_title = lead.select_one("h2")
        if lead_title:
            kicker = lead_title.select_one(".p-kicker")
            if kicker:
                kicker.extract()
        title = clean_text(lead_title.get_text(" ", strip=True) if lead_title else "")
        lead_summary = lead.select_one(".p-article-lead")
        summary = clean_text(lead_summary.get_text(" ", strip=True) if lead_summary else "")
        if title and summary:
            items.append(RawArticle(category, "FulyAI", title, issue_url, summary[:SUMMARY_PROMPT_CHARS]))

    for story in stories[:limit]:
        anchor = story.select_one("h3 a[href]")
        if not anchor:
            continue
        title = clean_text(anchor.get_text(" ", strip=True))
        url = urljoin(issue_url, anchor["href"].strip())
        story_summary = story.select_one(".p-text")
        story_source = story.select_one(".p-src")
        summary = clean_text(story_summary.get_text(" ", strip=True) if story_summary else "")
        source = clean_text(story_source.get_text(" ", strip=True) if story_source else "")
        meta = story.select(".p-meta span")
        published = clean_text(meta[-1].get_text(" ", strip=True)) if len(meta) > 1 else ""
        if not title or not summary or not source or not urlparse(url).scheme.startswith("http"):
            continue
        items.append(
            RawArticle(category, f"FulyAI / {source}", title, url, summary[:SUMMARY_PROMPT_CHARS], published)
        )
    return items


def pick_entry_url(entry: Any) -> str:
    link = entry.get("link", "")
    if link:
        return link.strip()
    links = entry.get("links", [])
    if links:
        return links[0].get("href", "").strip()
    return ""


def clean_text(value: str) -> str:
    if not value:
        return ""
    return " ".join(BeautifulSoup(value, "lxml").get_text(" ", strip=True).split())


def normalize_title(title: str) -> str:
    lowered = title.lower()
    return re.sub(r"[^0-9a-z一-鿿]+", "", lowered)


def is_duplicate_title(title: str, seen_normalized_titles: list[str]) -> bool:
    normalized = normalize_title(title)
    if not normalized:
        return False
    for existing in seen_normalized_titles:
        if SequenceMatcher(None, normalized, existing).ratio() >= TITLE_DEDUPE_THRESHOLD:
            return True
    return False


def is_probably_article(url: str, domain: str) -> bool:
    parsed = urlparse(url)
    if not parsed.scheme.startswith("http"):
        return False
    if domain and domain not in parsed.netloc:
        return False
    lowered = url.lower()
    noise_tokens = (
        "#",
        "javascript:",
        "mailto:",
        "/tag/",
        "/category/",
        "/author/",
        "/account/",
        "/login",
        "/signup",
        "/subscribe",
        "/privacy",
        "/terms",
        "/about",
        "/contact",
    )
    if any(token in lowered for token in noise_tokens):
        return False
    path = parsed.path.strip("/")
    return len(path) >= 6
