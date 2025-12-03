from .base import BaseScraper
from playwright.async_api import Locator
from data_class.raw_data import RawData
from dataclasses import asdict
import asyncio
import traceback
from datetime import datetime


class RapplerUnifiedScraper(BaseScraper):
    def __init__(self, start_page: int = 6572):
        super().__init__(
            output_filename="rappler-unified", retry_filename="rappler-unified-retry"
        )
        self.start_page = start_page
        self.end_page = 9100  # Stop at this page
        self.restart_interval = 50
        self.log_clear_interval = 5

    async def process(self) -> None:
        await self.start()
        curr_page: int = self.start_page

        try:
            while True:
                # Stop when we go beyond end page
                if curr_page > self.end_page:
                    break

                if (
                    curr_page % self.restart_interval == 0
                    and curr_page != self.start_page
                ):
                    print(f"🔄 Restarting browser at page {curr_page}")
                    await self.restart()

                if (
                    curr_page % self.log_clear_interval == 0
                    and curr_page != self.start_page
                ):
                    await self.clear_logs_and_gc()

                # Scrape from the main Philippines section (covers all categories)
                await self.navigate_with_retry(
                    f"https://www.rappler.com/philippines/page/{curr_page}/"
                )

                urls = await self.extract_article_urls()

                # if len(urls) == 0:
                #     print("📄 No more articles found - scraping complete")
                #     break

                print(f"📊 Processing {len(urls)} articles from page {curr_page}")

                for url in urls:
                    article_data = await self.extract_data_from_url(url)

                    if article_data is None:
                        continue

                    article_data_dict = asdict(article_data)
                    await self.append_to_json(article_data_dict)
                    print(
                        f"✅ Saved: {article_data.type} - {article_data.title[:50]}..."
                    )

                    await asyncio.sleep(0.5)

                curr_page += 1

        except Exception as e:
            print(f"❌ Error: {e}")
            print(traceback.format_exc())
        finally:
            await self.quit()

    async def extract_article_urls(self) -> list[str]:
        """Extract all article URLs from current page"""

        article_elements: list[Locator] = (
            await self.page.locator("div.top-stories")
            .nth(1)
            .locator("h3.post-card__title > a")
            .all()
        )

        urls: list[str] = []

        for article in article_elements:
            href = await article.get_attribute("href")

            # Skip fact check articles
            if self.is_fact_check(href):
                continue

            if href:
                if href.startswith("/"):
                    href = f"https://www.rappler.com{href}"
                urls.append(href)

        return urls

    def is_fact_check(self, url: str) -> bool:
        """Check if URL is a fact check article"""

        # Split URL by "/" and check if any part contains "fact-check"
        url_parts = url.lower().split("/")

        # Return False if any URL part contains "fact-check"
        if any("fact-check" in part for part in url_parts):
            return True

        return False

    async def extract_title(self, throw_error=True) -> str:
        return (await self.page.locator("h1.post-single__title").inner_text()).strip()

    async def extract_publish_date(self, throw_error=True) -> datetime:
        return datetime.fromisoformat(
            await self.page.locator("span.posted-on > time").get_attribute("datetime")
        )

    async def extract_content(self, throw_error=True) -> str:
        try:
            # Remove ad containers first
            await self.page.locator("div.rappler-ad-container").evaluate_all(
                "elements => elements.forEach(el => el.remove())"
            )

            # Extract content from main content area
            content_elements = await self.page.locator(
                "div.post-single__content.entry-content > *"
            ).all()

            content_parts = []
            for element in content_elements:
                text = await element.inner_text()
                if text.strip():
                    content_parts.append(text.strip())

            return "\n\n".join(content_parts)

        except Exception as e:
            if throw_error:
                raise Exception(f"No content found: {e}")
            return ""

    async def extract_authors(self, throw_error=True) -> list[str]:
        try:
            authors: list[str] = list(
                map(
                    str.strip,
                    (
                        await self.page.locator("div.post-single__authors").inner_text()
                    ).split(","),
                )
            )
        except Exception as e:
            return []

        return authors

    async def extract_data_from_url(self, url: str) -> RawData | None:
        print(f"🔍 Scraping {url}")

        if not await self.navigate_with_retry(url):
            await self.append_to_retry(url, "Failed to navigate")
            return None

        try:
            title = await self.extract_title()
            publish_date = await self.extract_publish_date()
            content = await self.extract_content()
            authors = await self.extract_authors()

            return RawData(
                title=title,
                content=content,
                publish_date=publish_date.isoformat(),
                url=url,
                source="rappler",
                type="news",
                source_bias=None,
                claim=None,
                verdict=None,
                authors=authors,
            )

        except Exception as e:
            await self.append_to_retry(url, str(e))
            return None


async def main():
    scraper = RapplerUnifiedScraper()
    await scraper.process()


if __name__ == "__main__":
    asyncio.run(main())
