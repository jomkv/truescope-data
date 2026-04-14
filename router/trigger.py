import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from dotenv import load_dotenv

# Add the root directory to sys.path to allow importing from scrapers
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

# Load environment variables
load_dotenv()

# Define the router
router = APIRouter(
    prefix="/trigger",
    tags=["triggers"]
)

# Global lock to prevent overlapping runs
scrape_in_progress = False
last_run_start = None
last_run_end = None

def run_scrape_sequence():
    global scrape_in_progress, last_run_start, last_run_end
    
    # Deferred import inside a thread to keep the event loop free
    # (Avoids loading heavy embedding models during API startup/ping)
    from scrapers.run_all import main as run_all_main
    
    scrape_in_progress = True
    last_run_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        print(f"--- API Triggered Scrape Started at {last_run_start} ---")
        asyncio.run(run_all_main())
        print(f"--- API Triggered Scrape Finished ---")
    except Exception as e:
        print(f"Error during triggered scrape: {e}")
    finally:
        scrape_in_progress = False
        last_run_end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@router.get("")
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    token: str = Query(..., description="Security token to start the scrape"),
):
    global scrape_in_progress
    
    # Verify token
    expected_token = os.getenv("SCRAPE_TRIGGER_TOKEN")
    if not expected_token or token != expected_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid token")

    # Check if already running
    if scrape_in_progress:
        return {
            "status": "already_running",
            "message": "A scrape is already in progress.",
            "started_at": last_run_start,
        }

    # Start scrape in background (uses a thread because it's a 'def' task)
    background_tasks.add_task(run_scrape_sequence)
    
    return {
        "status": "success",
        "message": "Scraper sequence initiated in the background.",
        "trigger_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

@router.get("/status")
async def get_status():
    return {
        "scrape_in_progress": scrape_in_progress,
        "last_run_start": last_run_start,
        "last_run_end": last_run_end,
    }
