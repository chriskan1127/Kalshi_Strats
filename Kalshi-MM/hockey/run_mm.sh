#!/usr/bin/env bash
# NHL Kalshi market-maker — post offers then schedule game-time cancellations.
# Scheduled via crontab at 8:15 AM ET (see Kalshi-MM/crontab_aws.txt).
# Requires: atd running  (sudo systemctl enable atd && sudo systemctl start atd)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%m-%d-%y)_run_mm_nhl.log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "===== NHL MM start ====="

log "Activating conda environment: sports_trading"
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate sports_trading

# Run independently — cancel must fire even if MM posting fails
log "Running pregame_dk_nhl_playerprop.py..."
python "$SCRIPT_DIR/pregame_dk_nhl_playerprop.py" >> "$LOG" 2>&1 || log "pregame_dk_nhl_playerprop.py exited non-zero"

log "Running cancel_at_gametime_nhl.py..."
python "$SCRIPT_DIR/cancel_at_gametime_nhl.py" >> "$LOG" 2>&1 || log "cancel_at_gametime_nhl.py exited non-zero"

log "===== NHL MM done ====="
