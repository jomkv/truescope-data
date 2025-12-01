from .base import BaseScraper
from playwright.async_api import Locator
from data_class.raw_data import RawData
from dataclasses import asdict
import asyncio
import traceback


class FactcheckorgScraper(BaseScraper):
    def __init__(self, start_page: int = 1):
        super().__init__(
            output_filename="factcheckorg-factcheck",
            retry_filename="factcheckorg-factcheck-retry",
        )
        self.start_page = start_page
        self.restart_interval = 2  # In pages
        self.log_clear_interval = 1  # In pages

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

                # print(f"Navigating to page {curr_page}")
                await self.navigate_with_retry(
                    f"https://www.factcheck.org/the-factcheck-wire/page/{curr_page}"
                )

                # print("Locating article contents")
                articles = await self.locate_articles()

                if len(articles) == 0:
                    print("No more articles found - scraping complete")
                    break

                # print("Extracting URLs from articles")
                urls = await self.extract_urls(articles)

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

                    await asyncio.sleep(0.5)

                curr_page += 1
                await self.clear_logs_and_gc()

        except Exception as e:
            print(traceback.format_exc())
            print(f"Error during scraping: {e}")
        finally:
            await self.quit()

    async def locate_articles(self) -> list[Locator]:
        return await self.page.locator(
            "article.post.type-post > h3.entry-title > a"
        ).all()

    async def extract_urls(self, articles: list[Locator]) -> list[str]:
        urls: list[str] = []

        for article in articles:
            href = await article.get_attribute("href")
            if href:
                # Handle relative URLs
                if href.startswith("/"):
                    href = f"https://www.factcheck.org{href}"
                urls.append(href)

        return urls

    async def extract_title(self, throw_error=True) -> str:
        return (await self.page.locator("h1.entry-title").inner_text()).strip()

    async def extract_publish_date(self, throw_error=True) -> str:
        return await self.page.locator("p.posted-on > time").get_attribute("datetime")

    async def extract_content(self, throw_error=True) -> str:
        # Get all paragraphs that come before the HR separator
        content_paragraphs = await self.page.locator(
            "div.entry-content p:not(hr.wp-block-separator ~ p)"
        ).all_inner_texts()

        # Filter out empty paragraphs and join
        filtered_content = [text.strip() for text in content_paragraphs if text.strip()]

        return "\n\n".join(filtered_content)

    async def extract_authors(self, throw_error=True) -> list[str]:
        try:
            author_elements = await self.page.locator("p.byline > a").all()
            authors = []

            for author_el in author_elements:
                authors.append(await author_el.inner_text())

            return authors
        except Exception as e:
            return []

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
            publish_date=publish_date,
            url=url,
            source="factcheckorg",
            type="fact-check-no-verdict",
            source_bias=None,
            claim=title,
            verdict=None,
            authors=authors,
        )

        return article_data


async def main():
    scraper = FactcheckorgScraper()
    await scraper.process()


if __name__ == "__main__":
    asyncio.run(main())
