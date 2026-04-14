import json
import time
import random
import sys
from pathlib import Path
from urllib.parse import urlparse, urljoin
from datetime import timezone, timedelta
from dateutil import parser
import requests
import gc
import os
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

# -------------------------
# Path and Imports
# -------------------------
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from data_cleaning.manilaBulletinCleaner import clean_article as ManilaBulletinCleaner
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

# -------------------------
# Utilities: normalize links
# -------------------------


# -------------------------
# Utilities: normalize links
# -------------------------
def _normalize_link(link):
    """Normalize and make absolute. Remove trailing slash (except root)."""
    if not link:
        return None
    try:
        link = link.strip()
        if link.startswith("//"):
            link = "https:" + link
        # convert relative to absolute using site root
        link = urljoin("https://mb.com.ph", link)
        parsed = urlparse(link)
        # canonicalize scheme + host (lowercase)
        link = parsed._replace(
            scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower()
        ).geturl()
        # remove trailing slash except for domain root
        if link.endswith("/") and parsed.path != "/":
            link = link.rstrip("/")
        return link
    except Exception:
        return link


# -------------------------
# Load existing URLs (normalized)
# -------------------------


# -------------------------
# Save article safely
# -------------------------
def save_article(article: dict):
    return save_article_sync(article, MBCleaner, EMBEDDER)


# -------------------------
# API listing fetch (MB)
# -------------------------
def fetch_listing_via_api(path_url="/category/world", limit=10, page=None):
    api = "https://mb.com.ph/api/pb/fetch-articles-paginated"
    params = {
        "limit": limit,
        "path_url": path_url,
        "hide_widget_in_pagination": 1,
        # section_id can be left or removed; harmless if ignored
    }
    if page is not None:
        try:
            params["page"] = int(page)
            params["start"] = (int(page) - 1) * int(limit)
        except Exception:
            pass

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    try:
        r = requests.get(api, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        j = r.json()
        if isinstance(j, dict) and j.get("response") == "success":
            data = j.get("data") or []
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


# -------------------------
# Scrape one article (robust)
# -------------------------
def scrape_mb_article(page, url):
    try:
        page.goto(url, timeout=90000)  # 90s
        page.wait_for_selector("article", timeout=20000)
        article_el = page.query_selector("article")
        if not article_el:
            return {"url": url, "skipped": True, "reason": "No article element"}

        # --- JSON-LD detection (best metadata source) ---
        ld_json = None
        for s in page.query_selector_all('script[type="application/ld+json"]'):
            try:
                text = s.inner_text().strip()
                if not text:
                    continue
                parsed = json.loads(text)
                # parsed may be dict or list
                if isinstance(parsed, list):
                    for obj in parsed:
                        t = (obj.get("@type") or obj.get("type") or "").lower()
                        if isinstance(t, str) and "newsarticle" in t:
                            ld_json = obj
                            break
                    if ld_json:
                        break
                elif isinstance(parsed, dict):
                    t = (parsed.get("@type") or parsed.get("type") or "").lower()
                    if isinstance(t, str) and "newsarticle" in t:
                        ld_json = parsed
                        break
            except Exception:
                continue

        # --- Title ---
        title = None
        try:
            h1 = article_el.query_selector("h1")
            if h1:
                title = h1.inner_text().strip()
        except Exception:
            title = None

        if not title:
            meta_og = page.query_selector('meta[property="og:title"]')
            if meta_og:
                title = meta_og.get_attribute("content")
        if not title and ld_json:
            title = ld_json.get("headline") or ld_json.get("name")

        if title:
            title = title.strip()

        # --- Author ---
        author = None
        try:
            a_el = article_el.query_selector(".author-section a")
            if a_el:
                author = a_el.inner_text().strip()
        except Exception:
            author = None

        if not author:
            meta_author = page.query_selector(
                'meta[name="author"]'
            ) or page.query_selector('meta[property="article:author"]')
            if meta_author:
                try:
                    author = meta_author.get_attribute("content")
                except Exception:
                    author = None

        if not author and ld_json:
            a = ld_json.get("author")
            if isinstance(a, dict):
                author = a.get("name")
            elif isinstance(a, str):
                author = a

        if author:
            author = author.strip()

        # --- Date ---
        publishDate = None
        date_str = None
        meta_date = (
            page.query_selector('meta[name="datePublished"]')
            or page.query_selector('meta[property="article:published_time"]')
            or page.query_selector('meta[itemprop="datePublished"]')
        )
        if meta_date:
            try:
                date_str = meta_date.get_attribute("content")
            except Exception:
                date_str = None

        if not date_str:
            # site sometimes includes a visible date element
            date_el = (
                article_el.query_selector(".issue_date")
                or article_el.query_selector(".post-date")
                or article_el.query_selector("time")
            )
            if date_el:
                try:
                    date_str = date_el.inner_text().replace("Published", "").strip()
                except Exception:
                    date_str = None

        if not date_str and ld_json:
            date_str = ld_json.get("datePublished") or ld_json.get("dateCreated")

        if date_str:
            try:
                dt = parser.parse(date_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
                publishDate = dt.isoformat()
            except Exception:
                publishDate = date_str

        # --- Content collection (many fallbacks) ---
        paragraphs = []

        # Try article-specific containers first
        content_selectors = [
            ".article-full-body p",
            ".article-body p",
            ".article-content p",
            ".entry-content p",
            "div[itemprop='articleBody'] p",
            "article p",
            ".article-full-body .article-text",
            ".article-full-body div.article-text",
            ".article-text p",
        ]

        for sel in content_selectors:
            try:
                elems = article_el.query_selector_all(sel)
                for p in elems:
                    try:
                        text = p.inner_text().strip()
                    except Exception:
                        text = None
                    if text:
                        paragraphs.append(text)
                if paragraphs:
                    break
            except Exception:
                continue

        # If not found, try to collect larger blocks (some pages place text in divs)
        if not paragraphs:
            fallback_blocks = [
                ".article-full-body",
                ".article-body",
                ".article-content",
                "article",
            ]
            for sel in fallback_blocks:
                try:
                    block = page.query_selector(sel)
                    if block:
                        try:
                            text = block.inner_text().strip()
                            if text:
                                # split into lines and filter short noise lines
                                lines = [
                                    ln.strip() for ln in text.splitlines() if ln.strip()
                                ]
                                # heuristics: remove lines that are likely adverts or share labels
                                good = [ln for ln in lines if len(ln) > 20]
                                if good:
                                    paragraphs = good
                                    break
                        except Exception:
                            pass
                except Exception:
                    pass

        # last resort: JSON-LD description
        if not paragraphs and ld_json:
            desc = ld_json.get("description")
            if desc and isinstance(desc, str):
                paragraphs = [desc.strip()]

        content = "\n\n".join(paragraphs) if paragraphs else None

        # --- Canonical URL if available ---
        page_url = url
        canonical = page.query_selector("link[rel='canonical']")
        if canonical:
            try:
                cu = canonical.get_attribute("href")
                if cu:
                    page_url = _normalize_link(cu)
            except Exception:
                pass
        else:
            meta_url = page.query_selector("meta[name='url']")
            if meta_url:
                try:
                    mu = meta_url.get_attribute("content")
                    if mu:
                        page_url = _normalize_link(mu)
                except Exception:
                    pass

        # Ensure we have title and content
        if not title or not content:
            return {
                "url": page_url,
                "skipped": True,
                "reason": "Missing title or content",
            }

        return {
            "title": title,
            "content": content,
            "publishDate": publishDate,
            "author": author,
            "url": page_url,
            "source": "MANILA-BULLETIN",
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


# -------------------------
# Listing collector (API first, fallback to browser)
# -------------------------
def collect_and_scrape_listing(listing_url, max_pages=10):
    print(f"Starting Manila Bulletin scraper for: {listing_url}")

    print(f"Fetch existing URLs from the database once per category run")
    print(f"Loaded {len(existing_urls)} existing articles to skip duplicates.")

    print("Attempting to fetch listing via site JSON API with pagination...")
    total_scraped = 0
    first_page_items = fetch_listing_via_api(
        path_url=urlparse(listing_url).path, limit=10, page=1
    )
    api_success = bool(first_page_items)

    if api_success:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            consecutive_too_old = 0
            consecutive_no_new_links = 0
            page_num = 0
            while True:
                page_num += 1
                items = (
                    first_page_items
                    if page_num == 1
                    else fetch_listing_via_api(
                        path_url=urlparse(listing_url).path, limit=10, page=page_num
                    )
                )

                if not items:
                    print(
                        f"API returned no items at page {page_num}  stopping API pagination."
                    )
                    break

                api_page_url = f"{listing_url.rstrip('/')}?page={page_num}"
                print(
                    f"API page {page_num} URL: {api_page_url}: {len(items)} items returned; processing..."
                )

                new_links = 0
                for item in items:
                    # Accept common keys and normalize
                    link = (
                        item.get("link")
                        or item.get("url")
                        or item.get("permalink")
                        or item.get("permalink_url")
                        or item.get("clean_url")
                    )
                    link = _normalize_link(link)
                    if not link:
                        continue

                    #  Skip if already in database
                    if link in existing_urls:
                        # We don't print for every skip to avoid flooding terminal in API mode
                        continue

                    parsed = urlparse(link)
                    if "mb.com.ph" not in parsed.netloc:
                        continue

                    # Scrape it
                    try:
                        print(f"Scraping article: {link}")
                        page = browser.new_page()
                        article_data = scrape_mb_article(page, link)
                        page.close()

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
                            new_links += 1

                        time.sleep(random.uniform(1, 2))
                    except Exception as e:
                        print(f"Error scraping {link}: {e}")

                print(
                    f"API page {page_num} processed {new_links} new links (total scraped: {total_scraped})."
                )

                if new_links == 0:
                    consecutive_no_new_links += 1
                    print(f"No new links found on API page {page_num} ({consecutive_no_new_links}/{MAX_CONSECUTIVE_NO_NEW_LINKS})")
                    if consecutive_no_new_links >= MAX_CONSECUTIVE_NO_NEW_LINKS:
                        print(f"Stopping: {consecutive_no_new_links} consecutive pages with no new links.")
                        break
                else:
                    consecutive_no_new_links = 0

                # Memory hygiene: restart browser and clear logs periodically
                if page_num % 10 == 0:
                    print(f"Restarting browser at API page {page_num} for memory management")
                    try:
                        browser.close()
                    except Exception:
                        pass
                    
                    # Force garbage collection
                    gc.collect()
                    print(f"Memory cleared and garbage collected at {time.strftime('%H:%M:%S')}")
                    
                    time.sleep(1)
                    browser = p.chromium.launch(headless=True)

                time.sleep(random.uniform(0.4, 1.0))

            browser.close()
        print(
            f" API-driven scraping complete. Total articles scraped: {total_scraped}."
        )

    # If API didn't give items, fallback to browser render of listing
    if not api_success:
        print("Falling back to Playwright listing rendering...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            current_url = listing_url
            pages_scraped = 0
            consecutive_too_old = 0
            consecutive_no_new_links = 0

            while current_url and pages_scraped < max_pages:
                # --- Retry loop for page navigation ---
                max_nav_attempts = 3
                nav_success = False
                for attempt in range(1, max_nav_attempts + 1):
                    try:
                        print(f"\nNavigating to {current_url} (Attempt {attempt}/{max_nav_attempts})...")
                        page.goto(current_url, timeout=60000)
                        nav_success = True
                        break
                    except Exception as e:
                        print(f"Failed to load {current_url}: {e}")
                        if attempt < max_nav_attempts:
                            time.sleep(2)

                if not nav_success:
                    print(f"Aborting Manila Bulletin fallback after failing to load {current_url}")
                    break

                try:
                    page.wait_for_load_state("networkidle", timeout=30000)

                    #  Explicitly wait for article elements to ensure links have rendered
                    try:
                        page.wait_for_selector("article", timeout=15000)
                    except Exception:
                        print(
                            "Warning: Timed out waiting for 'article' selector; proceeding anyway."
                        )

                    time.sleep(random.uniform(2, 4))
                except Exception as e:
                    print(f"Could not load listing page {current_url}")
                    break

                # Collect article links
                links = set()
                for a in page.query_selector_all("article a[href]"):
                    try:
                        href = a.get_attribute("href")
                        href = _normalize_link(href)
                        if href and "mb.com.ph" in href:
                            #  Skip if already in database
                            if href in existing_urls:
                                continue
                            links.add(href)
                    except Exception:
                        continue

                print(f"Found {len(links)} new article links on this page.")

                if not links:
                    consecutive_no_new_links += 1
                    if consecutive_no_new_links >= 10:
                        print(
                            f"Stopping: {consecutive_no_new_links} consecutive pages with no new links. Pagination halted to save time."
                        )
                        break
                else:
                    consecutive_no_new_links = 0

                # Scrape content
                for link in links:
                    print(f"Scraping article: {link}")
                    article_page = browser.new_page()
                    article_data = scrape_mb_article(article_page, link)
                    article_page.close()

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

                    time.sleep(random.uniform(1, 2))

                # Next page link if exists
                try:
                    next_btn = page.query_selector("a.pagination-next")
                    if next_btn:
                        href = next_btn.get_attribute("href")
                        current_url = urljoin(current_url, href) if href else None
                    else:
                        current_url = None
                except Exception:
                    current_url = None

                pages_scraped += 1
                
                # Memory hygiene: restart browser and clear logs periodically (Fallback Mode)
                if pages_scraped % 5 == 0:
                    print(f"Restarting browser at fallback page {pages_scraped} for memory management")
                    try:
                        browser.close()
                    except Exception:
                        pass
                    
                    # Force garbage collection
                    gc.collect()
                    print(f"Memory cleared and garbage collected at {time.strftime('%H:%M:%S')}")
                    
                    time.sleep(1)
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()

                time.sleep(random.uniform(1, 2))

            browser.close()
            print("\nScraping complete (Playwright fallback).")


def main():
    CATEGORIES = [
        "https://mb.com.ph/category/philippines/",
        "https://mb.com.ph/category/world/",
        "https://mb.com.ph/category/business/",
        "https://mb.com.ph/category/opinion/",
        "https://mb.com.ph/category/lifestyle/",
        "https://mb.com.ph/category/entertainment/",
        "https://mb.com.ph/category/sports/",
    ]

    for cat_url in CATEGORIES:
        print(f"\n=== Starting category: {cat_url} ===")
        collect_and_scrape_listing(cat_url, max_pages=MAX_PAGES)


if __name__ == "__main__":
    main()
