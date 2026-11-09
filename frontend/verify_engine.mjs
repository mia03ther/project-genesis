// Verify the JS engine port against the Python golden worlds.
//
// Loads tests/golden_worlds.json, runs each world through frontend/engine.js
// and compares digest (full 64-hex), config, policy, trajectory, final and
// residents by deep equality. Prints PASS/FAIL per world plus timing.
//
// Usage: node frontend/verify_engine.mjs   (from the repository root)

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";
import { runWorld } from "./engine.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const GOLDEN_PATH = join(HERE, "..", "tests", "golden_worlds.json");

const golden = JSON.parse(readFileSync(GOLDEN_PATH, "utf-8"));

let passed = 0;
for (const [index, expected] of golden.entries()) {
  const label = expected.label ?? `world ${index + 1}`;
  const started = performance.now();
  const got = runWorld({
    seed: expected.seed,
    days: expected.days,
    residents: expected.config.num_residents,
    taxBps: expected.policy.tax_rate_bps,
    maxOrders: expected.policy.max_orders_per_day,
  });
  const ms = performance.now() - started;
  const failures = [];
  const check = (name, fn) => {
    try {
      fn();
    } catch (error) {
      failures.push(`${name}: ${String(error.message).split("\n")[0]}`);
    }
  };
  check("digest", () => assert.equal(got.digest, expected.digest));
  check("config", () => assert.deepEqual(got.config, expected.config));
  check("policy", () => assert.deepEqual(got.policy, expected.policy));
  check("seed", () => assert.equal(got.seed, expected.seed));
  check("days", () => assert.equal(got.days, expected.days));
  check("invariants", () => assert.equal(got.invariants, expected.invariants));
  check("trajectory", () => assert.deepEqual(got.trajectory, expected.trajectory));
  check("final", () => assert.deepEqual(got.final, expected.final));
  check("residents", () => assert.deepEqual(got.residents, expected.residents));
  if (failures.length === 0) {
    passed++;
    console.log(`PASS ${label} (${ms.toFixed(0)} ms, digest ${got.digest.slice(0, 16)})`);
  } else {
    console.log(`FAIL ${label} (${ms.toFixed(0)} ms)`);
    for (const failure of failures) console.log(`     ${failure}`);
    if (got.digest !== expected.digest) {
      console.log(`     digest got      ${got.digest}`);
      console.log(`     digest expected ${expected.digest}`);
    }
  }
}
console.log(`\n${passed}/${golden.length} golden worlds pass`);
process.exit(passed === golden.length ? 0 : 1);
