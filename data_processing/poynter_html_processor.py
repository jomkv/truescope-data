from bs4 import BeautifulSoup
import csv
from pathlib import Path
from typing import List
import logging
import pathlib

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PoynterHtmlProcessor:
    def __init__(self, input_file: str, output_file: str):
        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
        self.urls_found = []

    def extract_urls_from_html(self) -> List[str]:
        """Extract URLs from article elements in the HTML file"""
        try:
            # Read the HTML file
            with open(self.input_file, "r", encoding="utf-8") as f:
                html_content = f.read()

            # Parse with BeautifulSoup
            soup = BeautifulSoup(html_content, "html.parser")

            # Find all article elements
            articles = soup.find_all("article", class_="card-layout")
            logger.info(f"Found {len(articles)} article elements")

            urls = []
            for i, article in enumerate(articles, 1):
                try:
                    # Look for the main article link in the headline
                    headline_link = article.find("h2", class_="card-layout__headline")
                    if headline_link:
                        link_tag = headline_link.find("a", class_="card-layout__link")
                        if link_tag and link_tag.get("href"):
                            url = link_tag["href"]
                            urls.append(url)
                            logger.debug(f"Extracted URL {i}: {url}")
                        else:
                            logger.warning(
                                f"No href found in headline link for article {i}"
                            )
                    else:
                        logger.warning(f"No headline found for article {i}")

                except Exception as e:
                    logger.error(f"Error processing article {i}: {e}")
                    continue

            self.urls_found = urls
            logger.info(f"Successfully extracted {len(urls)} URLs")
            return urls

        except Exception as e:
            logger.error(f"Error reading or parsing HTML file: {e}")
            return []

    def save_urls_to_csv(self, urls: List[str]) -> None:
        """Save URLs to CSV file with ID and URL columns"""
        try:
            # Create output directory if it doesn't exist
            self.output_file.parent.mkdir(parents=True, exist_ok=True)

            # Write URLs to CSV
            with open(self.output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                # Write header
                writer.writerow(["id", "url"])

                # Write URLs with sequential IDs
                for i, url in enumerate(urls, 1):
                    writer.writerow([i, url])

            logger.info(f"Saved {len(urls)} URLs to {self.output_file}")

        except Exception as e:
            logger.error(f"Error saving URLs to CSV: {e}")

    def process(self) -> None:
        """Main processing method"""
        logger.info(f"Starting HTML processing for: {self.input_file}")

        # Extract URLs from HTML
        urls = self.extract_urls_from_html()

        if urls:
            # Save to CSV
            self.save_urls_to_csv(urls)

            # Summary
            logger.info("Processing complete!")
            logger.info(f"Total URLs extracted: {len(urls)}")
            logger.info(f"Output saved to: {self.output_file}")
        else:
            logger.warning("No URLs found in the HTML file")


def main():
    BASE_DIR = pathlib.Path(__file__).resolve().parent.parent

    # Configure paths
    input_file = BASE_DIR / "data_sets/poynter_factcheck/raw.html"
    output_file = BASE_DIR / "outputs/poynter_urls.csv"

    processor = PoynterHtmlProcessor(input_file, output_file)
    processor.process()


if __name__ == "__main__":
    main()
