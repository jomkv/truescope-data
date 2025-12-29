from ..base import BaseScraper
from playwright.async_api import Locator
from data_class.raw_data import RawData
from dataclasses import asdict
from pathlib import Path
import asyncio
import traceback
import csv


class PolitifactScraper(BaseScraper):
    def __init__(
        self,
        csv_path: str | Path,
    ):
        super().__init__(
            output_filename="politifact-factcheck2",
            retry_filename="politifact-factcheck2-retry",
        )
        self.restart_interval = 50  # In articles
        self.csv_path = Path(csv_path)

    def load_urls(self) -> list[str]:
        urls: list[str] = []
        if not self.csv_path.exists():
            print(f"CSV not found at {self.csv_path.resolve()}")
            return urls

        with self.csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = (row.get("url") or "").strip()
                if not url:
                    continue
                if not url.startswith(("http://", "https://")):
                    url = f"https://{url.lstrip('/')}"
                urls.append(url)
        return urls

    async def process(self) -> None:
        await self.start()
        try:
            urls = self.load_urls()
            if not urls:
                print("No URLs loaded from CSV.")
                return

            # Process URLs sequentially
            for i, url in enumerate(urls):
                await self.process_url(url)

                # Clear logs and GC every 50 articles
                if (i + 1) % 50 == 0:
                    await self.clear_logs_and_gc()
                    await self.restart()

        except Exception as e:
            print(traceback.format_exc())
            print(f"Error during scraping: {e}")
        finally:
            await self.quit()

    async def process_url(self, url: str) -> None:
        article_data = await self.extract_data_from_url(url)
        if article_data is None:
            return
        await self.append_to_json(asdict(article_data))
        # await asyncio.sleep(1)

    async def locate_articles(self) -> list[Locator]:
        return await self.page.locator("div.m-statement__quote > a").all()

    async def extract_urls(self, articles: list[Locator]) -> list[str]:
        urls: list[str] = []

        for article in articles:
            href = await article.get_attribute("href")
            if href:
                # Handle relative URLs
                if href.startswith("/"):
                    href = f"https://www.politifact.com{href}"
                urls.append(href)

        return urls

    async def extract_title(self, throw_error=True) -> str:
        return (
            await self.page.locator(
                '//*[@id="top"]/main/section[3]/div/article/div[2]/div/div[1]/div'
            ).inner_text()
        ).strip()

    async def extract_publish_date(self, throw_error=True) -> str:
        return (
            await self.page.locator("div.m-statement__meta")
            .nth(1)
            .locator("div.m-statement__desc")
            .inner_text()
        ).strip()

    async def extract_verdict(self, throw_error=True) -> str:
        return (
            await self.page.locator(
                '//*[@id="top"]/main/section[3]/div/article/div[2]/div/div[2]/div[1]/picture/img'
            ).get_attribute("alt")
        ).strip()

    async def extract_content(self, throw_error=True) -> str:
        content_element = self.page.locator(
            ".t-row:has(article.m-textblock) div.t-row__center"
        )
        content_text = await content_element.all_inner_texts()

        return "\n\n".join(content_text)

    async def extract_data_from_url(self, url: str) -> RawData | int:
        print(f"Scraping {url}")

        if not await self.navigate_with_retry(url):
            await self.append_to_retry(url)
            return None

        try:
            title = await self.extract_title()
            publish_date = await self.extract_publish_date()
            claim = title
            verdict = await self.extract_verdict()
            content = await self.extract_content()
        except Exception as e:
            await self.append_to_retry(url, traceback.format_exc())
            return None

        article_data = RawData(
            title=title,
            content=content,
            publish_date=publish_date,
            url=url,
            source="politifact",
            type="fact-check",
            source_bias=None,
            claim=claim,
            verdict=verdict,
            authors=[],
        )

        return article_data


async def main():
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    csv_path = BASE_DIR / f"outputs/politifact_urls.csv"

    scraper = PolitifactScraper(csv_path=csv_path)
    await scraper.process()


if __name__ == "__main__":
    asyncio.run(main())
