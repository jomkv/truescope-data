from .base import BaseScraper
from data_class.raw_data import RawData
import asyncio
import json
import traceback
import pathlib


class PolitifactMetadataUpdater(BaseScraper):
    """Updates only publish_date and authors fields from existing URLs"""

    def __init__(self, input_file: str):
        super().__init__(
            output_filename="politifact-metadata-updated",
            retry_filename="politifact-metadata-retry",
        )
        self.input_file = input_file
        self.updated_count = 0
        self.failed_count = 0

        # For memory optimization
        self.restart_every = 50

    async def process(self) -> None:
        await self.start()

        # Load existing data
        with open(self.input_file, "r", encoding="utf-8") as f:
            articles = json.load(f)

        print(f"Updating metadata for {len(articles)} articles...")

        try:
            for idx, article in enumerate(articles, 1):
                url = article.get("url")
                if not url:
                    print(f"Skipping article {idx}: No URL")
                    continue

                print(f"[{idx}/{len(articles)}] Updating {url}")

                updated_fields = await self.extract_metadata_from_url(url)

                if updated_fields:
                    # Update only these specific fields
                    article["publish_date"] = updated_fields[0]
                    article["authors"] = updated_fields[1]
                    self.updated_count += 1
                else:
                    self.failed_count += 1

                # Save progress periodically
                if idx % 10 == 0:
                    await self.save_progress(articles)

                # Maintenance every 50 items
                if idx % self.restart_every == 0:
                    await self.clear_logs_and_gc()
                    print(f"Restarting browser at item {idx} for memory management")
                    await self.restart()

                # await asyncio.sleep(0.5)

            # Final save
            await self.save_progress(articles)

        except Exception as e:
            print(f"Error during update: {e}")
            print(traceback.format_exc())
            await self.save_progress(articles)
        finally:
            print(f"\nUpdate complete!")
            print(f"Successfully updated: {self.updated_count}")
            print(f"Failed: {self.failed_count}")
            await self.quit()

    async def extract_metadata_from_url(self, url: str) -> tuple[str, str] | None:
        """Extract only publish_date and authors"""
        if not await self.navigate_with_retry(url):
            await self.append_to_retry(url)
            return None

        try:
            publish_date = await self.extract_publish_date()
            authors = await self.extract_authors(url)

            return (publish_date, authors)
        except Exception as e:
            print(f"  Error extracting metadata: {e}")
            await self.append_to_retry(url, traceback.format_exc())
            return None

    async def extract_publish_date(self) -> str:
        """Extract actual publish date (not the claim date)"""
        date = await self.page.locator("span.m-author__date").all_inner_texts()
        return date[-1].strip()

    async def extract_authors(self, url: str) -> list[str]:
        """Extract article authors"""
        # Try to find author links
        authors = await self.page.locator("div.m-author__content a").all_inner_texts()

        if len(authors) > 1:
            print(url)

        return authors

    async def save_progress(self, articles: list[dict]):
        """Save current progress to output file"""
        output_path = (
            pathlib.Path(self.output_file).parent
            / f"{pathlib.Path(self.output_file).stem}_progress.json"
        )
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(articles, f, indent=2, ensure_ascii=False)
        print(f"  Progress saved to {output_path}")


async def main():
    BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
    input_file = BASE_DIR / f"outputs_clean/politifact/politifact_cleaned.json"

    updater = PolitifactMetadataUpdater(input_file)
    await updater.process()


if __name__ == "__main__":
    asyncio.run(main())
