import json
import time
import random
import sys
import re
from pathlib import Path
from urllib.parse import urlparse, urljoin
from datetime import datetime, timezone, timedelta
from dateutil import parser
import gc
import os
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from data_cleaning.frontpageCleaner import clean_article as FrontpageCleaner
from .utils import (
    save_article_sync,
    get_existing_articles_urls,
    DATE_LIMIT,
    MAX_PAGES,
    MAX_CONSECUTIVE_OLD,
    EMBEDDER,
)

# Using shared EMBEDDER from utils


def save_article(article: dict):
    return save_article_sync(article, FrontpageCleaner, EMBEDDER)


# Scrape a single article page
def scrape_frontpageph_article(page, url):
    try:
        page.goto(url, timeout=90000)

        # Title
        title = None
        for sel in [
            "h1.loop-title",
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
            "a[rel='author'] span[itemprop='name']",
            ".entry-author a",
            "a[rel='author']",
            ".author-name",
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
                    if author:
                        break
            except Exception:
                continue

        # Date
        date_str = None
        for sel in [
            "time.entry-published",
            "time",
            "meta[property='article:published_time']",
            ".entry-date",
        ]:
            try:
                l = page.locator(sel)
                if l.count() > 0:
                    if sel.startswith("time") or sel == "time":
                        date_str = (
                            l.first.get_attribute("datetime")
                            or l.first.inner_text().strip()
                        )
                    elif sel.startswith("meta"):
                        date_str = l.first.get_attribute("content")
                    else:
                        date_str = l.first.inner_text().strip()
                    if date_str:
                        break
            except Exception:
                continue

        # Content
        paragraphs = []
        for sel in [
            ".entry-the-content p",
            ".entry-content p",
            "article .content p",
            "article p",
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
        source = "FRONTPAGEPH"

        return {
            "title": title,
            "content": content,
            "publishDate": publishDate,
            "author": author,
            "url": url,
            "source": source,
            "type": "NEWS",
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


# Collect and scrape listing page with pagination
def collect_and_scrape_listing(listing_url):
    print(f"Starting FrontpagePH Nation scraper with real-time DB integration...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        discovered_urls = set()
        consecutive_too_old = 0
        current_page = 1
        consecutive_no_new_links = 0

        #  Fetch existing URLs from the database once per run
        existing_urls = get_existing_articles_urls(EMBEDDER, source="FRONTPAGEPH")
        print(f"Loaded {len(existing_urls)} existing articles to skip duplicates.")

        while True:
            # Construct pagination URL
            if current_page == 1:
                page_url = listing_url
            else:
                # Remove trailing slash if present and add page number
                base_url = listing_url.rstrip("/")
                page_url = f"{base_url}/page/{current_page}/"

            print(f"\nScraping page {current_page}: {page_url}")

            try:
                page.goto(page_url, timeout=60000)
                time.sleep(random.uniform(2.0, 4.0))  # Let page load with random delay
            except Exception as e:
                print(f"Error loading page {current_page}: {e}")
                if "429" in str(e) or "Too Many Requests" in str(e):
                    print("Rate limited! Waiting 30 seconds before continuing...")
                    time.sleep(30)
                continue

            # Grab article links - FrontpagePH uses article tags with h2 > a structure
            anchors = page.locator("article h2 a").all()

            print(f"Total article elements found: {len(anchors)}")

            new_links = []
            all_links = []
            for a in anchors:
                href = a.get_attribute("href")
                if (
                    href
                    and href.startswith("https://frontpageph.com")
                    and "/category/" not in href
                    and "/author/" not in href
                ):
                    all_links.append(href)
                    if href not in discovered_urls:
                        #  Skip if already in database
                        if href in existing_urls:
                            continue
                        new_links.append(href)
                        discovered_urls.add(href)

            print(
                f"Page {current_page}: Found {len(all_links)} articles ({len(new_links)} new)"
            )

            if not new_links:
                print(
                    f"No new articles found on page {current_page} (all {len(all_links)} were duplicates or page is empty)."
                )
                consecutive_no_new_links += 1
                if consecutive_no_new_links >= 10:
                    print(
                        f"Stopping: {consecutive_no_new_links} consecutive pages with no new links. Pagination halted to save time."
                    )
                    break
                current_page += 1
                continue
            else:
                consecutive_no_new_links = 0

            # Scrape any new found links
            for url in new_links:
                print(f"Scraping: {url}")
                article_page = browser.new_page()
                data = scrape_frontpageph_article(article_page, url)
                article_page.close()

                # save_article returns False only if skipped due to age
                is_recent = save_article(data)
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

                time.sleep(
                    random.uniform(2.0, 4.0)
                )  # Longer delay between article scrapes

            # Memory hygiene: restart browser and clear logs periodically
            if current_page % 5 == 0:
                print(
                    f"Restarting browser at page {current_page} for memory management"
                )
                try:
                    browser.close()
                except Exception:
                    pass

                # Clear console and force garbage collection
                os.system("cls" if os.name == "nt" else "clear")
                gc.collect()
                print(
                    f"Memory cleared and garbage collected at {datetime.now().strftime('%H:%M:%S')}"
                )

                time.sleep(1)
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

            # Move to next page
            current_page += 1
            time.sleep(random.uniform(3.0, 6.0))  # Wait before next page

        browser.close()
        print("\n Scraping complete.")


def main():
    LISTING_URL = "https://frontpageph.com/category/nation/"
    collect_and_scrape_listing(LISTING_URL)


if __name__ == "__main__":
    main()
