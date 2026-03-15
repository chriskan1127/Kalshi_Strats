#!/usr/bin/env bash
# NHL DraftKings props pipeline — scrape + build CSV.
# Scheduled via crontab at 8:10 AM ET (see Kalshi-MM/crontab_aws.txt).

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%m-%d-%y).log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "===== NHL Pipeline start ====="

log "Activating conda environment: sports_trading"
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate sports_trading

log "Running scraper.py..."
python "$SCRIPT_DIR/scraper.py" >> "$LOG" 2>&1
log "scraper.py complete"

log "Running build_csv.js..."
node "$SCRIPT_DIR/build_csv.js" >> "$LOG" 2>&1
log "build_csv.js complete"

log "===== NHL Pipeline done ====="
