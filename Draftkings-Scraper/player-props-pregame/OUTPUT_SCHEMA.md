# DraftKings API — JSON Output Schema

**Endpoint:** `GET /sites/US-PA-SB/api/sportscontent/controldata/league/leagueSubcategory/v1/markets`
**Query:** NBA (leagueId `42648`) · Player Points Milestones (subcategoryId `16477`)
**Sample fetch:** 3 upcoming games, 32 player prop markets, 273 selections

---

## Top-Level Structure

```
{
  sports:               Array  — sport metadata
  leagues:              Array  — league metadata
  events:               Array  — upcoming games
  markets:              Array  — betting markets (one per player per game)
  selections:           Array  — individual bet options (threshold lines)
  subscriptionPartials: Object — echo of the OData query used
}
```

---

## `sports[]`
One entry per sport. Purely metadata.

| Field | Type | Example |
|---|---|---|
| `id` | string | `"2"` |
| `seoIdentifier` | string | `"basketball"` |
| `name` | string | `"Basketball"` |
| `sortOrder` | number | `60` |

---

## `leagues[]`
One entry per league matching the query.

| Field | Type | Example |
|---|---|---|
| `id` | string | `"42648"` |
| `seoIdentifier` | string | `"nba"` |
| `name` | string | `"NBA"` |
| `sportId` | string | `"2"` |
| `sortOrder` | number | `4858` |
| `tags` | string[] | `["Featured"]` |
| `isTeamSwap` | bool | `true` |

---

## `events[]`
One entry per game. 3 returned in this sample (all `NOT_STARTED`).

| Field | Type | Notes |
|---|---|---|
| `id` | string | Unique event ID |
| `seoIdentifier` | string | URL-safe slug e.g. `"la-clippers-%40-gs-warriors"` |
| `name` | string | `"LA Clippers @ GS Warriors"` |
| `startEventDate` | ISO 8601 string | UTC tip-off time |
| `status` | string | `"NOT_STARTED"` |
| `sportId` / `leagueId` | string | Foreign keys to `sports` / `leagues` |
| `eventParticipantType` | string | `"TwoTeam"` |
| `sortOrder` | number | Display ordering |
| `subscriptionKey` | string | Key into `subscriptionPartials` |
| `participants[]` | object[] | Home + away team objects (see below) |
| `media[]` | object[] | Stats/tracker provider links (BetRadar) |
| `tags[]` | string[] | Feature flags e.g. `"SGP"`, `"PrePack"`, `"YourBetEligible"` |
| `metadata` | object | Game info: `masterLeagueId`, `numberOfParts`, `secondsInOnePart` |

### `events[].participants[]`
Each event has two team participants (`venueRole`: `"Home"` / `"Away"`).

| Field | Notes |
|---|---|
| `id` | Team ID |
| `name` | Display name e.g. `"GS Warriors"` |
| `venueRole` | `"Home"` or `"Away"` |
| `type` | `"Team"` |
| `metadata.retailRotNumber` | Rotation number for the game |
| `metadata.rosettaTeamId/Name` | Canonical team ID/name |
| `metadata.shortName` | Abbreviation e.g. `"GS"` |
| `metadata.teamColor` | Hex color code |
| `seoIdentifier` | URL slug |
| `countryCode` | `"US"` |

---

## `markets[]`
One market per player per game (32 total across 3 games). All are **Points Milestones** props.

| Field | Type | Notes |
|---|---|---|
| `id` | string | Unique market ID |
| `eventId` | string | Links to `events[].id` |
| `sportId` / `leagueId` | string | Foreign keys |
| `name` | string | Player + stat e.g. `"Tyrese Maxey Points"` |
| `subcategoryId` | string | `"16477"` — Points Milestones category |
| `marketType.id` | string | `"12189"` |
| `marketType.name` | string | `"Points Milestones"` |
| `componentMapping.primary` | number | UI component ID (`331`) |
| `correlatedId` | string | Format: `eventId\|marketTypeId\|sportId:playerId` |
| `subscriptionKey` | string | Links to `subscriptionPartials` |
| `sortOrder` | number | Display ordering |
| `tags[]` | string[] | `"SGP"`, `"PlayerProps"`, `"Cashout"`, `"YourBetEligible"` etc. |
| `dynamicMetadata` | object | Usually empty `{}` |

---

## `selections[]`
Individual bet lines for each market. 273 total — roughly **8–10 thresholds per player**.

| Field | Type | Notes |
|---|---|---|
| `id` | string | Composite key encoding market + line |
| `marketId` | string | Links to `markets[].id` |
| `label` | string | Threshold label e.g. `"20+"` |
| `milestoneValue` | number | Numeric threshold (6–35+ range in sample) |
| `trueOdds` | number | Decimal probability (no vig) |
| `displayOdds.american` | string | e.g. `"−281"` or `"+175"` |
| `displayOdds.decimal` | string | e.g. `"1.35"` |
| `displayOdds.fractional` | string | e.g. `"100/281"` |
| `sortOrder` | number | Display ordering |
| `tags[]` | string[] | `"SGP"`, `"MostBalancedOdds"`, `"MostBalancedGlobalProbability"` |
| `metadata` | object | Usually empty `{}` |
| `participants[]` | object[] | Single player (see below) |

### `selections[].participants[]`
Each selection has one player participant.

| Field | Notes |
|---|---|
| `id` | Player ID |
| `name` | Full name e.g. `"Tyrese Maxey"` |
| `type` | `"Player"` |
| `venueRole` | `"HomePlayer"` or `"AwayPlayer"` |
| `statistic.prefix` | Stat type — `"PPG"` (points per game) |
| `statistic.value` | Season average e.g. `24.1` |
| `seoIdentifier` | URL slug |

---

## `subscriptionPartials`
Keyed by `subscriptionKey` (e.g. `"events--527603363"`). Echoes back the OData filter used to fetch the data — useful for confirming query correctness or live-update subscriptions.

| Field | Notes |
|---|---|
| `entity` | `"events"` |
| `query` | The eventsQuery OData filter |
| `includeMarkets` | The marketsQuery OData filter |
| `locale` | `"en"` |

---

## Key Relationships

```
sports ──< leagues ──< events ──< markets ──< selections
                        │                        │
                   participants[]           participants[]
                   (teams, Home/Away)       (player, PPG stat)
```

- Join `markets.eventId` → `events.id` to group props by game
- Join `selections.marketId` → `markets.id` to get all lines for a player
- `selections.participants[0]` gives the **player name, ID, and season PPG average**
- `selections.trueOdds` is the no-vig decimal probability — useful for implied probability calculations
