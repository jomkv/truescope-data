import uvicorn
from fastapi import FastAPI
from router.trigger import router as trigger_router

from core.config import API_NAME, API_VERSION, ENVIRONMENT

app = FastAPI(
    title=API_NAME or "TrueScope Central Intel API",
    description=f"Central hub for TrueScope data scrapers and processing. Environment: {ENVIRONMENT}",
    version=API_VERSION or "v1",
    debug=(ENVIRONMENT == "development")
)

# Include sub-routers
api_prefix = f"/api/{API_VERSION}" if API_VERSION else "/api/v1"
app.include_router(trigger_router, prefix=api_prefix)

@app.get("/")
async def root():
    return {
        "message": f"Welcome to {API_NAME or 'TrueScope API'}",
        "status": "online",
        "environment": ENVIRONMENT,
        "docs_url": "/docs",
        "endpoints": {
            "trigger_scrape": f"{api_prefix}/trigger",
            "trigger_status": f"{api_prefix}/trigger/status"
        }
    }

if __name__ == "__main__":
    # Standard entry point for running directly via 'python main.py'
    # Defaulting to 0.0.0.0 for accessibility on the Droplet
    is_dev = ENVIRONMENT == "development"
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=is_dev)
