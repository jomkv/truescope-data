from .base import BaseScraper
from playwright.async_api import Locator
from data_class.raw_data import RawData
from dataclasses import asdict
import asyncio
import traceback


class PolitifactScraper(BaseScraper):
    def __init__(self, start_page: int = 92):
        super().__init__(
            output_filename="politifact-factcheck",
            retry_filename="politifact-factcheck-retry",
        )
        self.start_page = start_page

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

                print(f"Navigating to page {curr_page}")
                await self.navigate_with_retry(
                    f"https://www.politifact.com/factchecks/list/?page={curr_page}"
                )

                print("Locating article contents")
                articles = await self.locate_articles()

                if len(articles) == 0:
                    print("No more articles found - scraping complete")
                    break

                print("Extracting URLs from articles")
                urls = await self.extract_urls(articles)

                if len(urls) == 0:
                    print("No URLs extracted - may have reached the end")
                    break

                print("Scraping through article URLs")
                for url in urls:
                    article_data = await self.extract_data_from_url(url)

                    if article_data == None:
                        continue

                    article_data_dict = asdict(article_data)

                    await self.append_to_json(article_data_dict)

                    await asyncio.sleep(2)

                curr_page += 1

        except Exception as e:
            print(traceback.format_exc())
            print(f"Error during scraping: {e}")
        finally:
            await self.quit()

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
            await self.page.locator("div.m-statement__quote").nth(1).inner_text()
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
            await self.page.locator("div.m-statement__meter")
            .nth(1)
            .locator("div.c-image > picture > img.c-image__original")
            .get_attribute("alt")
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
    scraper = PolitifactScraper()
    await scraper.process()


if __name__ == "__main__":
    asyncio.run(main())
