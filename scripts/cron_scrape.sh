#!/bin/bash

# ==============================================================================
# TrueScope Scraper Cron Wrapper
# This script is intended to be run by Linux Crontab.
# It sets up the environment and executes the full scraper suite.
# ==============================================================================

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$REPO_DIR/scrapers/logs"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_FILE="$LOG_DIR/scrape_$TIMESTAMP.log"

# Force UTF-8 mode for Python to prevent encoding crashes on the server
export PYTHONUTF8=1

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

echo "Starting TrueScope Scraper Run at $(date)" | tee -a "$LOG_FILE"
echo "Repository Directory: $REPO_DIR" | tee -a "$LOG_FILE"

# 1. Navigate to the repo directory
cd "$REPO_DIR" || exit 1

# 2. Check for .env file
if [ ! -f ".env" ]; then
    echo "Error: .env file not found in $REPO_DIR" | tee -a "$LOG_FILE"
    exit 1
fi

# 3. Activate Virtual Environment
# (Assumes .venv exists in the repo root)
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "Error: Virtual environment not found in $REPO_DIR/.venv" | tee -a "$LOG_FILE"
    exit 1
fi

# 4. Run the Scraper Suite
echo "Executing python -m scrapers.run_all..." | tee -a "$LOG_FILE"
python3 -m scrapers.run_all 2>&1 | tee -a "$LOG_FILE"

# 5. Capture Exit Status
STATUS=${PIPESTATUS[0]}

if [ $STATUS -eq 0 ]; then
    echo "--------------------------------------------------" | tee -a "$LOG_FILE"
    echo "✅ Scraper run completed successfully at $(date)" | tee -a "$LOG_FILE"
else
    echo "--------------------------------------------------" | tee -a "$LOG_FILE"
    echo "❌ Scraper run failed with exit code $STATUS at $(date)" | tee -a "$LOG_FILE"
fi

# Cleanup: Deactivate venv
deactivate
