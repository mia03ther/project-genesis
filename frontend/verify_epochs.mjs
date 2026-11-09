// Verify the JS epoch + betting port against the Python golden epochs.
//
// Loads tests/golden_epochs.json, re-runs each epoch through
// frontend/engine.js and compares the whole epoch object (digest, winner,
// per-civilization scores and digests) plus the settlement of the golden
// bets, by deep equality. Prints PASS/FAIL per epoch.
//
// Usage: node frontend/verify_epochs.mjs   (from the repository root)

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";
import { runEpoch, settleEpoch } from "./engine.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const GOLDEN_PATH = join(HERE, "..", "tests", "golden_epochs.json");

const golden = JSON.parse(readFileSync(GOLDEN_PATH, "utf-8"));

let passed = 0;
for (const [index, expected] of golden.entries()) {
  const label = expected.label ?? `epoch ${index + 1}`;
  const started = performance.now();
  const epoch = runEpoch({
    seed: expected.epoch.seed,
    days: expected.epoch.days,
    civs: expected.epoch.num_civs,
    residentsPerCiv: expected.epoch.residents_per_civ,
    taxBps: expected.epoch.tax_rate_bps,
    maxOrders: expected.epoch.max_orders_per_day,
  });
  const settlement = settleEpoch(epoch, expected.bets);
  const ms = performance.now() - started;
  const failures = [];
  const check = (name, fn) => {
    try {
      fn();
    } catch (error) {
      failures.push(`${name}: ${String(error.message).split("\n")[0]}`);
    }
  };
  check("epoch", () => assert.deepEqual(epoch, expected.epoch));
  check("settlement", () => assert.deepEqual(settlement, expected.settlement));
  if (failures.length === 0) {
    passed++;
    console.log(
      `PASS ${label} (${ms.toFixed(0)} ms, winner ${epoch.winner_name}, ` +
      `digest ${epoch.digest.slice(0, 16)}, ${settlement.outcome}, pool ${settlement.pool})`,
    );
  } else {
    console.log(`FAIL ${label} (${ms.toFixed(0)} ms)`);
    for (const failure of failures) console.log(`     ${failure}`);
    if (epoch.digest !== expected.epoch.digest) {
      console.log(`     digest got      ${epoch.digest}`);
      console.log(`     digest expected ${expected.epoch.digest}`);
    }
  }
}
console.log(`\n${passed}/${golden.length} golden epochs pass`);
process.exit(passed === golden.length ? 0 : 1);
