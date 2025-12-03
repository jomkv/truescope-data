from .base import BaseScraper
from playwright.async_api import Locator
from data_class.raw_data import RawData
from dataclasses import asdict
import asyncio
import traceback
import csv
from pathlib import Path


class PoynterFactcheckScraper(BaseScraper):
    def __init__(self, csv_file: str, start_index: int = 1):
        super().__init__(
            output_filename="poynter-factcheck",
            retry_filename="poynter-factcheck-retry",
        )
        self.csv_file = Path(csv_file)
        self.start_index = start_index
        self.restart_interval = 15
        self.log_clear_interval = 15

    def read_urls_from_csv(self) -> list[str]:
        """Read URLs from CSV file starting from start_index"""
        urls = []
        try:
            with open(self.csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    # Get the ID and URL from each row
                    article_id = int(row['id'])
                    article_url = row['url']
                    
                    # Only include URLs from start_index onwards
                    if article_id >= self.start_index:
                        urls.append(article_url)
                        
            print(f"Loaded {len(urls)} URLs from CSV (starting from ID {self.start_index})")
            return urls
            
        except Exception as e:
            print(f"Error reading CSV file: {e}")
            return []

    async def process(self) -> None:
        await self.start()

        # Read URLs from CSV
        urls = self.read_urls_from_csv()
        
        if not urls:
            print("No URLs found in CSV file")
            return

        # Track current index for restart intervals
        curr_index = self.start_index

        try:
            print(f"Starting to scrape {len(urls)} articles...")
            
            for i, url in enumerate(urls):
                # Restart browser periodically for memory management
                if (curr_index % self.restart_interval == 0 and curr_index != self.start_index):
                    print(f"Restarting browser at article {curr_index} for memory management")
                    await self.restart()
                    await self.clear_logs_and_gc()

                # Extract data from current URL
                article_data = await self.extract_data_from_url(url)

                if article_data is None:
                    curr_index += 1
                    continue

                # Save to JSON
                article_data_dict = asdict(article_data)
                await self.append_to_json(article_data_dict)

                # Small delay between requests
                await asyncio.sleep(0.5)
                
                curr_index += 1
                
                # Progress update
                if curr_index % 5 == 0:
                    print(f"Progress: {curr_index - self.start_index + 1}/{len(urls)} articles processed")

                # Clear logs periodically
                if curr_index % self.log_clear_interval == 0:
                    await self.clear_logs_and_gc()

            print(f"Completed scraping {len(urls)} articles")

        except Exception as e:
            print(traceback.format_exc())
            print(f"Error during scraping: {e}")
        finally:
            await self.quit()

    async def extract_title(self, throw_error=True) -> str:
        return (
            await self.page.locator(
                "h1.article-header__headline.headline_1"
            ).inner_text()
        ).strip()

    async def extract_publish_date(self, throw_error=True) -> str:
        return (await self.page.locator("div.poynter-blog-date").inner_text()).strip()

    async def extract_content(self, throw_error=True) -> str:
        # Get all paragraphs from the content div
        content_paragraphs = await self.page.locator(
            "div.poynter-post-content p"
        ).all_inner_texts()

        # Filter out empty paragraphs and join
        filtered_content = [text.strip() for text in content_paragraphs if text.strip()]

        return "\n\n".join(filtered_content)

    async def extract_authors(self, throw_error=True) -> list[str]:
        try:
            author_elements = await self.page.locator(
                "div.poynter-blog-author.author-info-content__name > a"
            ).all()
            authors = []

            for author_el in author_elements:
                authors.append((await author_el.inner_text()).strip())

            return authors
        except Exception as e:
            return []

    async def extract_data_from_url(self, url: str) -> RawData | None:
        print(f"Scraping: {url}")

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
            source="poynter",
            type="fact-check-no-verdict",
            source_bias=None,
            claim=title,
            verdict=None,
            authors=authors,
        )

        return article_data


async def main():
    # Specify your CSV file path
    csv_file_path = "outputs/poynter_urls.csv"
    
    # Create scraper with CSV file and optional start index
    scraper = PoynterFactcheckScraper(csv_file_path, start_index=1)
    await scraper.process()


if __name__ == "__main__":
    asyncio.run(main())