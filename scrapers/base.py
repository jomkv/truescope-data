from playwright.async_api import async_playwright
import json
import os
import asyncio
import pathlib
import gc
from datetime import datetime
from colorama import Fore, Style, init

init(autoreset=True)


class BaseScraper:
    def __init__(
        self, headless=True, output_filename: str = None, retry_filename: str = None
    ):
        BASE_DIR = pathlib.Path(__file__).resolve().parent.parent

        self.pw = None
        self.browser = None
        self.page = None
        self.headless = headless
        self.retry_file = None
        self.output_file = None

        if output_filename:
            self.output_file = BASE_DIR / f"outputs/{output_filename}.json"
        if retry_filename:
            self.retry_file = BASE_DIR / f"outputs/{retry_filename}.json"

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
