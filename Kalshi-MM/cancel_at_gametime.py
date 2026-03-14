#!/usr/bin/env python3
"""Register a Windows Task Scheduler task for each NBA game today.

Each task fires at tip-off time, wakes the computer from sleep if needed,
and runs cancel_game.bat <GAME_CODE> to cancel all open Kalshi orders for
that game.  This script exits immediately after scheduling.

One-time setup required:
    Run in an admin PowerShell:
        powercfg /change wake-timers-enabled 1
    Or: Settings > Power & sleep > Additional power settings > Change plan
    settings > Change advanced power settings > Sleep > Allow wake timers > Enable
"""

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
CANCEL_PY   = os.path.join(SCRIPT_DIR, "cancel_game.py")

# Resolve the Python executable for the current platform
if sys.platform == "win32":
    PYTHON_EXE = r"C:\Users\chris\miniconda3\envs\sports_trading\python.exe"
else:
    PYTHON_EXE = os.path.expanduser("~/miniconda3/envs/sports_trading/bin/python")
LOGS_DIR    = os.path.join(SCRIPT_DIR, "logs")
TASK_PREFIX = "KalshiCancel"
_today      = datetime.now().strftime("%m-%d-%y")

# Global log file handle set in main()
_log_fh = None

def log(msg: str) -> None:
    ts   = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


# ── NBA schedule ──────────────────────────────────────────────────────────────

def _parse_games(raw_games: list[dict], time_key: str) -> list[dict]:
    """Parse a list of raw NBA API game dicts into our internal format."""
    result = []
    for g in raw_games:
        away    = g.get("awayTeam", {}).get("teamTricode", "")
        home    = g.get("homeTeam", {}).get("teamTricode", "")
        utc_str = g.get(time_key, "")
        if not (away and home and utc_str):
            continue
        try:
            start_utc = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        result.append({
            "game_code":  away + home,
            "game_code2": home + away,
            "start_utc":  start_utc,
            "label":      f"{away} @ {home}",
        })
    return result


def _fetch_json(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        log(f"[ERROR] Could not fetch {url}: {e}")
        return None


def get_todays_games() -> list[dict]:
    """Return list of {game_code, game_code2, start_utc, label} for today's future games.

    Tries the live scoreboard first.  If it still shows yesterday's games
    (all in the past — common before ~11 AM ET), falls back to the full
    season schedule filtered by today's local date.
    """
    now = datetime.now(timezone.utc)

    # --- Primary: live scoreboard ---
    data = _fetch_json("https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json")
    if data:
        games = _parse_games(data.get("scoreboard", {}).get("games", []), "gameTimeUTC")
        future = [g for g in games if g["start_utc"] > now]
        if future:
            log(f"[source] live scoreboard ({len(future)} future game(s))")
            return future
        log(f"[source] scoreboard has no future games (still showing yesterday) — falling back to season schedule")

    # --- Fallback: full season schedule (indexed by local date) ---
    data = _fetch_json("https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json")
    if not data:
        return []

    today_str = datetime.now().strftime("%m/%d/%Y")   # local date, e.g. "03/09/2026"
    raw = next(
        (gd.get("games", [])
         for gd in data.get("leagueSchedule", {}).get("gameDates", [])
         if gd.get("gameDate", "").startswith(today_str)),
        []
    )
    games = _parse_games(raw, "gameDateTimeUTC")
    future = [g for g in games if g["start_utc"] > now]
    log(f"[source] season schedule ({len(future)} future game(s) on {today_str})")
    return future


# ── Task Scheduler registration ───────────────────────────────────────────────

def register_task(game: dict) -> bool:
    """Schedule cancel_game.py to run at tip-off.

    Windows: uses PowerShell + Task Scheduler.
    Linux:   uses the `at` command (requires `atd` daemon — `sudo apt install at`).
    """
    now       = datetime.now(timezone.utc)
    start_utc = game["start_utc"]
    label     = game["label"]
    game_code = game["game_code"]

    if start_utc <= now:
        log(f"[SKIP] {label} already started ({int((now - start_utc).total_seconds() / 60)}m ago)")
        return False

    local_start = start_utc.astimezone().replace(tzinfo=None)
    h, rem = divmod(int((start_utc - now).total_seconds()), 3600)
    m, s   = divmod(rem, 60)

    if sys.platform == "win32":
        trigger_str = local_start.strftime("%Y-%m-%dT%H:%M:%S")
        task_name   = f"{TASK_PREFIX}-{game_code}"
        ps_script = f"""
try {{
    $action              = New-ScheduledTaskAction -Execute '{PYTHON_EXE}' -Argument '"{CANCEL_PY}" {game_code}'
    $trigger             = New-ScheduledTaskTrigger -Once -At '{trigger_str}'
    $trigger.EndBoundary = (Get-Date '{trigger_str}').AddHours(1).ToString('s')
    $settings  = New-ScheduledTaskSettingsSet -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -DeleteExpiredTaskAfter (New-TimeSpan -Minutes 30)
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    Register-ScheduledTask -TaskName '{task_name}' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force -ErrorAction Stop | Out-Null
    Write-Output "OK"
}} catch {{
    Write-Output "ERROR: $_"
    exit 1
}}
""".strip()
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, text=True
        )
        ok = result.returncode == 0 and "OK" in result.stdout
        if ok:
            log(f"[SCHEDULED] {label}  in {h:02d}h {m:02d}m {s:02d}s  (task: {task_name})")
        else:
            log(f"[ERROR] Failed to register task for {label}")
            if result.stdout.strip():
                log(f"  stdout: {result.stdout.strip()[:300]}")
            if result.stderr.strip():
                log(f"  stderr: {result.stderr.strip()[:300]}")
        return ok

    else:
        # Linux: schedule via `at` (install with: sudo apt install at)
        time_str = local_start.strftime("%H:%M %Y-%m-%d")
        at_cmd   = f'echo "{PYTHON_EXE} {CANCEL_PY} {game_code}" | at {time_str}'
        result   = subprocess.run(at_cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            log(f"[SCHEDULED] {label}  in {h:02d}h {m:02d}m {s:02d}s  (via at)")
            return True
        else:
            log(f"[ERROR] Failed to schedule {label}")
            if result.stderr.strip():
                log(f"  stderr: {result.stderr.strip()[:300]}")
            return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    global _log_fh
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, f"{_today}_cancel_at_gametime.log")
    _log_fh  = open(log_path, "a", encoding="utf-8")

    try:
        log(f"=== Cancel-at-gametime scheduler started ===")

        if not os.path.exists(PYTHON_EXE):
            log(f"[ERROR] Python not found at {PYTHON_EXE}")
            sys.exit(1)
        if not os.path.exists(CANCEL_PY):
            log(f"[ERROR] cancel_game.py not found at {CANCEL_PY}")
            sys.exit(1)

        games = get_todays_games()
        if not games:
            log("No NBA games found for today.")
            return

        log(f"Found {len(games)} game(s) today:")
        for g in games:
            log(f"  {g['label']}  {g['start_utc'].strftime('%H:%M UTC')}  code={g['game_code']}")

        scheduled = 0
        for game in games:
            if register_task(game):
                scheduled += 1

        log(f"\n{scheduled} task(s) registered in Windows Task Scheduler.")
        log("Tasks visible in Task Scheduler under 'KalshiCancel-*'.")
    finally:
        _log_fh.close()
        _log_fh = None


if __name__ == "__main__":
    main()
