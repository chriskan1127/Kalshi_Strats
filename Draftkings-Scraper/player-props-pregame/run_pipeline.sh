#!/usr/bin/env bash
# DraftKings props pipeline — fetches all prop categories and builds a dated CSV.
#
# Schedule with Windows Task Scheduler via run_pipeline.bat (CMD or PowerShell):
#   schtasks /create /tn "DK Props Pipeline" /tr "C:\Users\chris\Sports-Trading\Draftkings-Scraper\run_pipeline.bat" /sc daily /st 08:00 /f
#
# To remove the scheduled task:
#   schtasks /delete /tn "DK Props Pipeline" /f

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%m-%d-%y).log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "===== Pipeline start ====="

# Activate conda environment
log "Activating conda environment: sports_trading"
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate sports_trading

# Step 1: scrape.py — fetches all prop categories, writes dk_props_latest.json
log "Running scrape.py..."
python "$SCRIPT_DIR/scrape.py" >> "$LOG" 2>&1
log "scrape.py complete"

# Step 2: build_csv.js — flattens JSON into mm-dd-yy_props.csv
log "Running build_csv.js..."
node "$SCRIPT_DIR/build_csv.js" >> "$LOG" 2>&1
log "build_csv.js complete"

log "===== Pipeline done ====="
