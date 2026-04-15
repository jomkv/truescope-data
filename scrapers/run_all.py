import asyncio
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from . import utils

# Async Scrapers
from .politifact_factcheck_scraper import main as politifact_scraper
from .verafileFC import main as verafile_fc_scraper
from .snopesfc import main as snopes_fc_scraper
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


async def scraper_task_wrapper(name, func, semaphore):
    """
    Wrapper to run a scraper with a concurrency limit.
    """
    async with semaphore:
        start_time = datetime.now()
        print(f"\n[ {start_time.strftime('%H:%M:%S')} ] STARTING: {name}")
        print(f"──────────────────────────────────────────────────")

        try:
            if asyncio.iscoroutinefunction(func):
                await func()
            else:
                await run_sync_scraper(func)

            end_time = datetime.now()
            duration = end_time - start_time
            print(
                f"\n[ {end_time.strftime('%H:%M:%S')} ] FINISHED: {name} (Duration: {duration})"
            )

        except Exception as e:
            print(f"\n[ {datetime.now().strftime('%H:%M:%S')} ] ERROR in '{name}': {e}")
            print(f"Skipping to next available scraper...")


async def main():
    print(f"==================================================")
    print(f"   TRUESCOPE MULTI-SCRAPER RUNNER (SEQUENTIAL)   ")
    print(f"==================================================")
    print(f"Dynamic Date Limit: {utils.DATE_LIMIT}")
    print(f"Max Pagination:    {utils.MAX_PAGES} pages")
    print(f"==================================================\n")

    # 2. Define the execution list
    scrapers = [
        ("Politifact", politifact_scraper),
        ("Verafiles FC", verafile_fc_scraper),
        ("Snopes FC", snopes_fc_scraper),
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

    # limit to 1 concurrent scraper for maximum stability
    semaphore = asyncio.Semaphore(1)

    # Create tasks for all scrapers
    tasks = [scraper_task_wrapper(name, func, semaphore) for name, func in scrapers]

    # Run all tasks (semaphore will ensure only 2 run at a time)
    await asyncio.gather(*tasks)

    print("\n==================================================")
    print("All scrapers have completed their cycles.")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(main())
