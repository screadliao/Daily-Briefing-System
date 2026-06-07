from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse
import urllib.request

import feedparser
import httpx
from bs4 import BeautifulSoup

from src.sources import SOURCES

MAX_ITEMS_PER_SOURCE = 5
MAX_TOTAL_ITEMS = 200
DEFAULT_TIMEOUT = 15.0
USER_AGENT = "DailyBriefingBot/1.0 (+https://github.com/screadliao)"
MAX_WORKERS = 10


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
                    seen_urls.add(article.url)
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
