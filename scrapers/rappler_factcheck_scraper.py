from .base import BaseScraper
from playwright.async_api import Locator
from data_class.raw_data import RawData
from datetime import datetime
from dataclasses import asdict
import asyncio
import traceback


class RapplerScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            output_filename="rappler-factcheck",
            retry_filename="rappler-factcheck-retry",
        )

    async def process(self) -> None:
        await self.start()

        # Track page
        curr_page: int = 1

        try:
            while True:
                print(f"Navigating to page {curr_page}")
                await self.navigate_with_retry(
                    f"https://www.rappler.com/newsbreak/fact-check/page/{curr_page}"
                )

                print("Locating article contents")
                articles = await self.locate_articles()

                print("Extracting URLs from articles")
                urls = await self.extract_urls(articles)

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
        return await self.page.locator("div.archive-article__content > h2 > a").all()

    async def extract_urls(self, articles: list[Locator]) -> list[str]:
        urls: list[str] = []

        for article in articles:
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

    async def extract_claim(self, throw_error=True) -> str:
        english_selector = self.page.locator(
            "div.entry-content p:has-text('Claim:'), li:has(strong:text('Claim:')), h5:has-text('Claim:')"
        )
        if await english_selector.count() > 0:
            claim_full_text = await english_selector.inner_text()
            return claim_full_text.strip().removeprefix("Claim: ")

        p2_selector = self.page.locator("div.entry-content p:has-text('The claim:')")
        if await p2_selector.count() > 0:
            claim_full_text = await p2_selector.inner_text()
            return claim_full_text.strip().removeprefix("The claim: ")

        tagalog_selector = self.page.locator(
            "div.entry-content p:has-text('Ang sabi-sabi:'), li:has(strong:text('Ang sabi-sabi:'))"
        )
        if await tagalog_selector.count() > 0:
            claim_full_text = await tagalog_selector.inner_text()
            return claim_full_text.strip().removeprefix("Ang sabi-sabi: ")

        english_caps_selector = self.page.locator("p:has-text('CLAIM:')")
        if await english_caps_selector.count() > 0:
            claim_full_text = await english_caps_selector.inner_text()
            return claim_full_text.strip().removeprefix("CLAIM: ")

        tagalog_caps_selector = self.page.locator("p:has-text('ANG SABI-SABI:')")
        if await tagalog_caps_selector.count() > 0:
            claim_full_text = await tagalog_caps_selector.inner_text()
            return claim_full_text.strip().removeprefix("ANG SABI-SABI: ")

        raise Exception("No claim element found")

    async def extract_verdict(self, throw_error=True) -> str:
        english_selector = self.page.locator(
            "h5:has-text('Rating:'), p:has-text('Rating:'), li:has(strong:text('Rating:'))"
        )
        if await english_selector.count() > 0:
            rating_text = await english_selector.inner_text()
            return rating_text.strip().removeprefix("Rating: ")

        tagalog_selector = self.page.locator(
            "h5:has-text('Marka:'), p:has-text('Marka:'), li:has(strong:text('Marka:'))"
        )
        if await tagalog_selector.count() > 0:
            rating_text = await tagalog_selector.inner_text()
            return rating_text.strip().removeprefix("Marka: ")

        raise Exception("No verdict element found")

    async def extract_content(self, throw_error=True) -> str:
        parent_div = await self.page.locator(
            "div.post-single__content.entry-content"
        ).all_inner_texts()
        return "\n\n".join(parent_div)

    async def extract_data_from_url(self, url: str) -> RawData | int:
        print(f"Scraping {url}")

        if not await self.navigate_with_retry(url):
            await self.append_to_retry(url)
            return None

        try:
            title = await self.extract_title()
            publish_date = await self.extract_publish_date()
            claim = await self.extract_claim()
            verdict = await self.extract_verdict()
            content = await self.extract_content()
        except Exception as e:
            await self.append_to_retry(url, traceback.format_exc())
            return None

        article_data = RawData(
            title=title,
            content=content,
            publish_date=publish_date.isoformat(),
            url=url,
            source="rappler",
            type="fact-check",
            source_bias=None,
            claim=claim,
            verdict=verdict,
            authors=[],
        )

        return article_data


async def main():
    scraper = RapplerScraper()
    await scraper.process()


if __name__ == "__main__":
    asyncio.run(main())
