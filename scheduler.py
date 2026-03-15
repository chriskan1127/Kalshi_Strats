#!/usr/bin/env python3
"""24/7 scheduler for Kalshi-Strats pipelines.

Runs three jobs daily:
  08:00 AM ET  — DraftKings scraper pipeline (scrape.py + build_csv.js)
  08:05 AM ET  — Kalshi pregame market-maker (pregame_dk_playerprop.py)
  08:10 AM ET  — Game-time cancel scheduler (cancel_at_gametime.py)

Start with:
    python scheduler.py

Keep this process alive (e.g. via a system service, screen/tmux session, or
a cloud VM) so it runs around the clock.
"""

import logging
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

# ── Paths ──────────────────────────────────────────────────────────────────────

ROOT             = os.path.dirname(os.path.abspath(__file__))
DK_DIR           = os.path.join(ROOT, "Draftkings-Scraper", "player-props-pregame")
NHL_DK_DIR       = os.path.join(ROOT, "Draftkings-Scraper", "hockey-props-pregame")
KALSHI_DIR       = os.path.join(ROOT, "Kalshi-MM")
NHL_KALSHI_DIR   = os.path.join(ROOT, "Kalshi-MM", "hockey")

PIPELINE_SH      = os.path.join(DK_DIR,         "run_pipeline.sh")
PREGAME_PY       = os.path.join(KALSHI_DIR,     "pregame_dk_playerprop.py")
CANCEL_GAME_PY   = os.path.join(KALSHI_DIR,     "cancel_game.py")

NHL_PIPELINE_SH      = os.path.join(NHL_DK_DIR,     "run_pipeline.sh")
NHL_PREGAME_PY       = os.path.join(NHL_KALSHI_DIR, "pregame_dk_nhl_playerprop.py")
NHL_CANCEL_GAME_PY   = os.path.join(NHL_KALSHI_DIR, "cancel_game_nhl.py")

if platform.system() == "Windows":
    PYTHON_EXE = r"C:\Users\chris\miniconda3\envs\sports_trading\python.exe"
    BASH_EXE   = r"C:\Program Files\Git\bin\bash.exe"
else:
    PYTHON_EXE = os.path.expanduser("~/miniconda3/envs/sports_trading/bin/python")
    BASH_EXE   = "/bin/bash"

LOGS_DIR      = os.path.join(ROOT, "logs")

# Set in main() so job functions can add dynamic jobs to the live scheduler
_scheduler = None

# ── Logging ────────────────────────────────────────────────────────────────────

os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOGS_DIR, "scheduler.log"), encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ── Job helpers ────────────────────────────────────────────────────────────────

def _run(label: str, cmd: list[str]) -> None:
    """Run a subprocess, streaming output to the scheduler log."""
    log.info(f"=== START: {label} ===")
    log.info(f"CMD: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                log.info(f"  {line}")
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                log.warning(f"  STDERR: {line}")
        if result.returncode == 0:
            log.info(f"=== DONE:  {label} (exit 0) ===")
        else:
            log.error(f"=== FAILED: {label} (exit {result.returncode}) ===")
    except Exception as e:
        log.error(f"=== ERROR launching {label}: {e} ===")


# ── Scheduled jobs ─────────────────────────────────────────────────────────────

def job_dk_scraper() -> None:
    """08:00 — DraftKings scraper pipeline."""
    _run(
        "DK Scraper Pipeline",
        [BASH_EXE, "-l", PIPELINE_SH],
    )


def job_pregame() -> None:
    """08:05 — Kalshi pregame market-maker."""
    _run(
        "Pregame DK Player Props",
        [PYTHON_EXE, PREGAME_PY],
    )


def _run_cancel_game(game_code: str, label: str, cancel_py: str) -> None:
    """Fires at tip-off — cancels all open Kalshi orders for the game."""
    _run(f"Cancel {label}", [PYTHON_EXE, cancel_py, game_code])


def _schedule_cancel_jobs(sport: str, cancel_game_py: str, get_games_fn) -> None:
    """Shared logic: fetch today's games and register DateTrigger cancel jobs."""
    from apscheduler.jobstores.base import JobLookupError

    if _scheduler is None:
        log.error(f"{sport} cancel scheduler: _scheduler is None — was main() called?")
        return

    now = datetime.now(timezone.utc)
    try:
        games = get_games_fn()
    except Exception as e:
        log.error(f"{sport} cancel scheduler: failed to fetch games — {e}")
        return

    if not games:
        log.info(f"{sport} cancel scheduler: no games today.")
        return

    scheduled = 0
    for game in games:
        start_utc = game["start_utc"]
        game_code = game["game_code"]
        label     = game["label"]

        if start_utc <= now:
            log.info(f"  [{sport}] SKIP {label} — already started")
            continue

        job_id = f"cancel_{sport.lower()}_{game_code}"
        try:
            _scheduler.remove_job(job_id)
        except JobLookupError:
            pass

        _scheduler.add_job(
            _run_cancel_game,
            DateTrigger(run_date=start_utc),
            args=[game_code, label, cancel_game_py],
            id=job_id,
            name=f"{sport} Cancel {label}",
        )
        h, rem = divmod(int((start_utc - now).total_seconds()), 3600)
        m, s   = divmod(rem, 60)
        log.info(f"  [{sport}] SCHEDULED {label} in {h:02d}h {m:02d}m {s:02d}s")
        scheduled += 1

    log.info(f"{sport} cancel: {scheduled} game(s) registered in APScheduler.")


def job_cancel_scheduler() -> None:
    """08:10 — Register APScheduler date-trigger jobs for each NBA game today."""
    if KALSHI_DIR not in sys.path:
        sys.path.insert(0, KALSHI_DIR)
    from cancel_at_gametime import get_todays_games
    _schedule_cancel_jobs("NBA", CANCEL_GAME_PY, get_todays_games)


def job_dk_scraper_nhl() -> None:
    """08:00 — NHL DraftKings scraper pipeline."""
    _run(
        "NHL DK Scraper Pipeline",
        [BASH_EXE, "-l", NHL_PIPELINE_SH],
    )


def job_pregame_nhl() -> None:
    """08:05 — NHL Kalshi pregame market-maker."""
    _run(
        "NHL Pregame DK Player Props",
        [PYTHON_EXE, NHL_PREGAME_PY],
    )


def job_cancel_scheduler_nhl() -> None:
    """08:10 — Register APScheduler date-trigger jobs for each NHL game today."""
    if NHL_KALSHI_DIR not in sys.path:
        sys.path.insert(0, NHL_KALSHI_DIR)
    try:
        from cancel_at_gametime_nhl import get_todays_games as get_nhl_games
    except ImportError:
        log.warning("NHL cancel_at_gametime_nhl.py not found — skipping NHL cancel scheduling.")
        return
    _schedule_cancel_jobs("NHL", NHL_CANCEL_GAME_PY, get_nhl_games)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    global _scheduler
    log.info("Kalshi-Strats scheduler starting …")
    log.info(f"  NBA pipeline : {PIPELINE_SH}")
    log.info(f"  NBA pregame  : {PREGAME_PY}")
    log.info(f"  NBA cancel   : {CANCEL_PY}")
    log.info(f"  NHL pipeline : {NHL_PIPELINE_SH}")
    log.info(f"  NHL pregame  : {NHL_PREGAME_PY}")
    log.info(f"  NHL cancel   : {NHL_CANCEL_PY}")

    _scheduler = BlockingScheduler(timezone="America/New_York")
    scheduler  = _scheduler

    scheduler.add_job(
        job_dk_scraper,
        CronTrigger(hour=8, minute=0, timezone="America/New_York"),
        id="dk_scraper",
        name="NBA DraftKings Scraper Pipeline",
        misfire_grace_time=300,
    )
    scheduler.add_job(
        job_dk_scraper_nhl,
        CronTrigger(hour=8, minute=0, timezone="America/New_York"),
        id="dk_scraper_nhl",
        name="NHL DraftKings Scraper Pipeline",
        misfire_grace_time=300,
    )
    scheduler.add_job(
        job_pregame,
        CronTrigger(hour=8, minute=5, timezone="America/New_York"),
        id="pregame",
        name="NBA Pregame DK Player Props",
        misfire_grace_time=300,
    )
    scheduler.add_job(
        job_pregame_nhl,
        CronTrigger(hour=8, minute=5, timezone="America/New_York"),
        id="pregame_nhl",
        name="NHL Pregame DK Player Props",
        misfire_grace_time=300,
    )
    scheduler.add_job(
        job_cancel_scheduler,
        CronTrigger(hour=8, minute=10, timezone="America/New_York"),
        id="cancel_scheduler",
        name="NBA Cancel-at-Gametime Scheduler",
        misfire_grace_time=300,
    )
    scheduler.add_job(
        job_cancel_scheduler_nhl,
        CronTrigger(hour=8, minute=10, timezone="America/New_York"),
        id="cancel_scheduler_nhl",
        name="NHL Cancel-at-Gametime Scheduler",
        misfire_grace_time=300,
    )
    log.info("Jobs scheduled (all times America/New_York):")
    log.info("  08:00  NBA + NHL DraftKings scraper pipelines")
    log.info("  08:05  NBA + NHL pregame market-makers")
    log.info("  08:10  NBA + NHL cancel-at-gametime schedulers")
    log.info("Scheduler running. Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("Scheduler stopped by user.")


if __name__ == "__main__":
    main()
