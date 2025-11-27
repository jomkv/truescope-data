from playwright.async_api import async_playwright, Page, Playwright, Browser
import json
import os
import asyncio
import pathlib
import gc
from datetime import datetime
from colorama import Fore, Style, init
from data_class.category_keywords import CategoryKeywords
from constants.category_keywords import (
    POLITICS_KEYWORDS,
    SOCIAL_ISSUES_KEYWORDS,
    NEWS_KEYWORDS,
    GOVERNMENT_ENTITIES_KEYWORDS,
)
from typing import Optional
from urllib.parse import urlparse

init(autoreset=True)


class BaseScraper:
    def __init__(
        self,
        headless=True,
        output_filename: str = None,
        retry_filename: str = None,
        enable_categorizer: bool = False,
    ):
        BASE_DIR = pathlib.Path(__file__).resolve().parent.parent

        self.pw: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.headless: bool = headless
        self.retry_file: str = None
        self.output_file: str = None
        self.CATEGORY_KEYWORDS: Optional[CategoryKeywords] = None

        if output_filename:
            self.output_file = BASE_DIR / f"outputs/{output_filename}.json"
        if retry_filename:
            self.retry_file = BASE_DIR / f"outputs/{retry_filename}.json"

        if enable_categorizer:
            self.CATEGORY_KEYWORDS = CategoryKeywords(
                politics=POLITICS_KEYWORDS,
                social_issues=SOCIAL_ISSUES_KEYWORDS,
                news=NEWS_KEYWORDS,
                government_entities=GOVERNMENT_ENTITIES_KEYWORDS,
            )

    async def start(self):
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(headless=self.headless)
        self.page = await self.browser.new_page()

    async def quit(self):
        if self.pw:
            await self.pw.stop()
        if self.browser:
            await self.browser.close()
        if self.page:
            await self.page.close()

    async def restart(self, delay: float = 5):
        await self.quit()
        await asyncio.sleep(delay)
        await self.start()

    async def append_to_json(self, article_data: dict) -> None:
        try:
            # Ensure the outputs directory exists
            os.makedirs(os.path.dirname(self.output_file), exist_ok=True)

            # Read existing data
            existing_data = []
            if os.path.exists(self.output_file):
                with open(self.output_file, "r", encoding="utf-8") as f:
                    try:
                        existing_data = json.load(f)
                    except json.JSONDecodeError:
                        existing_data = []

            # Append new article
            existing_data.append(article_data)

            # Write back to file
            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)

            print(
                f"{Fore.GREEN}✓ Saved article ({len(existing_data)} total articles){Style.RESET_ALL}"
            )

        except Exception as e:
            print(f"Error appending to JSON: {e}")

    async def append_to_retry(self, url: str, reason: str = "") -> None:
        try:
            # Ensure the outputs directory exists
            os.makedirs(os.path.dirname(self.retry_file), exist_ok=True)

            # Read existing data
            existing_data = []
            if os.path.exists(self.retry_file):
                with open(self.retry_file, "r", encoding="utf-8") as f:
                    try:
                        existing_data = json.load(f)
                    except json.JSONDecodeError:
                        existing_data = []

            # Append new retry
            new_retry = {"url": url, "reason": reason}
            existing_data.append(new_retry)

            # Write back to file
            with open(self.retry_file, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)

            print(
                f"{Fore.RED}✗ Saved retry URL ({len(existing_data)} total retries){Style.RESET_ALL}"
            )

        except Exception as e:
            print(f"Error appending to JSON: {e}")

    async def navigate_with_retry(
        self, url: str, max_retries: int = 3, retry_delay: float = 5
    ) -> bool:
        if self.page == None:
            raise Exception("Unable to navigate, no page found")

        for attempt in range(max_retries):
            try:
                print(f"Attempt {attempt + 1}/{max_retries} for {url}")
                await self.page.goto(
                    url,
                    timeout=30000,
                    wait_until="domcontentloaded",
                )
                return True
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)  # Wait before retry
                continue
        return False

    async def clear_logs_and_gc(self):
        """Clear console logs and force garbage collection"""
        try:
            # Clear console
            os.system("cls" if os.name == "nt" else "clear")

            # Force garbage collection
            gc.collect()

            # Clear browser console logs
            if self.page:
                await self.page.evaluate("console.clear()")

            print(
                f"🧹 Logs cleared and garbage collected at {datetime.now().strftime('%H:%M:%S')}"
            )

        except Exception as e:
            print(f"Error clearing logs: {e}")

    @staticmethod
    def _get_keyword_score(text: str, keywords: list[str]) -> float:
        """Calculate keyword density score for categorization"""
        text_lower = text.lower()
        matches = sum(1 for keyword in keywords if keyword in text_lower)
        return matches / len(keywords) if keywords else 0

    def categorize_article(self, title: str, content: str, url: str) -> str:
        """Categorization using multiple signals"""
        if self.CATEGORY_KEYWORDS == None:
            raise Exception("Base Scraper's categorizer is not enabled")

        # Parse URL for category hints
        url_path = urlparse(url).path.lower()

        # URL categories for boosting (not immediate decision)
        url_categories = {
            "politics": ["/politics/", "/government/", "/elections/"],
            "social-issues": ["/nation/", "/metro-manila/", "/regions/"],
            "government": ["/agencies/", "/departments/", "/bureau/", "/office/"],
        }

        text_combined = f"{title} {content}".lower()

        # Calculate base scores for each category including government entities
        scores = {
            "politics": self._get_keyword_score(
                text_combined, self.CATEGORY_KEYWORDS.politics
            ),
            "social_issues": self._get_keyword_score(
                text_combined, self.CATEGORY_KEYWORDS.social_issues
            ),
            "news": self._get_keyword_score(text_combined, self.CATEGORY_KEYWORDS.news),
            "government": self._get_keyword_score(
                text_combined, self.CATEGORY_KEYWORDS.government_entities
            ),
        }

        # Apply URL-based boosts to existing scores
        for category, patterns in url_categories.items():
            if any(pattern in url_path for pattern in patterns):
                if category in scores:
                    scores[category] += 0.3

        # Check if any government entity name appears in the URL path
        url_parts = url_path.split("/")
        if any(
            entity in url_parts for entity in self.CATEGORY_KEYWORDS.government_entities
        ):
            scores["government"] += 0.2

        # Return highest scoring category
        return max(scores, key=scores.get) if max(scores.values()) > 0 else "news"
