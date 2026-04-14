import time
import asyncio
from typing import Callable, Any
from datetime import date, timedelta
from data_embedding.embedder import Embedding


# Global scraper limits (can be updated at runtime in run_all.py)
MAX_PAGES = 10
MAX_CONSECUTIVE_OLD = 5
MAX_CONSECUTIVE_NO_NEW_LINKS = 10
DATE_LIMIT_DAYS = 3
DATE_LIMIT = date.today() - timedelta(days=DATE_LIMIT_DAYS)
EMBEDDER = Embedding(input_file="")


def get_existing_articles_urls(embedder: Any, source: str = None) -> set[str]:
    """Fetch unique URLs currently in the database, optionally filtered by source."""
    if source:
        print(f"Fetching existing URLs for source: {source}...")
    else:
        print("Fetching existing URLs from database...")
    return embedder.get_existing_urls(source=source)


def save_article_sync(
    article: dict,
    cleaner_func: Callable[[dict], dict],
    embedder: Any,
    ignore_date_limit: bool = False,
) -> bool:
    """
    Standard synchronous article saving pipeline.
    Returns False if skipped due to age, True otherwise.
    """
    if not article or article.get("skipped"):
        return True

    # 1. Clean the article
    cleaned = cleaner_func(article)

    # 2. Date Filtering
    pub_date = cleaned.get("publish_date")
    if not ignore_date_limit and pub_date and pub_date < DATE_LIMIT:
        print(f" Skipping (too old: {pub_date}): {cleaned.get('url')}")
        return False  # Indicate age skip

    # 3. Embed and insert into the database with retries
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            embedder.process_data([cleaned])
            log_url = cleaned.get("url")
            claim_snippet = (
                f" ({cleaned.get('claim', '')[:30]}...)" if cleaned.get("claim") else ""
            )
            print(f" Saved to database: {log_url}{claim_snippet}")
            return True
        except Exception as e:
            print(f" Attempt {attempt}/{max_retries} failed to save to database: {e}")
            if attempt < max_retries:
                time.sleep(2)

    print(
        f" FAILED to save to database after {max_retries} attempts: {cleaned.get('url')}"
    )
    return True  # Not an age skip


async def save_article_async(
    article: dict,
    cleaner_func: Callable[[dict], dict],
    embedder: Any,
    ignore_date_limit: bool = False,
) -> bool:
    """
    Standard asynchronous article saving pipeline.
    Returns False if skipped due to age, True otherwise.
    """
    if not article or article.get("skipped"):
        return True

    # 1. Clean the article
    cleaned = cleaner_func(article)

    # 2. Date Filtering
    pub_date = cleaned.get("publish_date")
    if not ignore_date_limit and pub_date and pub_date < DATE_LIMIT:
        print(f" Skipping (too old: {pub_date}): {cleaned.get('url')}")
        return False  # Indicate age skip

    # 3. Embed and insert into the database with retries
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            # Process data is sync, run in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, embedder.process_data, [cleaned])
            log_url = cleaned.get("url")
            claim_snippet = (
                f" ({cleaned.get('claim', '')[:30]}...)" if cleaned.get("claim") else ""
            )
            print(f" Saved to database: {log_url}{claim_snippet}")
            return True
        except Exception as e:
            print(f" Attempt {attempt}/{max_retries} failed to save to database: {e}")
            if attempt < max_retries:
                await asyncio.sleep(2 * attempt)

    print(
        f" FAILED to save to database after {max_retries} attempts: {cleaned.get('url')}"
    )
    return True  # Not an age skip


async def save_articles_batch_async(
    articles: list[dict],
    cleaner_func: Callable[[dict], dict],
    embedder: Any,
    ignore_date_limit: bool = False,
) -> bool:
    """
    Standard asynchronous article saving pipeline for a batch of articles.
    Returns False if ANY article was skipped due to age, True otherwise.
    (This ensures we stop even if some articles in the batch are new but some are old.)
    """
    if not articles:
        return True

    valid_articles = []
    all_recent = True

    # 1. Clean and Filter articles
    for article in articles:
        if not article or article.get("skipped"):
            continue

        cleaned = cleaner_func(article)
        pub_date = cleaned.get("publish_date")

        if not ignore_date_limit and pub_date and pub_date < DATE_LIMIT:
            print(f"Skipping (too old: {pub_date}): {cleaned.get('url')}")
            all_recent = False
            continue

        valid_articles.append(cleaned)

    if not valid_articles:
        return all_recent

    # 2. Embed and insert into the database with retries
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            # Process data is sync, run in executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, embedder.process_data, valid_articles)

            # Print a summary of the batch
            print(
                f"Successfully saved batch of {len(valid_articles)} articles to database."
            )
            return all_recent
        except Exception as e:
            print(
                f"Attempt {attempt}/{max_retries} failed to save batch to database: {e}"
            )
            if attempt < max_retries:
                await asyncio.sleep(2 * attempt)

    print(
        f"FAILED to save batch of {len(valid_articles)} articles after {max_retries} attempts."
    )
    return all_recent
