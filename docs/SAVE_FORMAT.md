# Save format: `genesis.world`, schema version 1

A save file is a single SQLite 3 database holding exactly one world. It is
written by `genesis.persistence.save_world` and read by `load_world`.

- **Atomic.** A save rewrites the whole snapshot inside one transaction, so a
  file is either the old world or the new one, never a mix.
- **Self-identifying.** The `meta` table names the format and schema version.
  GENESIS refuses to read, overwrite or reset a file that is not a
  `genesis.world` save of a schema version it supports, so a mistyped `--db`
  path cannot destroy an unrelated database.
- **Verified on load.** Loading re-checks the state invariants (non-negative
  holdings, conserved money and resources); a tampered or corrupted file raises
  `SaveFormatError` instead of being simulated further. `genesis verify`
  additionally replays the whole event log.
- **Constrained.** `CHECK` constraints reject negative cash, inventories and
  prices at the database level as well.

All money is stored as integer cents and all quantities as integer units.
JSON columns are UTF-8 text with sorted keys.

## Tables

### `meta`

| key | value |
| --- | --- |
| `format` | always `genesis.world` |
| `schema_version` | `1` |
| `genesis_version` | version of GENESIS that wrote the file, e.g. `0.1.0` |
| `seed` | world seed (integer) |
| `day` | last simulated day (`0` for a new world) |
| `money_supply` | total cash in existence, in cents |
| `config` | the `SimulationConfig` as a JSON object |

### `residents`

| column | type | notes |
| --- | --- | --- |
| `id` | INTEGER PK | 1..N |
| `name` | TEXT | |
| `occupation` | TEXT | `farmer`, `woodcutter` or `miner` |
| `policy` | TEXT | key of the agent that decides for this resident, e.g. `rule_based` |
| `cash` | INTEGER | cents, `>= 0` |
| `health` | INTEGER | `0..100` |
| `alive` | INTEGER | `0` or `1` |
| `last_occupation_change` | INTEGER NULL | day of the last change, `NULL` if never |
| `died_on` | INTEGER NULL | day of death |

### `inventories` and `skills`

| table | columns |
| --- | --- |
| `inventories` | `resident_id`, `resource` (`food`/`wood`/`stone`), `quantity >= 0`; PK (`resident_id`, `resource`) |
| `skills` | `resident_id`, `occupation`, `skill_pct > 0` (percent of base output); PK (`resident_id`, `occupation`) |

### `market`

One row per resource: `resource` (PK), `price` (current reference price in
cents, `> 0`) and `demand`, `supply`, `volume`: units bid, offered and traded in
the latest auction.

### `ledger`

One row per resource: `initial` (units handed out at creation), `produced` and
`consumed` (cumulative). The conservation invariant is
`sum(inventories.quantity) == initial + produced - consumed`.

### `events`

The append-only event log, complete enough to reconstruct every balance.

| column | type | notes |
| --- | --- | --- |
| `seq` | INTEGER PK | 1, 2, 3, ... without gaps |
| `day` | INTEGER | day the event happened (`0` = creation) |
| `kind` | TEXT | see below |
| `resident_id` | INTEGER NULL | subject; the **buyer** of a trade |
| `counterparty_id` | INTEGER NULL | the **seller** of a trade |
| `data` | TEXT | JSON object, fields per kind below |

| kind | data fields |
| --- | --- |
| `world_created` | `seed`, `residents`, `money_supply`, `prices` |
| `resident_created` | `name`, `occupation`, `skills`, `cash`, `inventory`, `policy` (the genesis allocation) |
| `agent_error` | `error` (the agent raised or returned something that is not a `Decision`) |
| `action_rejected` | `action` (`activity` or `change_occupation`), `reason`, `value` |
| `occupation_changed` | `previous`, `occupation` |
| `production` | `resource`, `quantity`, `occupation` |
| `order_rejected` | `reason`, `order` (what was submitted) |
| `trade` | `resource`, `quantity`, `price`, `value` (= quantity x price) |
| `market_cleared` | `resource`, `previous_price`, `price`, `clearing_price` (NULL if no trade), `demand`, `supply`, `volume`, `value`, `trades`, `best_bid`, `best_ask` |
| `consumption` | `consumed`, `unmet` (per resource), `health_before`, `health_after`, `rested` |
| `resident_died` | `cause`, `estate_cash`, `estate_inventory` |

Order rejection reasons: `malformed_order`, `invalid_quantity`,
`invalid_price`, `self_cross`, `insufficient_funds`, `insufficient_inventory`,
`too_many_orders`. Action rejection reasons: `invalid_activity`,
`invalid_occupation`, `already_in_occupation`, `occupation_cooldown`.

### `daily_stats`

One row per simulated day: `day` (PK) and `data`, the `DailyStats` record as a
JSON object: `population`, `deaths`, `working`, `resting`, `occupations`,
`prices`, `production`, `consumption`, `unmet_needs`, `demand`, `supply`,
`trade_volume`, `trade_value`, `trade_count`, `rejected_orders`, `holdings`,
`money_supply`, `mean_health`, `total_wealth`, `gini`.

## Querying a save directly

```sql
-- Price history of food
SELECT day, json_extract(data, '$.prices.food') AS food_price FROM daily_stats ORDER BY day;

-- Every trade of resident 3, as buyer or seller
SELECT day, kind, resident_id AS buyer, counterparty_id AS seller, data
FROM events WHERE kind = 'trade' AND 3 IN (resident_id, counterparty_id);

-- Why were orders rejected?
SELECT json_extract(data, '$.reason') AS reason, COUNT(*) FROM events
WHERE kind = 'order_rejected' GROUP BY reason;
```

## Versioning policy

`schema_version` changes whenever the layout or meaning of stored data
changes. A build reads exactly the schema versions it knows and refuses others
with a clear error rather than guessing. When a future version changes the
schema, it will ship an explicit, tested migration from every earlier version;
v0.1 knows only version 1, so there are no migrations yet.
