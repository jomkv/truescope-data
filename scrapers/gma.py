import json
import time
import random
import sys
import asyncio
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta
from dateutil import parser
import urllib.request
import urllib.error
import gzip
from io import BytesIO
import gc
import os

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from data_cleaning.gmaCleaner import clean_article as GMACleaner
from .utils import (
    save_article_async,
    save_articles_batch_async,
    get_existing_articles_urls,
    DATE_LIMIT,
    MAX_PAGES,
    MAX_CONSECUTIVE_OLD,
    MAX_CONSECUTIVE_NO_NEW_LINKS,
    EMBEDDER,
)

# No longer using API discovery as per USER request
# Using direct archive crawling instead


# Using shared EMBEDDER from utils


async def save_article(article: dict):
    return await save_article_async(article, GMACleaner, EMBEDDER)


async def save_articles_batch(articles: list[dict]):
    return await save_articles_batch_async(articles, GMACleaner, EMBEDDER)


# Scrape a single article page
async def scrape_gma_article(page, url):
    try:
        await page.goto(url, timeout=90000)

        # Title
        title = None
        for sel in [
            "meta[property='og:title']",
            "div.title-line header h1",
            "article h1",
            "h1",
        ]:
            try:
                if sel.startswith("meta"):
                    t = page.locator(sel)
                    if await t.count() > 0:
                        content = await t.first.get_attribute("content")
                        if content:
                            title = content.strip()
                else:
                    t = page.locator(sel)
                    if await t.count() > 0:
                        text = await t.first.inner_text()
                        if text:
                            title = text.strip()
                if title:
                    break
            except Exception:
                continue

        # Author
        author = None
        for sel in [
            "meta[name='author']",
            "meta[property='creator']",
            "div.article-author",
            ".author",
            ".byline",
            ".author-name",
        ]:
            try:
                l = page.locator(sel)
                if await l.count() > 0:
                    if sel.startswith("meta"):
                        content = await l.first.get_attribute("content")
                        if content:
                            author = content.strip()
                    else:
                        text = await l.first.inner_text()
                        if text:
                            author = text.strip()
                    if author:
                        break
            except Exception:
                continue

        # Date
        date_str = None
        for sel in [
            "meta[property='og:pubdate']",
            "meta[property='pubdate']",
            "meta[property='article:published_time']",
            "meta[property='lastmod']",
            "div.article-date",
            "time",
            ".published",
        ]:
            try:
                l = page.locator(sel)
                if await l.count() > 0:
                    if sel.startswith("meta"):
                        content = await l.first.get_attribute("content")
                        if content:
                            date_str = content.strip()
                    else:
                        text = await l.first.inner_text()
                        if text:
                            date_str = text.strip()
                    if date_str:
                        break
            except Exception:
                continue

        # Content - extract text from article paragraphs, excluding ads and noise
        try:
            # Handle cookie banner if it blocks clicks
            cookie_btn = page.locator("button:has-text('I AGREE')").first
            if await cookie_btn.is_visible(timeout=2000):
                await cookie_btn.click()
        except Exception:
            pass

        try:
            # Handle "Read More" button for Balitambayan and mobile pages
            read_more = page.locator(
                ".read-more-btn, button:has-text('Read More'), #ob-readmore-button"
            ).first
            if await read_more.is_visible(timeout=3000):
                await read_more.click()
                await asyncio.sleep(1)  # Wait for expansion
        except Exception:
            pass

        try:
            # Remove unwanted newsletter and related content widgets
            await page.evaluate(
                """
                document.querySelectorAll(".newsletter-widget-container, .newsletter-widget-wrapper, .story_related_content_holder, #story1_related_content, .stories, .ad, .label, .widget-newsletter").forEach(el => el.remove());
            """
            )
        except Exception:
            pass

        paragraphs = []
        for sel in [
            "div.story_main p:not(.ad):not(.label)",
            "div.article-body p:not(.ad):not(.label)",
            "div.article-content p:not(.ad):not(.label)",
            "article p:not(.ad):not(.label)",
        ]:
            try:
                ps = await page.locator(sel).all()
                if ps:
                    for p in ps:
                        text = (await p.inner_text()).strip()
                        # Skip paragraphs that look like ads or labels
                        if (
                            text
                            and not text.upper().startswith("ADVERTISEMENT")
                            and len(text) > 10
                        ):
                            paragraphs.append(text)
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
        source = domain.split(".")[0] if domain else "unknown"

        return {
            "title": title,
            "content": content,
            "publishDate": publishDate,
            "author": author,
            "url": url,
            "source": "GMANETWORK",
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


async def scrape_archive_page(page):
    """Extracts all story links and dates from the current view of the archive page."""
    stories = []
    try:
        # User provided structure: a.story_link.story
        # Inside it: .archive_date_time contains the date
        elements = await page.locator("a.story_link.story").all()
        for el in elements:
            try:
                href = await el.get_attribute("href")
                date_el = el.locator(".archive_date_time")
                date_text = ""
                if await date_el.count() > 0:
                    date_text = await date_el.first.inner_text()
                
                if href:
                    stories.append({
                        "url": href,
                        "date_str": date_text.strip()
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"Error extracting links from archive: {e}")
    return stories


async def collect_and_scrape_archive(archive_url):
    print(f"Starting GMA Archive Crawler (Scrolling Approach)...")
    
    async def start_browser():
        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=True)
        return p, browser

    playwright_context, browser = await start_browser()
    existing_urls = get_existing_articles_urls(EMBEDDER, source="GMANETWORK")
    print(f"Loaded {len(existing_urls)} existing articles to skip duplicates.")

    try:
        page = await browser.new_page()
        await page.goto(archive_url, timeout=90000)
        
        # Handle initial cookie banner
        try:
            cookie_btn = page.locator("button:has-text('I AGREE')").first
            if await cookie_btn.is_visible(timeout=5000):
                await cookie_btn.click()
        except: pass

        discovered_urls = set()
        consecutive_too_old = 0
        empty_cycles = 0
        MAX_EMPTY_CYCLES = 10
        MAX_OLD_THRESHOLD = 5
        
        semaphore = asyncio.Semaphore(3)

        async def process_item(url):
            async with semaphore:
                print(f"Scraping: {url}")
                article_page = None
                try:
                    article_page = await browser.new_page()
                    data = await scrape_gma_article(article_page, url)
                    return await save_article(data)
                except Exception as e:
                    print(f"Error processing {url}: {e}")
                    return True
                finally:
                    if article_page: await article_page.close()

        while True:
            # 1. Scrape current view
            found_items = await scrape_archive_page(page)
            
            new_this_cycle = 0
            for item in found_items:
                url = item["url"]
                date_str = item["date_str"]

                if url in discovered_urls or url in existing_urls:
                    continue
                
                # Check date at list level
                is_old = False
                if date_str:
                    try:
                        # Format: "Apr 14, 2026 10:45 AM"
                        article_dt = parser.parse(date_str)
                        if article_dt.tzinfo is None:
                            article_dt = article_dt.replace(tzinfo=timezone(timedelta(hours=8)))
                        
                        article_iso = article_dt.astimezone(timezone.utc).isoformat()
                        if article_iso < DATE_LIMIT:
                            is_old = True
                    except: pass
                
                if is_old:
                    consecutive_too_old += 1
                    print(f" Skipping list item (too old): {url} ({date_str})")
                    if consecutive_too_old >= MAX_OLD_THRESHOLD:
                        print(f" Stop Threshold Reached: {MAX_OLD_THRESHOLD} consecutive old articles on archive page.")
                        return
                    continue
                else:
                    consecutive_too_old = 0 # Reset on any recent one
                
                # If we are here, it's new and recent
                discovered_urls.add(url)
                new_this_cycle += 1
                await process_item(url)
                await asyncio.sleep(random.uniform(0.5, 1.0))

            print(f"Cycle Complete: {new_this_cycle} new links found.")
            
            if new_this_cycle == 0:
                empty_cycles += 1
                if empty_cycles >= MAX_EMPTY_CYCLES:
                    print(f" Stopping: {MAX_EMPTY_CYCLES} consecutive cycles with no new links.")
                    break
            else:
                empty_cycles = 0

            # 2. Scroll to load more
            print("Scrolling to load more content...")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(3) # Wait for network/loading
            
            # Optional: Move mouse to trigger lazy loading if needed
            await page.mouse.move(random.randint(0, 500), random.randint(0, 500))

    finally:
        print("\nScraping complete. Cleaning up...")
        try:
            await browser.close()
            await playwright_context.stop()
        except Exception:
            pass


async def main():
    LISTING_URL = "https://www.gmanetwork.com/news/archives/topstories/"
    # Using auto-look for latest Feed ID
    await collect_and_scrape_archive(LISTING_URL)
    # python -m scrapers.gma


if __name__ == "__main__":
    asyncio.run(main())
