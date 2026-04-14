import json
import time
import asyncio
import sys
import gc
import os
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

from data_cleaning.veraFilesNewsCleaner import clean_article as VeraNewsCleaner
from .utils import (
    save_article_sync,
    get_existing_articles_urls,
    DATE_LIMIT,
    MAX_PAGES as UTILS_MAX_PAGES,
    MAX_CONSECUTIVE_OLD,
    MAX_CONSECUTIVE_NO_NEW_LINKS,
    EMBEDDER,
)

# Using shared EMBEDDER from utils

# --- Configuration ---
LISTING_URL = "https://verafiles.org/issues-archive/2/all/30"
# MAX_PAGES now from utils

# --- Helper Functions ---


def save_article(article: dict):
    return save_article_sync(article, VeraNewsCleaner, EMBEDDER)


def _goto_with_retries(
    page,
    url: str,
    attempts: int = 3,
    timeout: int = 90000,
    wait_for_selector: str | None = None,
    wait_timeout: int = 10000,
) -> bool:
    """Try to load a page up to `attempts` times. Returns True on success, False on final failure."""
    for attempt in range(1, attempts + 1):
        try:
            page.goto(url, timeout=timeout)
            if wait_for_selector:
                page.wait_for_selector(wait_for_selector, timeout=wait_timeout)
            return True
        except PlaywrightTimeoutError:
            print(f" Timeout loading {url} (attempt {attempt}/{attempts}).")
            if attempt < attempts:
                sleep_time = random.uniform(1.0, 2.0)
                print(f"   Retrying after {sleep_time:.1f}s...")
                time.sleep(sleep_time)
                continue
            return False
        except Exception as e:
            print(f" Error loading {url} (attempt {attempt}/{attempts}): {e}")
            if attempt < attempts:
                time.sleep(random.uniform(0.5, 1.0))
                continue
            return False


def scrape_verafile_article(page, url: str) -> dict:
    """Scrapes a single article URL for relevant fields."""
    # Try loading the article page with retries to handle transient timeouts
    try:
        ok = _goto_with_retries(page, url, attempts=3, timeout=90000)
        if not ok:
            return {
                "url": url,
                "skipped": True,
                "reason": "Timeout loading article after 3 attempts",
            }

        # --- Title ---
        title = None
        for sel in ["h1.entry-title", "article h1", "h1", "meta[property='og:title']"]:
            try:
                if sel.startswith("meta"):
                    t = page.locator(sel).first
                    if t.count() > 0:
                        title = t.get_attribute("content")
                else:
                    t = page.locator(sel).first
                    if t.count() > 0:
                        title = t.inner_text().strip()
                if title:
                    break
            except Exception:
                continue

        # --- Author ---
        author = None
        for sel in [".author", ".byline", ".entry-author", "meta[name='author']"]:
            try:
                l = page.locator(sel).first
                if l.count() > 0:
                    author = (
                        l.inner_text().strip()
                        if not sel.startswith("meta")
                        else l.get_attribute("content")
                    )
                    if author:
                        break
            except Exception:
                continue

        # --- Date ---
        date_str = None
        for sel in [
            "time",
            ".entry-date",
            ".published",
            "meta[property='article:published_time']",
        ]:
            try:
                l = page.locator(sel).first
                if l.count() > 0:
                    if sel == "time":
                        date_str = l.get_attribute("datetime")
                    elif sel.startswith("meta"):
                        date_str = l.get_attribute("content")
                    else:
                        date_str = l.inner_text().strip()
                    if date_str:
                        break
            except Exception:
                continue

        # --- Content paragraphs ---
        paragraphs = []
        content_selectors = [
            "div.entry-content p",
            "div.is-fact-check.entry-content p",
            "div.is-fact-check p",
            "div.post-content p",
            "article p",
            "div[class*='entry-content'] p",
            "main p",
        ]
        for sel in content_selectors:
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

        # (Claim/verdict extraction removed  news articles don't include structured fact-check blocks)

        # --- Validation ---
        if not title or (not content and not date_str):
            return {
                "url": url,
                "skipped": True,
                "reason": "Missing title or essential fields",
            }

        # --- Date Parsing ---
        publishDate = None
        if date_str:
            try:
                clean_date = date_str.replace("Published ", "").strip()
                dt = parser.parse(clean_date)
                # Assume PHT (UTC+8) if no timezone is present
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
                publishDate = dt.isoformat()
            except Exception:
                publishDate = date_str

        # --- Source/Domain Extraction ---
        domain = urlparse(url).netloc.replace("www.", "")
        source = "VERAFILES"

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


def run_scraper(listing_url: str):
    """Main function to iterate through listing pages and scrape individual articles."""
    print(f"Starting Vera Files News scraper with real-time DB integration...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        listing_page = context.new_page()

        #  Fetch existing URLs from the database once per category run
        existing_urls = get_existing_articles_urls(EMBEDDER, source="VERAFILES")
        print(f"Loaded {len(existing_urls)} existing articles to skip duplicates.")

        discovered_urls = set()
        consecutive_too_old = 0

        # Pagination loop
        page_num = 1
        consecutive_no_new_links = 0
        while True:
            if page_num == 1:
                page_url = listing_url
            else:
                page_url = listing_url.rstrip("/") + f"/page/{page_num}"

            print(f"\n--- Visiting listing page {page_num}/{MAX_PAGES}: {page_url} ---")

            # Try loading the listing page with retries (3 attempts)
            ok = _goto_with_retries(
                listing_page,
                page_url,
                attempts=3,
                timeout=60000,
                wait_for_selector="a[href*='/articles/']",
                wait_timeout=10000,
            )
            if not ok:
                print(
                    f" Timed out loading listing page {page_url} after multiple attempts. Stopping pagination."
                )
                break

            # Find anchors that point to article cards
            anchors = listing_page.locator("a[href*='/articles/']").all()

            new_links = []
            for a in anchors:
                try:
                    href = a.get_attribute("href")
                except Exception:
                    continue

                if not href:
                    continue

                # Normalize URL
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = urlparse(listing_url)._replace(path=href).geturl()

                # Filter for valid, unique, and new VERA Files article URLs
                # Removed existing_urls check for Always-Refresh logic
                if (
                    href.startswith("https://verafiles.org/articles/")
                    and href != page_url
                    and href not in discovered_urls
                ):
                    #  Skip if already in database
                    if href in existing_urls:
                        continue
                    new_links.append(href)
                    discovered_urls.add(href)

            print(f"Found {len(new_links)} new links to scrape on page {page_num}.")
            if not new_links:
                consecutive_no_new_links += 1
                if consecutive_no_new_links >= 10:
                    print(
                        f"Stopping: {consecutive_no_new_links} consecutive pages with no new links. Pagination halted to save time."
                    )
                    break
            else:
                consecutive_no_new_links = 0

            # Scrape individual articles
            for url in new_links:
                article_page = context.new_page()
                data = scrape_verafile_article(article_page, url)
                article_page.close()

                # save_article returns False only if skipped due to age
                is_recent = save_article(data)
                if not is_recent:
                    consecutive_too_old += 1
                    if consecutive_too_old >= MAX_CONSECUTIVE_OLD:
                        print(
                            f" Stop requested: {consecutive_too_old} consecutive articles are too old (before {DATE_LIMIT})."
                        )
                        browser.close()
                        return
                else:
                    consecutive_too_old = 0  # Reset on any valid found article

                # Throttle requests
                time.sleep(random.uniform(0.6, 1.3))

            # Memory hygiene: restart browser and clear logs periodically
            if page_num % 10 == 0:
                print(f"Restarting browser at page {page_num} for memory management")
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
                context = browser.new_context()
                listing_page = context.new_page()

            page_num += 1

        browser.close()
        print("\n Scraping complete.")


# --- Main Execution ---
def main():
    LISTING_URL = "https://verafiles.org/issues-archive/2/all/30"
    run_scraper(LISTING_URL)


if __name__ == "__main__":
    main()
