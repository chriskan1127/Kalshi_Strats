const fs = require('fs');
const path = require('path');

const DIR = __dirname.replace(/\\/g, '/');
const INPUT = path.join(DIR, 'dk_props_latest.json');

// Output filename: mm-dd-yy_props.csv
const now = new Date();
const mm  = String(now.getMonth() + 1).padStart(2, '0');
const dd  = String(now.getDate()).padStart(2, '0');
const yy  = String(now.getFullYear()).slice(-2);
const PROPS_DIR = path.join(DIR, 'props');
if (!fs.existsSync(PROPS_DIR)) fs.mkdirSync(PROPS_DIR);
const OUTPUT = path.join(PROPS_DIR, `${mm}-${dd}-${yy}_props.csv`);

// Display labels for each prop category key from scrape.py
const PROP_TYPE_LABELS = {
  points:        'Points',
  rebounds:      'Rebounds',
  assists:       'Assists',
  threes:        '3-Pointers Made',
  double_double: 'Double Double',
  triple_double: 'Triple Double',
};

if (!fs.existsSync(INPUT)) {
  console.error('dk_props_latest.json not found. Run scrape.py first.');
  process.exit(1);
}

const combined = JSON.parse(fs.readFileSync(INPUT, 'utf8'));
const allRows = [];

for (const [key, data] of Object.entries(combined)) {
  if (!data || !data.selections) {
    console.warn(`  Skipping ${key}: no data`);
    continue;
  }

  const propTypeLabel = PROP_TYPE_LABELS[key] || key;

  // Lookup: eventId -> { matchup, game_date }
  // Convert UTC tip-off time to US Eastern (handles EST/EDT automatically)
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

  // Lookup: marketId -> { matchup, game_date, marketName }
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

    // Strip player name from market name to get the bare prop label (e.g. "Points")
    // then append the threshold label (e.g. "20+")
    const propDetail = market.marketName.replace(player.name, '').trim();
    const playerProp = propDetail ? `${propDetail} ${s.label}` : s.label;

    // Implied probability from display decimal odds = 1 / decimal
    const decOdds = parseFloat(s.displayOdds.decimal);
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
const csv = [header, ...allRows].map(r => r.map(escape).join(',')).join('\n');

fs.writeFileSync(OUTPUT, csv);
console.log(`\nTotal rows: ${allRows.length} -> ${path.basename(OUTPUT)}`);
