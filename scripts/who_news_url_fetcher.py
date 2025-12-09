import requests
import csv
from pathlib import Path
import time
from typing import List, Dict


class WHONewsUrlFetcher:
    def __init__(self, output_file: str):
        self.base_url = "https://www.who.int/api/hubs/newsitems"
        self.base_news_url = "https://www.who.int/news/item"
        self.output_file = Path(output_file)

        # API parameters
        self.params = {
            "sf_site": "15210d59-ad60-47ff-a542-7ed76645f0c7",
            "sf_provider": "OpenAccessDataProvider",
            "sf_culture": "en",
            "$orderby": "PublicationDateAndTime desc",
            "$select": "ItemDefaultUrl,FormatedDate",
            "$format": "json",
            "$top": "100",
            "$skip": "0",
        }

        self.all_urls = []
        self.total_fetched = 0

    def fetch_news_batch(self, skip: int) -> List[Dict]:
        """Fetch a batch of news items with the given skip offset"""
        self.params["$skip"] = str(skip)

        try:
            response = requests.get(self.base_url, params=self.params, timeout=30)
            response.raise_for_status()

            data = response.json()
            return data.get("value", [])

        except requests.exceptions.RequestException as e:
            print(f"Error fetching data at skip={skip}: {e}")
            return []

    def extract_urls_from_batch(self, batch: List[Dict]) -> List[str]:
        """Extract and format complete URLs from batch results"""
        urls = []

        for item in batch:
            item_url = item.get("ItemDefaultUrl", "")
            if item_url:
                # Remove leading slash if present
                item_url = item_url.lstrip("/")
                # Construct complete URL
                complete_url = f"{self.base_news_url}/{item_url}"
                urls.append(complete_url)

        return urls

    def fetch_all_urls(self) -> None:
        """Fetch all news URLs from WHO API"""
        print("Starting to fetch WHO news URLs...")

        skip = 0
        batch_num = 1

        while True:
            print(f"Fetching batch {batch_num} (skip={skip})...")

            # Fetch batch
            batch = self.fetch_news_batch(skip)

            # Check if we've reached the end
            if not batch or len(batch) == 0:
                print(f"Reached the end of results at skip={skip}")
                break

            # Extract URLs from batch
            urls = self.extract_urls_from_batch(batch)
            self.all_urls.extend(urls)
            self.total_fetched += len(urls)

            print(f"Fetched {len(urls)} URLs (Total: {self.total_fetched})")

            # Move to next batch
            skip += 100
            batch_num += 1

            # Small delay to be respectful to the API
            time.sleep(0.5)

        print(f"\nCompleted! Total URLs fetched: {self.total_fetched}")

    def save_to_csv(self) -> None:
        """Save all URLs to CSV file"""
        if not self.all_urls:
            print("No URLs to save")
            return

        # Create output directory if it doesn't exist
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(self.output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)

                # Write header
                writer.writerow(["id", "url"])

                # Write URLs with sequential IDs
                for i, url in enumerate(self.all_urls, 1):
                    writer.writerow([i, url])

            print(f"Saved {len(self.all_urls)} URLs to {self.output_file}")

        except Exception as e:
            print(f"Error saving to CSV: {e}")

    def process(self) -> None:
        """Main processing method"""
        # Fetch all URLs
        self.fetch_all_urls()

        # Save to CSV
        self.save_to_csv()

        # Show sample URLs
        if self.all_urls:
            print("\nSample URLs (first 3):")
            for i, url in enumerate(self.all_urls[:3], 1):
                print(f"{i}. {url}")


def main():
    # Configure output path
    output_file = "outputs/who_news_urls.csv"

    # Create fetcher and run
    fetcher = WHONewsUrlFetcher(output_file)
    fetcher.process()


if __name__ == "__main__":
    main()
