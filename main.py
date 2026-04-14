import uvicorn
from fastapi import FastAPI
from router.trigger import router as trigger_router

app = FastAPI(
    title="TrueScope Central Intel API",
    description="Central hub for TrueScope data scrapers and processing.",
    version="1.0.0"
)

# Include sub-routers
app.include_router(trigger_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {
        "message": "Welcome to TrueScope Central Intel API",
        "status": "online",
        "docs_url": "/docs",
        "endpoints": {
            "trigger_scrape": "/api/v1/trigger",
            "trigger_status": "/api/v1/trigger/status"
        }
    }

if __name__ == "__main__":
    # Standard entry point for running directly via 'python main.py'
    # Defaulting to 0.0.0.0 for accessibility on the Droplet
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
