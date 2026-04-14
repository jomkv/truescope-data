import json
import time
import random
import sys
import re
from pathlib import Path
from urllib.parse import urlparse, urljoin
from datetime import datetime, timezone, timedelta
from dateutil import parser
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)
import gc
import os

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from data_cleaning.snopesCleaner import clean_article as SnopesNewsCleaner
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


def save_article(article: dict):
    return save_article_sync(article, SnopesNewsCleaner, EMBEDDER)


def _first_locator_text(page, selectors):
    for sel in selectors:
        try:
            l = page.locator(sel)
            if l.count() > 0:
                txt = l.first.inner_text().strip()
                if txt:
                    return txt
        except Exception:
            continue
    return None


def scrape_snopes_news_article(page, url):
    try:
        page.goto(url, timeout=90000)

        title = None
        try:
            t = page.locator(
                ".title-container h1, main#article_main .title-container h1, .title-container h1[itemprop=headline]"
            )
            if t.count() > 0:
                title = t.first.inner_text().strip()
        except Exception:
            title = None

        if not title:
            for sel in [
                "h1.entry-title",
                "h1.post-title",
                "h1[itemprop=headline]",
                "article h1",
                "h1",
            ]:
                try:
                    t = page.locator(sel)
                    if t.count() > 0:
                        title = t.first.inner_text().strip()
                        break
                except Exception:
                    continue

        # detect if this article is a Fact Check
        is_fact_check = False
        try:
            st = page.locator(".section_title")
            if st.count() > 0:
                try:
                    txt = st.first.inner_text().strip()
                except Exception:
                    txt = ""
                if txt and "fact" in txt.lower():
                    is_fact_check = True
                else:
                    # also detect by presence of the check logo svg
                    if st.locator("svg.circle_check_logo").count() > 0:
                        is_fact_check = True
            else:
                # fallback: any svg with this class anywhere
                if page.locator("svg.circle_check_logo").count() > 0:
                    is_fact_check = True
        except Exception:
            is_fact_check = False

        author = None
        date_str = None
        try:
            author = _first_locator_text(
                page,
                [
                    ".title-container .author_name a.author_link",
                    ".author-container .author_name a.author_link",
                    ".author_name a",
                    ".author_name",
                ],
            )

            d = page.locator(
                ".published_date .publish_date, .publish_date, .author-container .publish_date, .published_date"
            )
            if d.count() > 0:
                date_str = d.first.inner_text().strip()
            else:
                t = page.locator("time, meta[property='article:published_time']")
                if t.count() > 0:
                    for i in range(t.count()):
                        el = t.nth(i)
                        try:
                            dt_attr = el.get_attribute("datetime")
                        except Exception:
                            dt_attr = None
                        if dt_attr:
                            date_str = dt_attr
                            break
                    if not date_str:
                        try:
                            date_str = t.first.inner_text().strip()
                        except Exception:
                            date_str = None
        except Exception:
            pass

        paragraphs = []
        for sel in [
            "#article-content p",
            "article#article-content p",
            ".entry-content p",
            "article .entry-content p",
            "article p",
            "div.article-body p",
            "div.entry p",
        ]:
            try:
                ps = page.locator(sel).all()
                if ps:
                    out = []
                    for p in ps:
                        try:
                            in_figure = p.evaluate(
                                "node => !!node.closest('figure') || !!node.closest('figcaption')"
                            )
                            if in_figure:
                                continue
                            text = p.inner_text().strip()
                            if text:
                                out.append(text)
                        except Exception:
                            continue
                    if out:
                        paragraphs = out
                        break
            except Exception:
                continue

        if not paragraphs:
            try:
                container = page.locator(".entry-content, .article-body, article")
                if container.count() > 0:
                    txt = container.first.inner_text().strip()
                    if txt:
                        paragraphs = [
                            ln.strip() for ln in txt.split("\n") if ln.strip()
                        ]
            except Exception:
                pass

        content = "\n".join(paragraphs) if paragraphs else None

        if not title or not content:
            return {"url": url, "skipped": True, "reason": "Missing title or content"}

        # if fact-check, try to extract claim and verdict
        claim = None
        verdict = None
        if is_fact_check:
            try:
                c = page.locator(
                    "#fact_check_rating_container .claim_cont, .claim_cont"
                )
                if c.count() > 0:
                    claim = c.first.inner_text().strip()
            except Exception:
                claim = None

            if not claim:
                try:
                    heads = page.locator("h3, h2, strong")
                    for i in range(min(50, heads.count())):
                        try:
                            h = heads.nth(i)
                            ht = h.inner_text().strip()
                        except Exception:
                            continue
                        if "claim" in ht.lower():
                            try:
                                sib = h.evaluate_handle(
                                    "node => node.nextElementSibling"
                                )
                                if sib:
                                    txt = page.evaluate("node => node.innerText", sib)
                                    if txt:
                                        claim = txt.strip()
                                        break
                            except Exception:
                                continue
                except Exception:
                    pass

            try:
                v = page.locator(
                    "#main_rating .rating_title_wrap, #fact_check_rating_container .rating_wrapper .rating_title_wrap"
                )
                if v.count() > 0:
                    verdict = v.first.inner_text().strip()
                    verdict = verdict.split("\n")[0].strip()
                else:
                    img = page.locator(
                        "#main_rating img, #fact_check_rating_container img"
                    )
                    if img.count() > 0:
                        alt = img.first.get_attribute("alt")
                        if alt:
                            verdict = alt.strip()
            except Exception:
                verdict = None

            if not verdict:
                try:
                    spans = page.locator("span, strong, p")
                    for i in range(min(100, spans.count())):
                        try:
                            s = spans.nth(i)
                            st = s.inner_text().strip()
                        except Exception:
                            continue
                        if any(
                            k in st.lower()
                            for k in ["truth", "rating", "rating:", "label:"]
                        ):
                            verdict = st
                            break
                except Exception:
                    pass

            # clean up content that starts with 'About this rating'
            if content and content.lower().startswith("about this rating"):
                content = "\n".join(content.split("\n")[1:]).strip()

        publishDate = None
        if date_str:
            try:
                clean_date = re.sub(r"\s+Share.*$", "", date_str)
                dt = parser.parse(clean_date)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone(timedelta(hours=0)))
                publishDate = dt.isoformat()
            except Exception:
                publishDate = date_str

        domain = urlparse(url).netloc.replace("www.", "")
        source = domain.split(".")[0] if domain else "snopes"

        result = {
            "title": title,
            "content": content,
            "publishDate": publishDate,
            "author": author,
            "url": url,
            "source": "SNOPES",
            "sourceBias": None,
        }

        if is_fact_check:
            result.update(
                {
                    "type": "fact-check",
                    "claim": claim,
                    "verdict": verdict,
                    "sourceBias": result.get("sourceBias", None),
                }
            )
        else:
            # For news articles, include claim/verdict/sourceBias keys with nulls
            result.update(
                {"type": "news", "claim": None, "verdict": None, "sourceBias": None}
            )

        return result

    except PlaywrightTimeoutError:
        return {"url": url, "skipped": True, "reason": "Timeout loading article"}
    except PlaywrightError as e:
        return {"url": url, "skipped": True, "reason": str(e)}
    except Exception as e:
        return {"url": url, "skipped": True, "reason": str(e)}


def collect_and_scrape_listing(listing_url, max_attempts=3):
    print(f"Starting Snopes News scraper with real-time DB integration...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        url = listing_url
        discovered_urls = set()
        consecutive_too_old = 0
        consecutive_no_new_links = 0
        visited_pages = set()

        #  Fetch existing URLs from the database once per run
        existing_urls = get_existing_articles_urls(EMBEDDER, source="SNOPES")
        print(f"Loaded {len(existing_urls)} existing articles to skip duplicates.")

        page_count = 0
        while url:
            page_count += 1
            if url in visited_pages:
                print(
                    "Already visited this listing page  stopping to avoid loop:", url
                )
                break
            visited_pages.add(url)

            loaded = False
            for attempt in range(1, max_attempts + 1):
                try:
                    page.goto(url, timeout=60000)
                    loaded = True
                    break
                except Exception as e:
                    wait = 0.5 * (2 ** (attempt - 1))
                    print(
                        f"Attempt {attempt}/{max_attempts} failed for {url}: {e}. Retrying in {wait:.1f}s..."
                    )
                    time.sleep(wait)

            if not loaded:
                print(
                    f"Failed to load listing page after {max_attempts} attempts: {url}"
                )
                break

            anchors = page.locator(
                "#article-list .article_wrapper a.outer_article_link_wrapper, #list_template_wrapper .article_wrapper a.outer_article_link_wrapper"
            ).all()
            new_links = []
            if not anchors:
                anchors = page.locator("a").all()

            for a in anchors:
                try:
                    href = a.get_attribute("href")
                except Exception:
                    href = None
                if not href:
                    continue
                if href.startswith("/"):
                    href = urljoin(listing_url, href)
                parsed = urlparse(href)
                domain = parsed.netloc.replace("www.", "")
                # accept any Snopes article links found on the politics listing
                if "snopes.com" in domain and href not in discovered_urls:
                    #  Skip if already in database
                    if href in existing_urls:
                        continue
                    new_links.append(href)
            print(f"New links this cycle: {len(new_links)}")

            if not new_links:
                consecutive_no_new_links += 1
                print(f"No new links found on page {page_count} ({consecutive_no_new_links}/{MAX_CONSECUTIVE_NO_NEW_LINKS})")
                if consecutive_no_new_links >= MAX_CONSECUTIVE_NO_NEW_LINKS:
                    print(f" Stopping: {consecutive_no_new_links} consecutive pages with no new links.")
                    break
            else:
                consecutive_no_new_links = 0

            for link in new_links:
                print(f"Scraping: {link}")
                article_page = browser.new_page()
                data = scrape_snopes_news_article(article_page, link)
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

                time.sleep(random.uniform(0.6, 1.3))

            next_href = None
            try:
                sel = page.query_selector(
                    'a.next-button, #next-previous a.next-button, a[rel="next"], a.next, a[aria-label="Next"]'
                )
                if sel:
                    nh = sel.get_attribute("href")
                    if nh:
                        next_href = nh
            except Exception:
                pass

            if not next_href:
                try:
                    p_anchors = page.locator("a").all()
                    candidates = {}
                    for a in p_anchors:
                        try:
                            href = a.get_attribute("href")
                        except Exception:
                            href = None
                        if not href:
                            continue
                        if (
                            "/page/" in href
                            or "pagenum=" in href
                            or "page=" in href
                            or "?p=" in href
                        ):
                            full = urljoin(listing_url, href)
                            candidates[full] = full
                    for cand in sorted(candidates.keys()):
                        if cand != url:
                            next_href = cand
                            break
                except Exception:
                    next_href = None

            if next_href:
                next_url = urljoin(listing_url, next_href)
                if next_url == url:
                    print("Pagination next link same as current page  stopping.")
                    break
                print(f"Following pagination to: {next_url}")

                try:
                    browser.close()
                except Exception:
                    pass

                time.sleep(0.5)

                try:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                except Exception as e:
                    print(f"Failed to relaunch browser: {e}")
                    break

                url = next_url
                time.sleep(0.5)

                # Clear console and force garbage collection
                os.system("cls" if os.name == "nt" else "clear")
                gc.collect()
                print(f"Memory cleared and garbage collected at {datetime.now().strftime('%H:%M:%S')}")
                
                continue
            else:
                print("No pagination link found  stopping.")
                try:
                    browser.close()
                except Exception:
                    pass


def main():
    # default politics listing
    LISTING_URL = "https://www.snopes.com/category/politics/"
    collect_and_scrape_listing(LISTING_URL)


if __name__ == "__main__":
    main()
