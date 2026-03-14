#!/usr/bin/env python3
"""24/7 scheduler for Kalshi-Strats pipelines.

Runs four jobs daily:
  08:00 AM ET  — DraftKings scraper pipeline (scrape.py + build_csv.js)
  08:05 AM ET  — Kalshi pregame market-maker (pregame_dk_playerprop.py)
  08:10 AM ET  — Game-time cancel scheduler (cancel_at_gametime.py)
  08:30 AM ET  — Commit and push today's props + logs to GitHub

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
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# ── Paths ──────────────────────────────────────────────────────────────────────

ROOT        = os.path.dirname(os.path.abspath(__file__))
DK_DIR      = os.path.join(ROOT, "Draftkings-Scraper", "player-props-pregame")
KALSHI_DIR  = os.path.join(ROOT, "Kalshi-MM")

PIPELINE_SH   = os.path.join(DK_DIR,     "run_pipeline.sh")
PREGAME_PY    = os.path.join(KALSHI_DIR, "pregame_dk_playerprop.py")
CANCEL_PY     = os.path.join(KALSHI_DIR, "cancel_at_gametime.py")

if platform.system() == "Windows":
    PYTHON_EXE = r"C:\Users\chris\miniconda3\envs\sports_trading\python.exe"
    BASH_EXE   = r"C:\Program Files\Git\bin\bash.exe"
else:
    PYTHON_EXE = os.path.expanduser("~/miniconda3/envs/sports_trading/bin/python")
    BASH_EXE   = "/bin/bash"

LOGS_DIR      = os.path.join(ROOT, "logs")

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


def job_cancel_scheduler() -> None:
    """08:10 — Schedule game-time order cancellations."""
    _run(
        "Cancel-at-Gametime Scheduler",
        [PYTHON_EXE, CANCEL_PY],
    )


def job_git_push() -> None:
    """08:30 — Commit today's props CSVs and logs to GitHub."""
    log.info("=== START: Git push ===")
    try:
        subprocess.run(["git", "-C", ROOT, "add",
                        "Draftkings-Scraper/player-props-pregame/props/",
                        "Draftkings-Scraper/player-props-pregame/logs/",
                        "Kalshi-MM/logs/"],
                       check=True)
        date_str = datetime.now().strftime("%m-%d-%y")
        result = subprocess.run(
            ["git", "-C", ROOT, "commit", "-m", f"Daily run {date_str}"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            subprocess.run(["git", "-C", ROOT, "push"], check=True)
            log.info("=== DONE: Git push ===")
        else:
            # Nothing new to commit
            log.info("=== SKIP: Git push — nothing new to commit ===")
    except Exception as e:
        log.error(f"=== ERROR: Git push — {e} ===")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("Kalshi-Strats scheduler starting …")
    log.info(f"  DK pipeline  : {PIPELINE_SH}")
    log.info(f"  Pregame      : {PREGAME_PY}")
    log.info(f"  Cancel sched : {CANCEL_PY}")

    scheduler = BlockingScheduler(timezone="America/New_York")

    scheduler.add_job(
        job_dk_scraper,
        CronTrigger(hour=8, minute=0, timezone="America/New_York"),
        id="dk_scraper",
        name="DraftKings Scraper Pipeline",
        misfire_grace_time=300,   # fire up to 5 min late if scheduler was down
    )
    scheduler.add_job(
        job_pregame,
        CronTrigger(hour=8, minute=5, timezone="America/New_York"),
        id="pregame",
        name="Pregame DK Player Props",
        misfire_grace_time=300,
    )
    scheduler.add_job(
        job_cancel_scheduler,
        CronTrigger(hour=8, minute=10, timezone="America/New_York"),
        id="cancel_scheduler",
        name="Cancel-at-Gametime Scheduler",
        misfire_grace_time=300,
    )
    scheduler.add_job(
        job_git_push,
        CronTrigger(hour=8, minute=30, timezone="America/New_York"),
        id="git_push",
        name="Git Commit and Push",
        misfire_grace_time=300,
    )

    log.info("Jobs scheduled (all times America/New_York):")
    log.info("  08:00  DraftKings scraper pipeline")
    log.info("  08:05  Pregame market-maker")
    log.info("  08:10  Cancel-at-gametime scheduler")
    log.info("  08:30  Git commit and push")
    log.info("Scheduler running. Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("Scheduler stopped by user.")


if __name__ == "__main__":
    main()
