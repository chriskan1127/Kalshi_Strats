# DraftKings Props Scraper — Pipeline

## How to Run

```bash
python scrape.py   # Step 1: fetch data
node build_csv.js  # Step 2: build spreadsheet
```

Output: `props.csv`

---

## Files

| File | Role |
|---|---|
| `scrape.py` | Fetches all 6 prop categories from DraftKings API, saves `dk_props_latest.json` + a timestamped archive |
| `build_csv.js` | Reads `dk_props_latest.json`, flattens all categories into a single `props.csv` |
| `dk_props_latest.json` | Combined raw JSON — overwritten on every run of `scrape.py` |
| `dk_props_YYYYMMDD_HHMMSS.json` | Timestamped archive — one per run, kept for history |
| `props.csv` | Final output spreadsheet |

---

## Prop Categories Scraped

| Key | Label | Subcategory ID |
|---|---|---|
| `points` | Points | 16477 |
| `rebounds` | Rebounds | 16479 |
| `assists` | Assists | 16478 |
| `threes` | 3-Pointers Made | 16480 |
| `double_double` | Double Double | 13762 |
| `triple_double` | Triple Double | 13759 |

---

## CSV Columns

| Column | Description |
|---|---|
| `game_date` | Date of the game (YYYY-MM-DD, UTC) |
| `matchup` | e.g. `LA Clippers @ GS Warriors` |
| `player_id` | DraftKings internal player ID |
| `player_name` | Full player name |
| `prop_type` | Category label (e.g. `Points`, `Rebounds`) |
| `player_prop` | Prop + threshold (e.g. `Points 20+`) |
| `true_odds` | No-vig decimal odds from DraftKings |
| `implied_probability` | `1 / display decimal odds` (includes vig) |
