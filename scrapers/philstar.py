import json
import asyncio
import gc
import os
import time
import random
import sys
from pathlib import Path
from urllib.parse import urlparse
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

from data_cleaning.philstarCleaner import clean_article as PhilstarCleaner
from .utils import (
    save_article_sync,
    get_existing_articles_urls,
    DATE_LIMIT,
    MAX_CONSECUTIVE_OLD,
    MAX_CONSECUTIVE_NO_NEW_LINKS,
    EMBEDDER,
)

# Using shared EMBEDDER from utils


def save_article(article: dict):
    return save_article_sync(article, PhilstarCleaner, EMBEDDER)


# Scrape a single Philstar article page
def scrape_philstar_article(page, url):
    # Selectors based on the Philstar HTML structure provided

    # Selector to wait for the main content block to appear
    MAIN_CONTENT_SELECTOR = ".theContent"

    # New priority list for data extraction
    TITLE_SELECTORS = ["div.article__title h1", "meta[property='og:title']"]
    AUTHOR_SELECTORS = [
        ".article__credits-author-pub a",
        ".article__credits-author-pub",
        "meta[name='author']",
    ]
    DATE_SELECTORS = [
        ".article__date-published",
        "meta[property='article:published_time']",
    ]
    CONTENT_SELECTORS = ["div.article__writeup p", "div.theContent p"]

    try:
        page.goto(url, timeout=90000)  # 90s timeout for slow pages

        # Wait for the main content block, which is essential for scraping
        page.wait_for_selector(MAIN_CONTENT_SELECTOR, timeout=30000)

        # --- Title ---
        title = None
        for sel in TITLE_SELECTORS:
            try:
                l = page.locator(sel)
                if l.count() > 0:
                    title = (
                        l.first.get_attribute("content")
                        if sel.startswith("meta")
                        else l.first.inner_text().strip()
                    )
                if title:
                    break
            except Exception:
                continue

        # --- Author ---
        author = None
        # We will use the locator to get the entire content of the credits div, as it contains all author/column names
        credits_locator = page.locator(".article__credits-author-pub")
        if credits_locator.count() > 0:
            try:
                # Get the inner text of the entire credits div, e.g., "CTALK - Cito Beltran - The Philippine Star"
                author_raw_text = credits_locator.first.inner_text().strip()

                # Split the text by ' - ' to isolate the author/column parts
                parts = [p.strip() for p in author_raw_text.split(" - ") if p.strip()]

                # Filter out known non-author elements (like the newspaper name)
                # We assume the actual author names (e.g., CTALK, Cito Beltran) are the first items.

                clean_parts = []
                for part in parts:
                    # Skip if the part is the known source/publisher name
                    if "The Philippine Star" in part or "Philstar.com" in part:
                        continue
                    # Also skip internal link prefixes/suffixes if they exist
                    if part and part not in clean_parts:
                        clean_parts.append(part)

                # Join the remaining clean parts using the hyphen separator you want
                author = " - ".join(clean_parts)

            except Exception:
                author = None

        # Fallback to metadata if primary extraction failed
        if not author:
            for sel in ["meta[name='author']"]:
                try:
                    l = page.locator(sel)
                    if l.count() > 0:
                        author = l.first.get_attribute("content")
                        if author:
                            break
                except Exception:
                    continue

        # --- Date ---
        date_str = None
        for sel in DATE_SELECTORS:
            try:
                l = page.locator(sel)
                if l.count() > 0:
                    date_str = (
                        l.first.get_attribute("content")
                        if sel.startswith("meta")
                        else l.first.inner_text().strip()
                    )
                if date_str:
                    break
            except Exception:
                continue

        # --- Content ---
        paragraphs = []
        for sel in CONTENT_SELECTORS:
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

        #  MODIFICATION: Clean content by removing "ADVERTISEMENT" from the beginning
        if content:
            ad_marker = "ADVERTISEMENT"
            if content.startswith(ad_marker):
                # Slice off the marker, then strip leading/trailing whitespace again
                content = content[len(ad_marker) :].lstrip()

        # Validate essential fields
        if not title or not content:
            return {"url": url, "skipped": True, "reason": "Missing title or content"}

        # Parse publishDate to ISO 8601 with timezone (+08:00)
        publishDate = None
        if date_str:
            try:
                if "|" in date_str:
                    date_str = date_str.split("|")[0].strip()

                clean_date = date_str.replace("Published", "").strip()
                dt = parser.parse(clean_date)

                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))

                publishDate = dt.isoformat()
            except Exception:
                publishDate = date_str

        # --- Final Return ---

        domain = urlparse(url).netloc.replace("www.", "")

        return {
            "title": title,
            "content": content,  # Returns the cleaned content
            "publishDate": publishDate,
            "author": author,
            "url": url,
            "source": "Philstar",
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


# Scrape listing page
def collect_and_scrape_listing(listing_url, max_scrolls=200):
    print(f"Starting Philstar scraper with real-time DB integration...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # --- Retry loop for the initial page load ---
        max_load_attempts = 3
        loaded = False
        for attempt in range(1, max_load_attempts + 1):
            try:
                print(f"Navigating to {listing_url} (Attempt {attempt}/{max_load_attempts})...")
                page.goto(listing_url, timeout=60000)
                loaded = True
                break
            except Exception as e:
                print(f"Failed to load {listing_url}: {e}")
                if attempt < max_load_attempts:
                    time.sleep(2)  # Wait before retry
        
        if not loaded:
            print(f"Could not load listing page after {max_load_attempts} attempts. Aborting.")
            browser.close()
            return

        print(f"Fetch existing URLs from the database once per run")
        print(f"Loaded {len(existing_urls)} existing articles to skip duplicates.")

        last_height = 0
        scroll_count = 0
        discovered_urls = set()
        consecutive_too_old = 0
        consecutive_no_new_links = 0

        total_cycles = 0
        while scroll_count < max_scrolls:
            total_cycles += 1
            # --- Collect links from page anchors and filter Philstar article URLs ---
            anchors = page.locator("a[href]").all()

            new_links = []
            for a in anchors:
                try:
                    href = a.get_attribute("href")
                except Exception:
                    href = None
                if not href:
                    continue
                # Removed existing_urls check for Always-Refresh logic
                if (
                    href.startswith("https://www.philstar.com")
                    and href not in discovered_urls
                ):
                    # match typical article path containing yyyy/mm/dd and numeric id
                    import re

                    if re.search(r"/\d{4}/\d{2}/\d{2}/\d+", href):
                        #  Skip if already in database or already found in this session
                        if href in existing_urls or href in discovered_urls:
                            continue
                        new_links.append(href)
                        discovered_urls.add(href)

            print(f"Found {len(new_links)} new articles in this scroll.")

            if not new_links:
                consecutive_no_new_links += 1
                if consecutive_no_new_links >= MAX_CONSECUTIVE_NO_NEW_LINKS:
                    print(f"Stopping: {consecutive_no_new_links} consecutive scrolls with no new links.")
                    break
            else:
                consecutive_no_new_links = 0

            # --- Scrape newly discovered links ---
            for url in new_links:
                print(f"Scraping: {url}")
                article_page = browser.new_page()
                article_data = scrape_philstar_article(article_page, url)
                article_page.close()

                # save_article returns False only if skipped due to age
                is_recent = save_article(article_data)

                if not is_recent:
                    consecutive_too_old += 1
                    if consecutive_too_old >= 5:
                        print(
                            f"Stopping: {consecutive_too_old} consecutive articles are too old (before {DATE_LIMIT})."
                        )
                        browser.close()
                        return
                else:
                    consecutive_too_old = 0  # Reset on any valid found article

                time.sleep(random.uniform(1, 2))  # polite interval

            # --- Scroll down ---
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.5)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                scroll_count += 1
                if scroll_count >= 3:
                    print("Reached end of page, stopping scroll.")
                    break
            else:
                scroll_count = 0
                last_height = new_height

            # Memory hygiene: restart browser and clear logs periodically
            if total_cycles % 10 == 0:
                print(f"Restarting browser at cycle {total_cycles} for memory management")
                try:
                    browser.close()
                except Exception:
                    pass
                
                # Clear console and force garbage collection
                os.system("cls" if os.name == "nt" else "clear")
                gc.collect()
                print(f"Memory cleared and garbage collected at {datetime.now().strftime('%H:%M:%S')}")
                
                time.sleep(1)
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                # Re-navigate to listing page (Philstar infinite scroll state is lost)
                # Note: This effectively "refreshes" the feed, which is fine since we skip duplicates.
                page.goto(listing_url, timeout=60000)

        browser.close()
        print("\nScraping complete!")


def main():
    LISTING_URL = "https://www.philstar.com/"
    collect_and_scrape_listing(LISTING_URL)


if __name__ == "__main__":
    main()
