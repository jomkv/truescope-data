from .base import BaseScraper
from playwright.async_api import Locator
from data_class.raw_data import RawData
from dataclasses import asdict
import asyncio
import traceback
from datetime import datetime


class RapplerElectionsScraper(BaseScraper):
    def __init__(self, start_page: int = 1):
        super().__init__(
            output_filename="rappler-elections",
            retry_filename="rappler-elections-retry",
        )
        self.start_page = start_page
        self.restart_interval = 50  # In pages
        self.log_clear_interval = 5  # In pages

    async def process(self) -> None:
        await self.start()

        # Track page
        curr_page: int = self.start_page

        try:
            while True:
                if (
                    curr_page % self.restart_interval == 0
                    and curr_page != self.start_page
                ):
                    print(
                        f"Restarting browser at page {curr_page} for memory management"
                    )
                    await self.restart()

                if (
                    curr_page % self.log_clear_interval == 0
                    and curr_page != self.start_page
                ):
                    await self.clear_logs_and_gc()

                # print(f"Navigating to page {curr_page}")
                await self.navigate_with_retry(
                    f"https://www.rappler.com/philippines/elections/page/{curr_page}/"
                )

                # print("Extracting URLs from articles")
                urls = await self.extract_article_urls()

                if len(urls) == 0:
                    print("No URLs extracted - may have reached the end")
                    break

                # print("Scraping through article URLs")
                for url in urls:
                    article_data = await self.extract_data_from_url(url)

                    if article_data == None:
                        continue

                    article_data_dict = asdict(article_data)

                    await self.append_to_json(article_data_dict)

                    await asyncio.sleep(1)

                curr_page += 1

        except Exception as e:
            print(traceback.format_exc())
            print(f"Error during scraping: {e}")
        finally:
            await self.quit()

    async def extract_article_urls(self) -> list[str]:
        article_elements = await self.page.locator("h3.post-card__title > a").all()

        urls: list[str] = []

        for article in article_elements:
            href = await article.get_attribute("href")
            if href:
                # Handle relative URLs
                if href.startswith("/"):
                    href = f"https://www.rappler.com{href}"
                urls.append(href)

        return urls

    async def extract_title(self, throw_error=True) -> str:
        return (await self.page.locator("h1.post-single__title").inner_text()).strip()

    async def extract_publish_date(self, throw_error=True) -> datetime:
        return datetime.fromisoformat(
            await self.page.locator("span.posted-on > time").get_attribute("datetime")
        )

    async def extract_content(self, throw_error=True) -> str:
        # Remove ad containers
        await self.page.locator("div.rappler-ad-container").evaluate_all(
            "elements => elements.forEach(el => el.remove())"
        )

        # Extract remaining content
        content_elements = await self.page.locator(
            "div.post-single__content.entry-content > *"
        ).all()

        content_parts = []
        for element in content_elements:
            text = await element.inner_text()
            if text.strip():
                content_parts.append(text.strip())

        return "\n\n".join(content_parts)

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

    async def extract_data_from_url(self, url: str) -> RawData | int:
        print(f"Scraping {url}")

        if not await self.navigate_with_retry(url):
            await self.append_to_retry(url)
            return None

        try:
            title = await self.extract_title()
            publish_date = await self.extract_publish_date()
            content = await self.extract_content()
            authors = await self.extract_authors()
        except Exception as e:
            await self.append_to_retry(url, traceback.format_exc())
            return None

        article_data = RawData(
            title=title,
            content=content,
            publish_date=publish_date.isoformat(),
            url=url,
            source="rappler",
            type="elections",
            source_bias=None,
            claim=None,
            verdict=None,
            authors=authors,
        )

        return article_data


async def main():
    scraper = RapplerElectionsScraper()
    await scraper.process()


if __name__ == "__main__":
    asyncio.run(main())
