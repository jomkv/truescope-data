import json
import asyncio
import gc
import os
import time
import random
import sys
from pathlib import Path
from urllib.parse import urlparse, urljoin
from datetime import datetime, timezone, timedelta
from dateutil import parser
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from data_cleaning.manilaStandardCleaner import clean_article as ManilaStandardCleaner
from .utils import (
    save_article_async,
    get_existing_articles_urls,
    DATE_LIMIT,
    MAX_PAGES as UTILS_MAX_PAGES,
    MAX_CONSECUTIVE_OLD,
    MAX_CONSECUTIVE_NO_NEW_LINKS,
    EMBEDDER,
)

# Using shared EMBEDDER from utils


def save_article(article: dict):
    return save_article_sync(article, ManilaStandardCleaner, EMBEDDER)


# Scrape a single Manila Standard article page
def scrape_manilastandard_article(page, url):
    try:
        page.goto(url, timeout=90000)

        # Title
        title = None
        for sel in [
            "h1.tdb-title-text",
            "h1.entry-title",
            "article h1",
            "h1",
            "meta[property='og:title']",
        ]:
            try:
                if sel.startswith("meta"):
                    t = page.locator(sel)
                    if t.count() > 0:
                        title = t.first.get_attribute("content")
                else:
                    t = page.locator(sel)
                    if t.count() > 0:
                        title = t.first.inner_text().strip()
                if title:
                    break
            except Exception:
                continue

        # Author
        author = None
        for sel in [
            ".tdb-author-name a",
            ".td-module-meta .td-post-author-name",
            ".author",
            ".byline",
            "meta[name='author']",
        ]:
            try:
                l = page.locator(sel)
                if l.count() > 0:
                    author = (
                        l.first.inner_text().strip()
                        if not sel.startswith("meta")
                        else l.first.get_attribute("content")
                    )
                    break
            except Exception:
                continue

        # Date
        date_str = None
        for sel in [
            ".tdb-date-update",
            "time",
            ".td-post-date",
            "meta[property='article:published_time']",
        ]:
            try:
                l = page.locator(sel)
                if l.count() > 0:
                    date_str = (
                        l.first.get_attribute("datetime")
                        if sel.startswith("meta") or sel == "time"
                        else l.first.inner_text().strip()
                    )
                    if not date_str:
                        date_str = l.first.inner_text().strip()
                    break
            except Exception:
                continue

        # Content paragraphs
        paragraphs = []
        for sel in [
            ".tdb-article-content p",
            "div.td-post-content p",
            "article p",
            "div.entry-content p",
        ]:
            try:
                ps = page.locator(sel).all()
                if ps:
                    paragraphs = [
                        p.inner_text().strip() for p in ps if p.inner_text().strip()
                    ]
                    if paragraphs:
                        break
            except Exception:
                continue
        content = "\n".join(paragraphs) if paragraphs else None

        if not title or (not author and not date_str and not content):
            return {
                "url": url,
                "skipped": True,
                "reason": "Missing title or essential fields",
            }

        publishDate = None
        if date_str:
            try:
                clean_date = date_str.replace("Published ", "").strip()
                dt = parser.parse(clean_date)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
                publishDate = dt.isoformat()
            except Exception:
                publishDate = date_str

        domain = urlparse(url).netloc.replace("www.", "")
        source = "MANILASTANDARD"

        return {
            "title": title,
            "content": content,
            "publishDate": publishDate,
            "author": author,
            "url": url,
            "source": "MANILASTANDARD",
            "type": "news",
            "sourceBias": None,
            "claim": None,
            "verdict": None,
        }

    except PlaywrightTimeoutError:
        return {"url": url, "skipped": True, "reason": "Timeout loading article"}
    except PlaywrightError as e:
        return {"url": url, "skipped": True, "reason": str(e)}
    except Exception as e:
        return {"url": url, "skipped": True, "reason": str(e)}


# Collect and scrape listing page that uses a "Load more" button
def collect_and_scrape_listing(listing_url, max_pages=100):
    print(f"Starting Manila Standard scraper with real-time DB integration...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        print(f"Fetch existing URLs from the database once per category run")
        print(f"Loaded {len(existing_urls)} existing articles to skip duplicates.")

        page.goto(listing_url, timeout=60000)
        try:
            page.wait_for_selector(
                ".td-ss-main-content, .td-pb-span8, article", timeout=15000
            )
        except Exception:
            pass

        discovered_urls = set()
        consecutive_too_old = 0
        dead_clicks = 0
        max_dead_clicks = 6  # Added to fix NameError
        total_scraped = 0

        pages_clicked = 0
        consecutive_no_new_links = 0
        while True:
            pages_clicked += 1

            # Grab article links. The theme uses multiple anchor placements
            selectors = [
                "a[href*='/news/']",
                ".td-module-title a",
                "h3.entry-title a",
                "a[rel='bookmark']",
                ".td-image-wrap",
            ]
            combined_sel = ",".join(selectors)
            new_links = []
            for sel in selectors:
                try:
                    for a in page.locator(sel).all():
                        try:
                            href = a.get_attribute("href")
                        except Exception:
                            href = None
                        if not href:
                            continue
                        # Normalize relative URLs
                        if href.startswith("/"):
                            href = urljoin(listing_url, href)

                        # Only accept article links under /news/ and exclude categories/tags
                        if (
                            "manilastandard.net" in href
                            and "/news/" in href
                            and "/category/" not in href
                            and "/tag/" not in href
                            and href not in discovered_urls
                        ):
                            #  Skip if already in database
                            if href in existing_urls:
                                continue
                            new_links.append(href)
                            discovered_urls.add(href)
                except Exception:
                    continue

            print(f"New links this cycle: {len(new_links)}")

            if not new_links:
                consecutive_no_new_links += 1
                print(f"No new links found on cycle {pages_clicked} ({consecutive_no_new_links}/{MAX_CONSECUTIVE_NO_NEW_LINKS})")
                if consecutive_no_new_links >= MAX_CONSECUTIVE_NO_NEW_LINKS:
                    print(f"Stopping: {consecutive_no_new_links} consecutive cycles with no new links.")
                    break
            else:
                consecutive_no_new_links = 0

            for url in new_links:
                print(f"Scraping: {url}")
                article_page = context.new_page()
                article_data = scrape_manilastandard_article(article_page, url)
                article_page.close()

                if article_data.get("skipped"):
                    print(
                        f"Skipped article: {url} - Reason: {article_data.get('reason')}"
                    )
                    continue

                # save_article returns False only if skipped due to age
                is_recent = save_article(article_data)
                if not is_recent:
                    consecutive_too_old += 1
                    if consecutive_too_old >= MAX_CONSECUTIVE_OLD:
                        print(
                            f"Stopping: {consecutive_too_old} consecutive articles are too old (before {DATE_LIMIT})."
                        )
                        browser.close()
                        return
                else:
                    consecutive_too_old = 0  # Reset on any valid found article
                    total_scraped += 1

                time.sleep(random.uniform(0.6, 1.3))

            # Count anchors using the same combined selector so we detect newly loaded items reliably
            before_count = len(page.locator(combined_sel).all())

            # Try clicking the "Load more" button if present
            load_more = page.locator(
                ".td_ajax_load_more, .td_ajax_load_more_js, a.td_ajax_load_more, a[id^='next-page']"
            )
            if load_more.count() > 0:
                try:
                    btn = load_more.first
                    if btn.is_visible():
                        try:
                            btn.scroll_into_view_if_needed()
                        except Exception:
                            pass
                        btn.click()
                        time.sleep(1.2)  # wait a bit for content to load
                        # wait for new anchors to appear (short polling)
                        for _ in range(16):
                            after_count = len(page.locator(combined_sel).all())
                            if after_count > before_count:
                                break
                            time.sleep(0.5)
                        after_count = len(page.locator(combined_sel).all())
                        if after_count == before_count:
                            dead_clicks += 1
                            print(
                                f"Load-more clicked but no new items ({dead_clicks}/{max_dead_clicks})"
                            )
                        else:
                            dead_clicks = 0
                            print(f"Loaded {after_count - before_count} new stories")
                    else:
                        dead_clicks += 1
                        print(
                            f"Load-more not visible ({dead_clicks}/{max_dead_clicks})"
                        )
                except Exception as e:
                    dead_clicks += 1
                    print(
                        f"Error clicking load-more: {e} ({dead_clicks}/{max_dead_clicks})"
                    )
            else:
                # No load more button present  likely end of listing
                print("No load-more button found  stopping.")
                break

            if dead_clicks >= max_dead_clicks:
                print("Reached end or no more content  stopping.")
                break

            # Memory hygiene: restart browser and clear logs periodically
            if pages_clicked % 10 == 0:
                print(f"Restarting browser at cycle {pages_clicked} for memory management")
                try:
                    browser.close()
                except Exception:
                    pass
                
                # Force garbage collection
                gc.collect()
                print(f"Memory cleared and garbage collected at {datetime.now().strftime('%H:%M:%S')}")
                
                time.sleep(1)
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800},
                )
                page = context.new_page()
                # Re-navigate to listing page (Manila Standard load-more state is lost)
                # Note: Manila Standard's stateful load-more is tricky, but browser restart is necessary for memory.
                page.goto(listing_url, timeout=60000)
                # Fast-forward to current content? Actually, most of these sites will re-load the same articles,
                # but get_existing_articles_urls() handles the skipping.

        browser.close()
        print("\nScraping complete.")


def main():
    LISTING_URL = "https://manilastandard.net/category/news"
    collect_and_scrape_listing(LISTING_URL)


if __name__ == "__main__":
    main()
