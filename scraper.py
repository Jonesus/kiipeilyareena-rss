#!/usr/bin/env python3
"""Scrape Kiipeilyareena news from ajankohtaista page and generate an RSS feed."""

import sys
import logging
import json
import xml.dom.minidom as minidom
from datetime import datetime, timezone
from io import StringIO

import requests
from bs4 import BeautifulSoup
from feedgenerator import Rss201rev2Feed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://kiipeilyareena.com"
FEED_URL = f"{BASE_URL}/ajankohtaista/"
OUTPUT_FILE = "feed.xml"
REQUEST_TIMEOUT = 30


def fetch_page(url: str) -> str:
    """Fetch a page and return its HTML content."""
    logger.info("Fetching %s", url)
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def parse_articles(soup: BeautifulSoup) -> list[dict]:
    """Extract articles from the page HTML."""
    articles = []
    for article_tag in soup.select("article.tease-course"):
        link_tag = article_tag.select_one("a.tease-course-container")
        if not link_tag:
            continue

        title_tag = article_tag.select_one("h2.content-title")
        body_tag = article_tag.select_one("p.content-body")
        img_tag = article_tag.select_one("img")

        title = title_tag.get_text(strip=True) if title_tag else ""
        body = body_tag.get_text(strip=True) if body_tag else ""
        link = link_tag.get("href", "")
        href = _join_url(link) if link else ""

        img_url = ""
        if img_tag:
            src = img_tag.get("src", "")
            if src:
                img_url = _join_url(src)

        articles.append(
            {
                "title": title,
                "body": body,
                "link": href,
                "image": img_url,
                "date": "",
            }
        )
    return articles


def _join_url(url: str) -> str:
    """Join a relative URL with the base URL."""
    if url.startswith("http"):
        return url
    if not url.startswith("/"):
        url = "/" + url
    return BASE_URL + url


def fetch_article_date(url: str) -> datetime:
    """Fetch the publish date from an article page."""
    try:
        html = fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")

        for meta in soup.select("meta"):
            prop = meta.get("property", "") or meta.get("name", "")
            if prop in ("article:published_time", "publish_date"):
                content = meta.get("content", "").strip()
                if content:
                    return _parse_iso_date(content)

        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string)
                dates = _extract_dates(data)
                if dates.get("published"):
                    return _parse_iso_date(dates["published"])
            except (json.JSONDecodeError, TypeError):
                pass

        return datetime.now(timezone.utc)
    except Exception as e:
        logger.warning("Failed to fetch date for %s: %s", url, e)
        return datetime.now(timezone.utc)


def _extract_dates(obj, result=None):
    """Recursively extract datePublished and dateModified from JSON-LD."""
    if result is None:
        result = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "datePublished" and not result.get("published"):
                result["published"] = value
            elif key == "dateModified" and not result.get("modified"):
                result["modified"] = value
            _extract_dates(value, result)
    elif isinstance(obj, list):
        for item in obj:
            _extract_dates(item, result)
    return result


def _parse_iso_date(date_str: str) -> datetime:
    """Parse an ISO 8601 date string and return a timezone-aware datetime."""
    try:
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"
        if "+" not in date_str[10:] and date_str.count("-") <= 2:
            date_str += "+00:00"
        return datetime.fromisoformat(date_str)
    except (ValueError, IndexError):
        return datetime.now(timezone.utc)


def get_all_articles() -> list[dict]:
    """Fetch articles from all paginated pages."""
    all_articles: list[dict] = []
    url = FEED_URL
    date_fetched = False

    while True:
        html = fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")
        articles = parse_articles(soup)

        if not articles:
            logger.info("No more articles found")
            break

        logger.info("Found %d articles", len(articles))

        # Fetch dates from the first page only
        if not date_fetched:
            date_fetched = True
            for article in articles:
                if article["link"]:
                    article["date"] = fetch_article_date(article["link"])

        all_articles.extend(articles)

        next_link = soup.select_one('link[rel="next"]')
        if next_link:
            next_href = next_link.get("href", "")
            if next_href:
                url = next_href
            else:
                break
        else:
            break

    # Sort by date descending, articles without dates go to the bottom
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    all_articles.sort(key=lambda a: a["date"] or epoch, reverse=True)
    return all_articles


def _build_description(article: dict) -> str:
    """Build the HTML description for an article."""
    parts = []
    if article["image"]:
        parts.append(f'<img src="{article["image"]}" alt="" />')
    if article["body"]:
        parts.append(f"<p>{article['body']}</p>")
    parts.append(f'<p><a href="{article["link"]}">Lue lisää...</a></p>')
    return "\n".join(parts)


def generate_rss(articles: list[dict]) -> str:
    """Generate an RSS 2.0 feed using feedgenerator, then prettify with minidom."""
    now = datetime.now(timezone.utc)

    feed = Rss201rev2Feed(
        title="Kiipeilyareena - Ajankohtaista",
        link=BASE_URL,
        description="Kiipeilyareenan ajankohtaiset tiedotteet ja uutiset",
        language="fi",
        feed_url=f"{BASE_URL}/feed.xml",
        subtitle=None,
    )

    feed.feed["image_url"] = f"{BASE_URL}/wp-content/uploads/2023/08/kiipeilyareena-favicon-2.png"
    feed.feed["image_title"] = "Kiipeilyareena - Ajankohtaista"
    feed.feed["image_link"] = BASE_URL

    for article in articles:
        description_html = _build_description(article)
        feed.add_item(
            title=article["title"],
            link=article["link"],
            description=description_html,
            pub_date=article["date"],
            unique_id=article["link"],
        )

    # Get the XML string from feedgenerator
    xml_string = feed.writeString("utf-8")

    # Parse and re-serialize with proper indentation using minidom
    # First, parse from the string
    dom = minidom.parse(StringIO(xml_string))

    # minidom's prettify adds an extra newline at the start, so we strip it
    pretty_xml = dom.toprettyxml(indent="  ", encoding=None)
    # Remove the extra blank line that toprettyxml adds at the start
    pretty_xml = pretty_xml.lstrip("\n")

    return pretty_xml


def main():
    articles = get_all_articles()

    if not articles:
        logger.error("No articles found!")
        sys.exit(1)

    logger.info("Total articles: %d", len(articles))

    xml_string = generate_rss(articles)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml_string)

    logger.info("RSS feed written to %s", OUTPUT_FILE)


if __name__ == "__main__":
    main()
