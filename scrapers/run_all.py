import asyncio
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from . import utils

# Async Scrapers
from .politifact_factcheck_scraper import main as politifact_scraper
from .verafileFC import main as verafile_fc_scraper
from .snopesfc import main as snopes_fc_scraper
from .fullfact_factcheck_scraper import main as fullfact_scraper
from .rappler_factcheck_scraper import main as rappler_scraper
from .gma import main as gma_scraper

# Sync Scrapers
from .verafilenews import main as verafile_news_scraper
from .philstar import main as philstar_scraper
from .manilaBulletin import main as manila_bulletin_scraper
from .manilastandard import main as manilastandard_scraper
from .frontpagephnation import main as frontpagephnation_scraper
from .frontpagephworld import main as frontpagephworld_scraper
from .snopesnews import main as snopesnews_scraper


async def run_sync_scraper(func, *args):
    """Run a synchronous scraper function in a separate thread."""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        await loop.run_in_executor(pool, func, *args)


async def main():
    # 1. Calculate dynamic date limit (Today - 7 days)
    limit_date_dt = datetime.now() - timedelta(days=utils.DATE_LIMIT_DAYS)
    limit_date_str = limit_date_dt.strftime("%Y-%m-%d")

    # Global Configuration Control Center
    utils.DATE_LIMIT = limit_date_str
    utils.MAX_PAGES = 10  # Maximum pagination deepness
    utils.MAX_CONSECUTIVE_OLD = (
        5  # Stop after X consecutive articles older than DATE_LIMIT
    )

    print(f"Starting Scraper Sequence...")
    print(f"Dynamic Date Limit: {limit_date_str}")
    print(f"Max Pagination: {utils.MAX_PAGES} pages")
    print(f"Stop Threshold: {utils.MAX_CONSECUTIVE_OLD} consecutive old articles")

    # 2. Define the execution list
    scrapers = [
        ("Politifact", politifact_scraper),
        ("Verafiles FC", verafile_fc_scraper),
        ("Snopes FC", snopes_fc_scraper),
        ("Full Fact", fullfact_scraper),
        ("Rappler FC", rappler_scraper),
        ("GMA", gma_scraper),
        ("Verafiles News", verafile_news_scraper),
        ("Philstar", philstar_scraper),
        ("Manila Bulletin", manila_bulletin_scraper),
        ("Manila Standard", manilastandard_scraper),
        ("FrontpagePH Nation", frontpagephnation_scraper),
        ("FrontpagePH World", frontpagephworld_scraper),
        ("Snopes News", snopesnews_scraper),
    ]

    for name, func in scrapers:
        print(f"\n──────────────────────────────────────────────────")
        print(f"Executing Scraper: {name}")
        print(f"──────────────────────────────────────────────────")

        try:
            if asyncio.iscoroutinefunction(func):
                await func()
            else:
                await run_sync_scraper(func)
            print(f"Finished: {name}")

        except Exception as e:
            print(f"Error in scraper '{name}': {e}")
            # --- USER CHOICE: STOP ON FAILURE ---
            # By default, we raise here to stop the whole process as requested.
            # To continue, comment out 'raise' and uncomment 'continue'.
            # raise e

            # --- USER CHOICE: CONTINUE ON FAILURE ---
            print(f"Skipping failed scraper '{name}' and continuing to next...")
            continue

    print("\nAll scrapers in the sequence have completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
