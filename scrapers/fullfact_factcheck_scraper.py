from .base import BaseScraper
from playwright.async_api import Locator
from data_class.raw_data import RawData
from dataclasses import asdict
import asyncio
import traceback


class FullfactFactcheckScraper(BaseScraper):
    def __init__(self, start_page: int = 1):
        super().__init__(
            output_filename="fullfact-factcheck",
            retry_filename="fullfact-factcheck-retry",
        )
        self.start_page = start_page
        self.restart_interval = 5  # In pages
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
                    f"https://fullfact.org/latest/?page={curr_page}"
                )

                urls = await self.extract_article_urls()

                if len(urls) == 0:
                    print("📄 No more articles found - scraping complete")
                    break

                # print("Scraping through article URLs")
                for url in urls:
                    article_datas = await self.extract_data_from_url(url)

                    for article_data in article_datas:
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

    async def extract_article_urls(self) -> list[str]:
        """Extract all article URLs from current page"""

        article_elements: list[Locator] = await self.page.locator(
            "div.card.feature-card > a.card-link"
        ).all()

        urls: list[str] = []

        for article in article_elements:
            href = await article.get_attribute("href")

            if href:
                if href.startswith("/"):
                    href = f"https://fullfact.org{href}"
                urls.append(href)

        return urls

    async def extract_title(self, throw_error=True) -> str:
        return (await self.page.locator("h1.mb-3.highlight-js").inner_text()).strip()

    async def extract_claims_and_verdicts(
        self, throw_error=True
    ) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []

        cards = await self.page.locator(
            "div.block-checked_claims div.card-claim-conclusion"
        ).all()

        for card in cards:
            claim_el = card.locator("div.card-claim-body p.card-text")
            verdict_el = card.locator("div.card-conclusion-body p.card-text")

            claim = (
                (await claim_el.inner_text()).strip()
                if await claim_el.count()
                else None
            )
            verdict = (
                (await verdict_el.inner_text()).strip()
                if await verdict_el.count()
                else None
            )

            if claim and verdict:
                pairs.append((claim, verdict))

        return pairs

    async def extract_publish_date(self, throw_error=True) -> str:
        return (await self.page.locator("div.timestamp").first.inner_text()).strip()

    async def extract_content(self, throw_error=True) -> str:
        # Get all paragraphs that come before the HR separator
        content_paragraphs = await self.page.locator(
            "div.cms-content > div.block-rich_text"
        ).all_inner_texts()

        # Filter out empty paragraphs and join
        filtered_content = [text.strip() for text in content_paragraphs if text.strip()]

        return "\n\n".join(filtered_content)

    async def extract_authors(self, throw_error=True) -> list[str]:
        try:
            author_elements = await self.page.locator(
                "ul.citation > li > span > cite"
            ).all()
            authors = []

            for author_el in author_elements:
                authors.append(await author_el.inner_text())

            return authors
        except Exception as e:
            return []

    async def extract_data_from_url(self, url: str) -> list[RawData]:
        print(f"Scraping {url}")

        if not await self.navigate_with_retry(url):
            await self.append_to_retry(url)
            return []

        try:
            title = await self.extract_title()
            publish_date = await self.extract_publish_date()
            content = await self.extract_content()
            authors = await self.extract_authors()

            claims_and_verdicts = await self.extract_claims_and_verdicts()
        except:
            await self.append_to_retry(url, traceback.format_exc())
            return []

        if len(claims_and_verdicts) == 0:
            return [
                RawData(
                    title=title,
                    content=content,
                    publish_date=publish_date,
                    url=url,
                    source="fullfact",
                    type="fact-check-no-verdict",
                    source_bias=None,
                    claim=title,
                    verdict=None,
                    authors=authors,
                )
            ]

        outputs: list[RawData] = []

        for cv in claims_and_verdicts:
            article_data = RawData(
                title=title,
                content=content,
                publish_date=publish_date,
                url=url,
                source="fullfact",
                type="fact-check",
                source_bias=None,
                claim=cv[0],
                verdict=cv[1],
                authors=authors,
            )

            outputs.append(article_data)

        return outputs


async def main():
    scraper = FullfactFactcheckScraper()
    await scraper.process()


if __name__ == "__main__":
    asyncio.run(main())
