const fs   = require('fs');
const path = require('path');

const DIR   = __dirname.replace(/\\/g, '/');
const INPUT = path.join(DIR, 'dk_nhl_latest.json');

// Output filename: mm-dd-yy_nhl_props.csv
const now = new Date();
const mm  = String(now.getMonth() + 1).padStart(2, '0');
const dd  = String(now.getDate()).padStart(2, '0');
const yy  = String(now.getFullYear()).slice(-2);
const PROPS_DIR = path.join(DIR, 'props');
if (!fs.existsSync(PROPS_DIR)) fs.mkdirSync(PROPS_DIR);
const OUTPUT = path.join(PROPS_DIR, `${mm}-${dd}-${yy}_nhl_props.csv`);

// Display labels matching Kalshi-MM/hockey/pregame_dk_nhl_playerprop.py PROP_TO_SERIES keys
const PROP_TYPE_LABELS = {
  goals:   'Goals',
  points:  'Points',
  assists: 'Assists',
};

// Keys in the JSON that are NOT prop categories
const SKIP_KEYS = new Set(['scraped_at', 'schedule']);

if (!fs.existsSync(INPUT)) {
  console.error('dk_nhl_latest.json not found. Run scraper.py first.');
  process.exit(1);
}

const combined = JSON.parse(fs.readFileSync(INPUT, 'utf8'));
const allRows  = [];

for (const [key, data] of Object.entries(combined)) {
  if (SKIP_KEYS.has(key)) continue;
  if (!data || !data.selections) {
    console.warn(`  Skipping ${key}: no data`);
    continue;
  }

  const propTypeLabel = PROP_TYPE_LABELS[key] || key;

  // eventId -> { matchup, game_date }
  const etFmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York',
    year: 'numeric', month: '2-digit', day: '2-digit',
  });
  const eventMap = {};
  (data.events || []).forEach(e => {
    eventMap[e.id] = {
      matchup:   e.name,
      game_date: etFmt.format(new Date(e.startEventDate)),
    };
  });

  // marketId -> { matchup, game_date, marketName }
  const marketMap = {};
  (data.markets || []).forEach(m => {
    const ev = eventMap[m.eventId] || {};
    marketMap[m.id] = {
      matchup:    ev.matchup   || m.eventId,
      game_date:  ev.game_date || '',
      marketName: m.name,
    };
  });

  data.selections.forEach(s => {
    const market = marketMap[s.marketId];
    if (!market) return;
    const player = s.participants && s.participants[0];
    if (!player) return;

    // Strip player name from market name to get bare prop label, append threshold label
    // e.g. marketName "Connor McDavid Goals" → propDetail "Goals" → playerProp "Goals 1+"
    const propDetail  = market.marketName.replace(player.name, '').trim();
    const playerProp  = propDetail ? `${propDetail} ${s.label}` : s.label;

    // Implied probability from display decimal odds
    const decOdds    = parseFloat(s.displayOdds.decimal);
    const impliedProb = (1 / decOdds).toFixed(6);

    allRows.push([
      market.game_date,
      market.matchup,
      player.id,
      player.name,
      propTypeLabel,
      playerProp,
      decOdds,
      impliedProb,
    ]);
  });

  console.log(`  ${key} (${propTypeLabel}): ${data.selections.length} selections`);
}

const header = [
  'game_date',
  'matchup',
  'player_id',
  'player_name',
  'prop_type',
  'player_prop',
  'dk_decimal_odds',
  'implied_probability',
];

const escape = v => '"' + String(v).replace(/"/g, '""') + '"';
const csv    = [header, ...allRows].map(r => r.map(escape).join(',')).join('\n');

fs.writeFileSync(OUTPUT, csv);
console.log(`\nTotal rows: ${allRows.length} -> ${path.basename(OUTPUT)}`);
