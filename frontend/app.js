/* GENESIS frontend v6 — canonical-epoch betting game + interactive playground, live in the browser.
 *
 * First screen is the GAME ("文明 3 分钟兴衰 —— 押注幸存者"): four
 * civilisations (Aurora, Boreas, Cinder, Dune) race in parallel for 60
 * sim-days (1x = 3s/day = 3 min), play-money parimutuel betting through
 * the canonical engine API only (docs/EPOCH_BETTING.md): runEpoch,
 * deriveWinner, survivalScore, placeBet, settleEpoch. Settlement is
 * verified end-to-end in the browser; the epoch digest is cross-checked
 * against a direct runEpoch() call and the panel says whether they agree.
 * The simulation runs HERE, in the browser, via frontend/engine.js — the
 * dependency-free ES-module port of the Python engine, verified 10/10
 * against the golden worlds (node frontend/verify_engine.mjs). No fetch,
 * no XHR, no server, no keys: open with `python -m http.server` and every
 * number below is computed live. Opened via file:// the module import is
 * blocked by the browser, so the page falls back to the embedded seed-42
 * snapshot in data.js and says so honestly instead of faking live numbers.
 * The game is disabled in file:// mode (it needs the live engine) and says so.
 *
 * Units: engine.js speaks integer cents (x100); the page displays credits,
 * so every money field is divided by 100 exactly once, in fromEngine().
 * Seed-42 defaults (live): 3,867 trades, 3,890 units, 12,350.97 credits,
 * Gini 0.057 -> 0.308, health 100.0, richest Ulla 428.66, poorest Mateo
 * 46.89, mean 180.64, prices 2.29/3.24/4.14, farmer 5 / woodcutter 7 /
 * miner 8, 7,649 events. Tax 10% on seed 42: Gini 0.054, richest 210.44,
 * poorest 153.29, 3,934 trades. Orders 2: 98 trades, 0 alive.
 */
"use strict";

/* Live-chain facts: the single source of truth is frontend/chain.json,
 * loaded at boot (fetch). Nothing in this file hardcodes a contract
 * address, tx hash, RPC URL or explorer URL. In file:// mode fetch fails
 * and Chain stays null: chain-dependent panels say so honestly instead of
 * showing numbers from a stale copy. */
let Chain = null;
const chainExplorer = () => (Chain && Chain.chain.explorer) || "";
const chainContract = () => (Chain && Chain.contract.address) || "";
const chainAnchorTx = () => (Chain && Chain.anchor.tx) || "";
const chainAnchorDigest = () => (Chain && Chain.anchor.digest) || "";
const chainDeployTx = () => (Chain && Chain.contract.deploy_tx) || "";
const chainCastCmd = () => (Chain && Chain.real_testnet_commands.read_anchor) || "";
async function loadChain() {
  try {
    const res = await fetch("chain.json");
    if (!res.ok) throw new Error(`chain.json: HTTP ${res.status}`);
    Chain = await res.json();
  } catch (e) { Chain = null; }
  renderChainFacts();
}

const OCC_COLORS = { farmer: "#e8b34b", woodcutter: "#6ee7a0", miner: "#94a3b8" };
const OCC_NAMES = { farmer: "农民 farmer", woodcutter: "伐木工 woodcutter", miner: "矿工 miner" };
const RES_META = {
  food: { icon: "粮", name: "食物", en: "FOOD" },
  wood: { icon: "木", name: "木材", en: "WOOD" },
  stone: { icon: "石", name: "石头", en: "STONE" },
};
const DEFAULT_PARAMS = { seed: 42, days: 100, residents: 20, taxPct: 0, maxOrders: 10 };

let Engine = null;          // engine.js module namespace, or null on file://
let current = null;         // normalized current playground run
let currentParams = { ...DEFAULT_PARAMS };
let baselineGini = null;    // tax-0 gini for the current params (tax callout)
let baselineRich = null, baselinePoor = null;
let savedA = null, savedB = null;
let showAllResidents = false;
let runSeq = 0;

const $ = (id) => document.getElementById(id);
const fmt = (n) => Number(n).toLocaleString("en-US");
const money = (n) => fmt(Number(n).toFixed(2));
const g3 = (n) => Number(n).toFixed(3);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const isAnchored = (digest) => !!Chain && digest === chainAnchorDigest();

/* ---------- normalization: engine cents -> display credits ---------- */
function fromEngine(r, p) {
  const f = r.final, w = f.wealth;
  const div = (v) => v / 100;
  return {
    source: "live",
    seed: r.seed, days: r.days,
    taxBps: p.taxPct * 100, taxPct: p.taxPct, maxOrders: p.maxOrders,
    digest: r.digest,
    trajectory: r.trajectory.map((t) => ({
      day: t.day, population: t.population, deaths: t.deaths || 0,
      prices: { food: div(t.prices.food), wood: div(t.prices.wood), stone: div(t.prices.stone) },
      trades: t.trades, units: t.units, value: div(t.value),
      health: t.health, gini: t.gini,
    })),
    final: {
      day: f.day,
      population: f.population,
      occupations: f.occupations,
      prices: { food: div(f.prices.food), wood: div(f.prices.wood), stone: div(f.prices.stone) },
      holdings: f.holdings.total,
      produced: f.produced, consumed: f.consumed,
      moneySupply: div(f.money_supply),
      trades: { trades: f.trades.trades, units: f.trades.units, value: div(f.trades.value) },
      meanHealth: f.mean_health,
      wealth: {
        mean: div(w.mean), median: div(w.median),
        min: div(w.minimum), max: div(w.maximum), gini: w.gini,
        richest10: w.top_10_share * 100, poorest50: w.bottom_50_share * 100,
      },
      events: f.events,
    },
    residents: r.residents.map((x) => ({
      id: x.id, name: x.name, occupation: x.occupation, health: x.health,
      cash: div(x.cash), inventory: { ...x.inventory }, wealth: div(x.wealth),
    })),
  };
}

/* Embedded seed-42 snapshot (data.js) — already in credits. */
function fromEmbedded(d) {
  const f = d.final, w = f.wealth;
  return {
    source: "embedded",
    seed: d.meta.seed, days: d.meta.days,
    taxBps: 0, taxPct: 0, maxOrders: 10,
    digest: d.meta.full_digest,
    trajectory: d.trajectory.map((t) => ({
      day: t.day, population: t.population, deaths: 0,
      prices: { ...t.prices }, trades: t.trades, units: t.units, value: t.value,
      health: t.health, gini: t.gini,
    })),
    final: {
      day: f.day,
      population: { alive: f.population, dead: f.dead, total: f.population + f.dead },
      occupations: f.occupations,
      prices: { ...f.prices },
      holdings: f.holdings,
      produced: f.produced, consumed: f.consumed,
      moneySupply: f.money_supply,
      trades: { trades: f.total_trades, units: f.total_units, value: f.total_value },
      meanHealth: f.mean_health,
      wealth: {
        mean: w.mean, median: w.median, min: w.min, max: w.max, gini: w.gini,
        richest10: w.richest_10_pct, poorest50: w.poorest_50_pct,
      },
      events: f.events,
    },
    residents: d.residents.map((x) => ({ ...x, inventory: { ...x.inventory } })),
  };
}

function readParams() {
  return {
    seed: Math.max(0, Math.floor(Number($("in-seed").value) || 0)),
    days: Math.min(365, Math.max(10, Math.floor(Number($("in-days").value) || 100))),
    residents: Math.min(40, Math.max(5, Math.floor(Number($("in-residents").value) || 20))),
    taxPct: Math.min(20, Math.max(0, Math.floor(Number($("in-tax").value) || 0))),
    maxOrders: Math.min(10, Math.max(0, Math.floor(Number($("in-orders").value) || 0))),
  };
}
const sameParams = (a, b) =>
  a.seed === b.seed && a.days === b.days && a.residents === b.residents &&
  a.taxPct === b.taxPct && a.maxOrders === b.maxOrders;
const isDefaultParams = (p) => sameParams(p, DEFAULT_PARAMS);

function runWorldSync(p) {
  if (!Engine) {
    if (isDefaultParams(p) && typeof EMBEDDED_DATA !== "undefined" && EMBEDDED_DATA) return fromEmbedded(EMBEDDED_DATA);
    throw new Error("need-server");
  }
  const t0 = performance.now();
  const raw = Engine.runWorld({
    seed: p.seed, days: p.days, residents: p.residents,
    taxBps: p.taxPct * 100, maxOrders: p.maxOrders,
  });
  const run = fromEngine(raw, p);
  run.ms = performance.now() - t0;
  return run;
}

/* ---------- clipboard ---------- */
function copyText(text, btn, doneLabel) {
  const done = () => {
    if (!btn) return;
    const old = btn.textContent;
    btn.textContent = doneLabel || "已复制 ✓";
    setTimeout(() => { btn.textContent = old; }, 1600);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else fallbackCopy(text, done);
}
function fallbackCopy(text, done) {
  const ta = document.createElement("textarea");
  ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select();
  try { document.execCommand("copy"); } catch (e) { /* ignore */ }
  document.body.removeChild(ta); done();
}

/* ================= BETTING GAME — wired ONLY to frontend/engine.js =================
 * Canonical API (docs/EPOCH_BETTING.md; engine.js + globalThis.GenesisEngine):
 *   Engine.runEpoch({seed, days, civs, residentsPerCiv, taxBps, maxOrders})
 *   Engine.deriveWinner(scores /* [{civ, score}] *\/, epochDigestHex) -> winning civ id
 *   Engine.survivalScore(alive, wealthCents, totalHealth) -> integer score
 *   Engine.placeBet(bets, {player, civ, amount, epochId, validCivs}) -> new bets array
 *   Engine.settleEpoch(epoch, bets) -> {outcome, pool, winner_pool, loser_pool,
 *     house_fee_cents: 0, rollover_cents: 0, payouts: [{player, civ, stake, payout, profit}]}
 *   Engine.civSeed(epochSeed, civIndex), Engine.epochIdFor(...),
 *   Engine.epochDigest(payload), Engine.PLAY_MONEY_LABEL, Engine.CIV_NAMES
 * Amounts are INTEGER CENTS everywhere in logic; divide by 100 exactly once
 * for display (credits = cents / 100). Balance starts at 1000 play credits.
 *
 * Live race: the 4 worlds are stepped one day at a time with the engine's
 * own createWorld + Simulation (the same calls runEpoch makes internally),
 * so the lanes show the real simulation, not a replay. At the final day the
 * epoch result is built in runEpoch's exact shape and its digest recomputed
 * with epochDigest + deriveWinner — then runEpoch() itself is called once
 * as a cross-check and the settlement panel reports whether the two digests
 * agree. Settlement itself always goes through settleEpoch(). No house base
 * pool, no invented bets: the pool is exactly the stakes. Nobody on the
 * winner -> full refund (outcome refunded_no_winner_bets); zero bets ->
 * outcome no_bets. Score: alive * 1,000,000 + wealth_cents + total_health
 * * 100 (survivalScore); ties break by smallest SHA-256 tiebreak hash.
 */
const GAME_PLAYER = "you";
const START_BALANCE_CENTS = 100000; // 1000 play credits
const MIN_BET_CENTS = 1000; // 10 play credits
const CIV_COLORS = ["#836ef9", "#6ee7f9", "#fb923c", "#e8b34b"]; // Aurora, Boreas, Cinder, Dune
const MS_PER_DAY = { 1: 3000, 2: 1500, 6: 500 }; // 1x: 60 days * 3s = 180s = 3 minutes
const EPOCH_CIVS = 4;
const EPOCH_RESIDENTS = 5;
const EPOCH_TAX_BPS = 0;
const EPOCH_MAX_ORDERS = 10;
let epoch = null; // {seed, days, epochId, worlds, day, phase, bets, live, result, settlement}
let epochNo = 1;
let balanceCents = START_BALANCE_CENTS;
let selectedCiv = null;
let speed = 1;
let tickTimer = null;
let epochPaused = false;
const board = {}; // civId -> { wins, played, bestAlive, bestScore }
const player = { stakedCents: 0, returnedCents: 0, epochs: 0 };

const fmtC = (cents) =>
  (cents / 100).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
const fmtOdds = (n) => n.toFixed(2);
const fmtTimer = (secs) => `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(Math.floor(secs % 60)).padStart(2, "0")}`;
const playMoneyLabel = () => (Engine ? Engine.PLAY_MONEY_LABEL : "演示积分 · 不是真钱");

function loadBalance() {
  try {
    const raw = window.localStorage.getItem("genesis-game-balance-cents-v2");
    if (raw === null) return; // first visit: keep START_BALANCE_CENTS
    const v = Number(raw);
    if (Number.isInteger(v) && v >= 0) balanceCents = v;
  } catch (e) { /* private mode etc.: session-only balance */ }
}
function saveBalance() {
  try { window.localStorage.setItem("genesis-game-balance-cents-v2", String(balanceCents)); } catch (e) { /* ignore */ }
}

/* Live stats read straight off the world object, exactly the way runEpoch
 * reads them from playSummary (living residents only; wealth in cents). */
function liveStats(world) {
  const livingList = world.residents.filter((r) => r.alive);
  const alive = livingList.length;
  let wealth = 0, health = 0;
  for (const r of livingList) {
    let w = r.cash;
    for (const res of ["food", "wood", "stone"]) w += r.inventory[res] * world.market[res].price;
    wealth += w;
    health += r.health;
  }
  return { alive, wealth, health, score: Engine.survivalScore(alive, wealth, health) };
}

function feedAdd(text, kind) {
  const feed = $("game-feed");
  if (!feed) return;
  const li = document.createElement("li");
  if (kind) li.className = "feed-" + kind;
  li.innerHTML = `<span class="feed-day">Day ${epoch ? epoch.day : 0}</span> ${text}`;
  feed.appendChild(li);
  feed.scrollTop = feed.scrollHeight;
}

function setLifecycle(step) {
  const order = ["proposed", "voted", "running", "finalized"];
  const idx = order.indexOf(step);
  document.querySelectorAll("#game-lifecycle li").forEach((li) => {
    const i = order.indexOf(li.dataset.step);
    li.classList.toggle("done", i < idx || (step === "finalized" && i <= idx));
    li.classList.toggle("now", li.dataset.step === step && step !== "finalized");
  });
}

function readEpochParams() {
  const seed = Math.max(0, Math.min(Engine.EPOCH_MAX_SEED || 1e9, Math.floor(Number($("game-seed").value) || 42)));
  const days = Math.max(Engine.EPOCH_MIN_DAYS, Math.min(Engine.EPOCH_MAX_DAYS, Math.floor(Number($("game-days").value) || Engine.EPOCH_DEFAULT_DAYS)));
  return { seed, days };
}

function renderGameStatus() {
  $("game-balance").textContent = fmtC(balanceCents);
  $("game-epoch-no").textContent = epochNo;
  const msPerDay = MS_PER_DAY[speed];
  const days = epoch ? epoch.days : (Engine ? Engine.EPOCH_DEFAULT_DAYS : 60);
  const remain = epoch ? (epoch.days - epoch.day) * msPerDay / 1000 : days * msPerDay / 1000;
  $("game-timer").textContent = fmtTimer(Math.max(0, remain));
  $("game-day").textContent = `Day ${epoch ? epoch.day : 0} / ${days}`;
  $("game-day-bar").style.width = `${epoch ? (epoch.day / epoch.days) * 100 : 0}%`;
}

function renderLanes() {
  const wrap = $("game-lanes");
  wrap.innerHTML = Engine.CIV_NAMES.map((name, i) => `
    <article class="lane" data-civ="${i}" style="--civ:${CIV_COLORS[i]}">
      <div class="lane-head">
        <span class="lane-name">${name}</span>
        <span class="lane-rank" id="lane-rank-${i}"></span>
      </div>
      <div class="lane-tag">种子 ${Engine.civSeed(epoch.seed, i)} · 5 位居民</div>
      <div class="lane-race"><div class="lane-streak"></div><div class="lane-fill" id="lane-fill-${i}" style="width:0%"></div></div>
      <div class="lane-stats">
        <div><span>存活</span><b id="lane-alive-${i}">5</b></div>
        <div><span>总健康</span><b id="lane-health-${i}">500</b></div>
        <div><span>总财富</span><b id="lane-wealth-${i}">—</b></div>
        <div><span>得分</span><b id="lane-score-${i}">—</b></div>
        <div><span>赔率</span><b id="lane-odds-${i}">—</b></div>
      </div>
      <button class="btn btn-ghost btn-sm lane-bet" data-civ="${i}">押这个文明</button>
    </article>`).join("");
  wrap.querySelectorAll(".lane").forEach((el) => {
    el.addEventListener("click", (e) => {
      if (e.target.classList.contains("lane-bet")) return;
      selectCiv(Number(el.dataset.civ));
    });
  });
  wrap.querySelectorAll(".lane-bet").forEach((btn) => {
    btn.addEventListener("click", () => selectCiv(Number(btn.dataset.civ)));
  });
}

const poolOnCents = (civ) => epoch.bets.filter((b) => b.civ === civ).reduce((s, b) => s + b.amount, 0);
const poolTotalCents = () => epoch.bets.reduce((s, b) => s + b.amount, 0);

function updateLanes() {
  if (!epoch) return;
  const ranked = [...epoch.live].map((s, i) => ({ i, score: s.score })).sort((a, b) => b.score - a.score);
  const top = ranked.length ? ranked[0].score : 1;
  const total = poolTotalCents();
  for (let i = 0; i < EPOCH_CIVS; i++) {
    const s = epoch.live[i];
    const aliveEl = $(`lane-alive-${i}`);
    if (!aliveEl) continue;
    aliveEl.textContent = `${s.alive} / 5`;
    $(`lane-health-${i}`).textContent = s.health;
    $(`lane-wealth-${i}`).textContent = fmtC(s.wealth);
    $(`lane-score-${i}`).textContent = fmt(s.score);
    const on = poolOnCents(i);
    $(`lane-odds-${i}`).textContent = total > 0 && on > 0 ? fmtOdds(total / on) : "—";
    $(`lane-fill-${i}`).style.width = `${Math.max(2, (s.score / top) * 100)}%`;
    const rank = ranked.findIndex((r) => r.i === i);
    $(`lane-rank-${i}`).textContent = rank === 0 ? "★ 领先" : `#${rank + 1}`;
    const lane = document.querySelector(`.lane[data-civ="${i}"]`);
    lane.classList.toggle("dead", s.alive === 0);
    lane.classList.toggle("leader", rank === 0 && epoch.phase === "running");
    lane.classList.toggle("selected", selectedCiv === i);
  }
  $("game-pool").textContent =
    `底池 = 全部投注之和：${fmtC(total)}（${epoch.bets.length} 笔）· 庄家抽成 0 · 赢家按投注比例分走整个总池；没人押中胜者则全额退款。`;
}

function renderBets() {
  const ul = $("game-bets");
  if (!epoch || !epoch.bets.length) {
    ul.innerHTML = `<li class="dim">还没下注 —— 封盘前都可以下注、撤注。</li>`;
  } else {
    ul.innerHTML = epoch.bets.map((b, idx) => {
      const locked = epoch.phase !== "betting";
      return `<li>${esc(Engine.CIV_NAMES[b.civ])} · ${fmtC(b.amount)} 积分` +
        (locked ? "" : ` <button class="btn btn-ghost btn-sm bet-cancel" data-idx="${idx}">撤注</button>`) + `</li>`;
    }).join("");
    ul.querySelectorAll(".bet-cancel").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.dataset.idx);
        const bet = epoch.bets[idx];
        if (!bet) return;
        epoch.bets = epoch.bets.filter((_, j) => j !== idx);
        balanceCents += bet.amount;
        saveBalance();
        renderBets();
        renderGameStatus();
        updatePreview();
      });
    });
  }
  updateLanes();
}

function betAmountCents() {
  // Amount input is in play credits; the engine takes integer cents.
  return Math.floor((Number($("bet-amount").value) || 0) * 100);
}

function updatePreview() {
  const box = $("bet-preview");
  if (!epoch) return;
  if (epoch.phase !== "betting") {
    box.textContent = epoch.phase === "running" ? "已封盘：本局正在进行，下一局再下注。" : "选一个文明和金额，这里会显示：若它赢，你预计拿回多少。";
    return;
  }
  if (selectedCiv === null) { box.textContent = "先点一条赛道选文明，再输金额。"; return; }
  const amount = betAmountCents();
  if (!Number.isInteger(amount) || amount < MIN_BET_CENTS) { box.textContent = `最少下注 ${fmtC(MIN_BET_CENTS)} 积分（${playMoneyLabel()}）。`; return; }
  if (amount > balanceCents) { box.textContent = `余额不足：你有 ${fmtC(balanceCents)}，想下 ${fmtC(amount)}。`; return; }
  const name = Engine.CIV_NAMES[selectedCiv];
  const newTotal = poolTotalCents() + amount;
  const newOn = poolOnCents(selectedCiv) + amount;
  const preview = Math.floor((amount * newTotal) / newOn);
  box.innerHTML = `若 <b>${esc(name)}</b> 赢：下 ${fmtC(amount)}，预计拿回约 <b>${fmtC(preview)}</b>（赔率 ${fmtOdds(newTotal / newOn)}，净赚约 ${fmtC(preview - amount)}）。结算按 settleEpoch 取整，零头按先后顺序补 1 分。`;
}

function selectCiv(id) {
  if (!epoch || epoch.phase !== "betting") return;
  selectedCiv = id;
  $("bet-civ-name").textContent = Engine.CIV_NAMES[id];
  $("bet-error").textContent = "";
  updateLanes();
  updatePreview();
}

function renderLeaderboard() {
  $("leaderboard-body").innerHTML = Engine.CIV_NAMES.map((name, i) => {
    const b = board[i] || { wins: 0, played: 0, bestAlive: 0, bestScore: 0 };
    return `<tr><td>${name}</td><td class="num">${b.wins}</td><td class="num">${b.played}</td><td class="num">${b.bestAlive} / 5</td><td class="num">${b.bestScore ? fmt(b.bestScore) : "—"}</td></tr>`;
  }).join("");
  const net = player.returnedCents - player.stakedCents;
  $("player-stats").innerHTML = [
    [`${fmtC(balanceCents)}`, "当前余额"],
    [`${fmtC(player.stakedCents)}`, "累计下注"],
    [`${fmtC(player.returnedCents)}`, "累计派彩"],
    [`${net >= 0 ? "+" : ""}${fmtC(net)}`, net >= 0 ? "净赚" : "净亏"],
  ].map(([b, s]) => `<div class="ws"><b>${b}</b><span>${s} · ${player.epochs} 局</span></div>`).join("");
}

function newEpoch() {
  const { seed, days } = readEpochParams();
  const worlds = Engine.CIV_NAMES.map((name, i) => {
    const config = Engine.defaultConfig();
    config.num_residents = EPOCH_RESIDENTS;
    config.max_orders_per_day = EPOCH_MAX_ORDERS;
    const world = Engine.createWorld(config, Engine.civSeed(seed, i));
    return { name, world, sim: new Engine.Simulation(world, EPOCH_TAX_BPS) };
  });
  epoch = {
    seed, days,
    epochId: Engine.epochIdFor(seed, days, EPOCH_CIVS, EPOCH_RESIDENTS, EPOCH_TAX_BPS, EPOCH_MAX_ORDERS),
    worlds, day: 0, phase: "betting", bets: [],
    live: worlds.map((w) => liveStats(w.world)),
    result: null, settlement: null,
  };
  selectedCiv = null;
  epochPaused = false;
  $("settle-panel").hidden = true;
  $("btn-start-epoch").disabled = false;
  $("btn-start-epoch").textContent = "▶ 开始一局";
  $("btn-pause-epoch").disabled = true;
  $("btn-pause-epoch").textContent = "⏸ 暂停";
  $("btn-place-bet").disabled = false;
  $("game-seed").disabled = false;
  $("game-days").disabled = false;
  $("game-days-val").textContent = days;
  $("bet-civ-name").textContent = "点一条赛道选文明";
  $("bet-error").textContent = "";
  $("game-feed").innerHTML = "";
  $("game-phase").textContent = "投注中 · 封盘前可下注";
  $("game-phase-sub").textContent = "Proposed → Voted → Finalized";
  setLifecycle("proposed");
  renderLanes();
  renderBets();
  renderGameStatus();
  updatePreview();
  feedAdd(`第 ${epochNo} 局已提议 Proposed：${Engine.CIV_NAMES.map((n, i) => `${n}（种子 ${Engine.civSeed(seed, i)}）`).join("、")}，每文明 5 位居民，${days} 天。 epoch_id <span class="mono">${epoch.epochId}</span>`, "proposed");
}

function startEpoch() {
  if (!epoch || epoch.phase !== "betting") return;
  epoch.phase = "running";
  $("game-phase").textContent = "进行中 Running";
  $("game-phase-sub").textContent = "已封盘 · 演化中";
  setLifecycle("running");
  document.querySelector("#game-lifecycle li[data-step='voted']").classList.add("done");
  $("btn-start-epoch").disabled = true;
  $("btn-start-epoch").textContent = "进行中…";
  $("btn-pause-epoch").disabled = false;
  $("btn-place-bet").disabled = true;
  $("game-seed").disabled = true;
  $("game-days").disabled = true;
  const staked = poolTotalCents();
  player.stakedCents += staked;
  feedAdd(`已封盘 Voted：总池 ${fmtC(staked)}（${epoch.bets.length} 笔投注，庄家抽成 0）。4 条赛道并行开跑 —— Monad 式并行执行，谁也不等谁。`, "voted");
  updatePreview();
  renderBets();
  tickTimer = setInterval(tickEpoch, MS_PER_DAY[speed]);
}

function tickEpoch() {
  if (!epoch || epoch.phase !== "running" || epochPaused) return;
  epoch.day += 1;
  epoch.worlds.forEach((w, i) => {
    const before = epoch.live[i].alive;
    w.sim.step();
    epoch.live[i] = liveStats(w.world);
    const after = epoch.live[i].alive;
    if (after < before) {
      feedAdd(`${esc(w.name)}有居民死亡：Day ${epoch.day} 存活 ${after} / 5。`, after === 0 ? "dead" : "info");
    }
    if (before > 0 && after === 0) {
      feedAdd(`<b>${esc(w.name)}灭亡</b>：Day ${epoch.day} 最后 1 位居民死亡。`, "dead");
    }
  });
  const third = Math.max(1, Math.floor(epoch.days / 3));
  if (epoch.day === third || epoch.day === third * 2) {
    const ranked = [...epoch.live].map((s, i) => ({ i, score: s.score })).sort((a, b) => b.score - a.score);
    const l = ranked[0];
    feedAdd(`Day ${epoch.day}：领先的是 <b>${esc(Engine.CIV_NAMES[l.i])}</b>（得分 ${fmt(l.score)}）。`, "info");
  }
  renderGameStatus();
  updateLanes();
  if (epoch.day >= epoch.days) finishEpoch();
}

/* Build the epoch result in runEpoch's exact shape, then cross-check it
 * against a direct runEpoch() call (same seeds, same params). */
function buildEpochResult() {
  const civResults = epoch.worlds.map((w, i) => {
    const summary = Engine.playSummary(w.world, EPOCH_TAX_BPS);
    const alive = summary.final.population.alive;
    const wealth = summary.residents.reduce((s, r) => s + r.wealth, 0);
    const health = summary.residents.reduce((s, r) => s + r.health, 0);
    return {
      id: i, name: Engine.CIV_NAMES[i], seed: Engine.civSeed(epoch.seed, i),
      digest: summary.digest, alive, wealth, health,
      score: Engine.survivalScore(alive, wealth, health),
      trades: summary.final.trades.trades,
      units: summary.final.trades.units,
      value: summary.final.trades.value,
    };
  });
  const payload = {
    epoch_id: epoch.epochId, seed: epoch.seed, days: epoch.days,
    num_civs: EPOCH_CIVS, residents_per_civ: EPOCH_RESIDENTS,
    tax_rate_bps: EPOCH_TAX_BPS, max_orders_per_day: EPOCH_MAX_ORDERS,
    civs: civResults,
  };
  const digest = Engine.epochDigest(payload);
  const winner = Engine.deriveWinner(civResults.map((c) => ({ civ: c.id, score: c.score })), digest);
  return {
    ...payload, currency: Engine.PLAY_MONEY_CURRENCY, play_money_note: Engine.PLAY_MONEY_LABEL,
    digest, winner, winner_name: Engine.CIV_NAMES[winner],
  };
}

function finishEpoch() {
  clearInterval(tickTimer);
  tickTimer = null;
  const result = buildEpochResult();
  epoch.result = result;
  const cross = Engine.runEpoch({
    seed: epoch.seed, days: epoch.days, civs: EPOCH_CIVS,
    residentsPerCiv: EPOCH_RESIDENTS, taxBps: EPOCH_TAX_BPS, maxOrders: EPOCH_MAX_ORDERS,
  });
  const crossOk = cross.digest === result.digest && cross.winner === result.winner;
  const settlement = Engine.settleEpoch(result, epoch.bets);
  epoch.settlement = settlement;
  const paid = settlement.payouts.reduce((s, p) => s + p.payout, 0);
  balanceCents += paid;
  player.returnedCents += paid;
  player.epochs += 1;
  saveBalance();
  $("game-phase").textContent = "已敲定 Finalized";
  $("game-phase-sub").textContent = "摘要已生成 · 可验证";
  setLifecycle("finalized");
  $("btn-pause-epoch").disabled = true;
  for (const r of result.civs) {
    const b = board[r.id] || (board[r.id] = { wins: 0, played: 0, bestAlive: 0, bestScore: 0 });
    b.played += 1;
    if (r.id === result.winner) b.wins += 1;
    b.bestAlive = Math.max(b.bestAlive, r.alive);
    b.bestScore = Math.max(b.bestScore, r.score);
  }
  renderLeaderboard();
  renderGameStatus();
  updateLanes();
  /* settlement panel */
  $("settle-panel").hidden = false;
  $("settle-epoch-label").textContent = `第 ${epochNo} 局 · ${epoch.days} 天 · ${result.epoch_id}`;
  $("settle-winner").textContent = `🏆 胜者：${result.winner_name}`;
  const w = result.civs[result.winner];
  const outcomeText = {
    settled: `总池 ${fmtC(settlement.pool)}，赢家分走全部（庄家抽成 0）。`,
    no_bets: "本局无人下注，总池为 0。",
    refunded_no_winner_bets: `没人押中胜者：全部 ${fmtC(settlement.pool)} 投注已全额退回，什么都没滚存。`,
  }[settlement.outcome];
  $("settle-summary").textContent =
    `${result.winner_name}以得分 ${fmt(w.score)} 胜出（存活 ${w.alive} / 5 · 总健康 ${w.health} · 总财富 ${fmtC(w.wealth)}）。${outcomeText}`;
  $("settle-check").textContent = crossOk
    ? "✓ 校验一致：本局摘要与 runEpoch() 现场复算一字不差（同样的种子和规则，换一台机器重跑也一样）。"
    : "✗ 校验不一致：本局摘要与 runEpoch() 复算结果不同 —— 这不应该发生，请把 epoch_id 发给开发者。";
  $("settle-check").className = "settle-check " + (crossOk ? "ok" : "bad");
  const ranked = [...result.civs].sort((a, b) => b.score - a.score);
  $("settle-rows").innerHTML = ranked.map((r, i) =>
    `<tr class="${i === 0 ? "top3" : ""}"><td>${i + 1}</td><td>${esc(r.name)}</td><td class="num">${r.alive} / 5</td>` +
    `<td class="num">${r.health}</td><td class="num">${fmtC(r.wealth)}</td><td class="num">${fmt(r.score)}</td>` +
    `<td class="num">${fmt(r.trades)}</td><td class="num mono">${r.digest.slice(0, 12)}…</td></tr>`).join("");
  if (settlement.payouts.length) {
    $("settle-payouts").innerHTML =
      `<h4>派彩（${settlement.outcome === "refunded_no_winner_bets" ? "全额退款" : "赢家分走整个总池"} ${fmtC(settlement.pool)}，派彩之和 = 总池）</h4>` +
      settlement.payouts.map((p) =>
        `<div class="payout-row"><span>${esc(Engine.CIV_NAMES[p.civ])} · 下注 ${fmtC(p.stake)}</span><b>→ 拿回 ${fmtC(p.payout)}${p.profit >= 0 ? `（+${fmtC(p.profit)}）` : `（${fmtC(p.profit)}）`}</b></div>`).join("") +
      `<div class="payout-row payout-total"><span>合计</span><b>${fmtC(paid)}（余额现为 ${fmtC(balanceCents)}）</b></div>`;
  } else if (epoch.bets.length) {
    $("settle-payouts").innerHTML = `<p>你本局下了 ${fmtC(poolTotalCents())}，但没押中胜者 —— 投注归入底池，下一局再来。</p>`;
  } else {
    $("settle-payouts").innerHTML = `<p>你本局没有下注 —— 只看了场戏。下一局可以先下注再开跑。</p>`;
  }
  $("settle-digest").textContent = result.digest;
  $("settle-note").textContent =
    "本局摘要 = 参数 + 4 个文明的世界摘要与得分，经 SHA-256 算出；同样的种子和规则重跑，摘要一字不差。摘要本身不上链 —— 想锚定它，用下面的「锚定你的世界」，走你自己的钱包。";
  feedAdd(`已敲定 Finalized：胜者 <b>${esc(result.winner_name)}</b>，总池 ${fmtC(settlement.pool)}，派彩 ${fmtC(paid)}。本局摘要 <span class="mono">${result.digest.slice(0, 16)}…</span>${crossOk ? "（与 runEpoch 复算一致 ✓）" : "（与 runEpoch 复算不一致 ✗）"}`, "finalized");
  $("settle-panel").scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "nearest" });
}

function initGame() {
  loadBalance();
  document.querySelectorAll("[data-play-money]").forEach((el) => { el.textContent = playMoneyLabel(); });
  if (!Engine) {
    $("game-note").textContent = "本地文件模式：实时对局需要浏览器加载 engine.js —— 请用 cd frontend && python -m http.server 打开这个页面。下面仍可查看种子 42 的存档世界与链上证明。";
    $("btn-start-epoch").disabled = true;
    $("btn-place-bet").disabled = true;
    $("game-lanes").innerHTML = `<p class="dim" style="padding:20px">实时赛道需要 http.server 模式；当前是本地文件模式，引擎加载不了。</p>`;
    renderGameStatus();
    return;
  }
  newEpoch();
  renderLeaderboard();
  $("btn-start-epoch").addEventListener("click", startEpoch);
  $("btn-next-epoch").addEventListener("click", () => { epochNo += 1; newEpoch(); });
  $("btn-pause-epoch").addEventListener("click", () => {
    if (!epoch || epoch.phase !== "running") return;
    epochPaused = !epochPaused;
    $("btn-pause-epoch").textContent = epochPaused ? "▶ 继续" : "⏸ 暂停";
    if (epochPaused) { clearInterval(tickTimer); tickTimer = null; }
    else tickTimer = setInterval(tickEpoch, MS_PER_DAY[speed]);
  });
  document.querySelectorAll(".speed-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      speed = Number(btn.dataset.speed);
      document.querySelectorAll(".speed-btn").forEach((b) => b.classList.toggle("on", b === btn));
      renderGameStatus();
      if (epoch && epoch.phase === "running" && !epochPaused) {
        clearInterval(tickTimer);
        tickTimer = setInterval(tickEpoch, MS_PER_DAY[speed]);
      }
    });
  });
  $("game-seed").addEventListener("change", () => { if (epoch && epoch.phase === "betting") newEpoch(); });
  $("game-days").addEventListener("input", () => {
    $("game-days-val").textContent = $("game-days").value;
    if (epoch && epoch.phase === "betting") newEpoch();
  });
  $("btn-reset-balance").addEventListener("click", () => {
    balanceCents = START_BALANCE_CENTS;
    player.stakedCents = 0; player.returnedCents = 0; player.epochs = 0;
    saveBalance();
    renderLeaderboard();
    renderGameStatus();
    updatePreview();
    $("game-note").textContent = `余额已重置为 ${fmtC(START_BALANCE_CENTS)} 积分（${playMoneyLabel()}）。`;
  });
  document.querySelectorAll(".amt-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const v = chip.dataset.amt === "all" ? credits(balanceCents) : Number(chip.dataset.amt);
      $("bet-amount").value = v;
      updatePreview();
    });
  });
  $("bet-amount").addEventListener("input", updatePreview);
  $("btn-place-bet").addEventListener("click", () => {
    if (!epoch || epoch.phase !== "betting") return;
    if (selectedCiv === null) { $("bet-error").textContent = "先点一条赛道选文明。"; return; }
    const amount = betAmountCents();
    if (!Number.isInteger(amount) || amount < MIN_BET_CENTS) {
      $("bet-error").textContent = `最少下注 ${fmtC(MIN_BET_CENTS)} 积分。`;
      return;
    }
    if (amount > balanceCents) {
      $("bet-error").textContent = `余额不足：你有 ${fmtC(balanceCents)}，想下 ${fmtC(amount)}。`;
      return;
    }
    let next;
    try {
      next = Engine.placeBet(epoch.bets, {
        player: GAME_PLAYER, civ: selectedCiv, amount,
        epochId: epoch.epochId, validCivs: [0, 1, 2, 3],
      });
    } catch (err) { $("bet-error").textContent = err.message; return; }
    epoch.bets = next;
    balanceCents -= amount;
    saveBalance();
    $("bet-error").textContent = "";
    renderBets();
    renderGameStatus();
    updatePreview();
  });
  $("btn-copy-settle-digest").addEventListener("click", (e) =>
    copyText($("settle-digest").textContent, e.currentTarget));
}

/* ---------- chain facts (frontend/chain.json) ---------- */
function renderChainFacts() {
  const setText = (key, value) => {
    document.querySelectorAll(`[data-chain-text="${key}"]`).forEach((el) => { el.textContent = value; });
  };
  const setHref = (key, value) => {
    document.querySelectorAll(`[data-chain-href="${key}"]`).forEach((el) => { if (value) el.href = value; });
  };
  if (!Chain) {
    document.querySelectorAll("[data-chain-text]").forEach((el) => { el.textContent = "（需用 python -m http.server 打开以加载 chain.json）"; });
    return;
  }
  const ex = Chain.chain.explorer;
  setText("contract-address", Chain.contract.address);
  setHref("contract-address", `${ex}/address/${Chain.contract.address}`);
  setText("contract-short", `${Chain.contract.address.slice(0, 8)}…${Chain.contract.address.slice(-4)}`);
  setHref("contract-short", `${ex}/address/${Chain.contract.address}`);
  setText("anchor-tx", Chain.anchor.tx);
  setHref("anchor-tx", `${ex}/tx/${Chain.anchor.tx}`);
  setText("anchor-tx-short", `${Chain.anchor.tx.slice(0, 10)}…${Chain.anchor.tx.slice(-6)}`);
  setHref("anchor-tx-short", `${ex}/tx/${Chain.anchor.tx}`);
  setText("anchor-digest-short", Chain.anchor.digest.slice(0, 16));
  setText("live-tx", Chain.first_live_transfer.tx);
  setHref("live-tx", `${ex}/tx/${Chain.first_live_transfer.tx}`);
  setText("live-tx-short", `${Chain.first_live_transfer.tx.slice(0, 10)}…${Chain.first_live_transfer.tx.slice(-6)}`);
  setHref("live-tx-short", `${ex}/tx/${Chain.first_live_transfer.tx}`);
  setText("deploy-tx", Chain.contract.deploy_tx);
  setHref("deploy-tx", `${ex}/tx/${Chain.contract.deploy_tx}`);
  setText("live-block", fmt(Chain.first_live_transfer.block));
  setText("live-amount", `${Chain.first_live_transfer.amount_mon} MON`);
  setText("live-fee", `${Chain.first_live_transfer.fee_mon} MON`);
  setText("live-from", Chain.first_live_transfer.from);
  setText("live-to", Chain.first_live_transfer.to);
  setText("cast-cmd", Chain.real_testnet_commands.read_anchor);
  setHref("faucet", Chain.chain.faucet);
  setText("chain-name", `${Chain.chain.name} · Chain ${Chain.chain.id}`);
  setText("seed42-trades", fmt(Chain.seed42_100day.trades));
  setText("seed42-units", fmt(Chain.seed42_100day.units));
  setText("seed42-value", Chain.seed42_100day.value_credits.toFixed(2));
}

/* ---------- playground ---------- */
function syncControlLabels() {
  $("in-days-val").textContent = $("in-days").value;
  $("in-res-val").textContent = $("in-residents").value;
  $("in-tax-val").textContent = $("in-tax").value + "%";
  $("in-orders-val").textContent = $("in-orders").value;
}

async function runPlayground(p, opts = {}) {
  const seq = ++runSeq;
  currentParams = { ...p };
  const btn = $("btn-run");
  btn.disabled = true; btn.textContent = "计算中…";
  $("pg-status").textContent = `正在算：种子 ${p.seed} · ${p.days} 天 · ${p.residents} 人 · 税 ${p.taxPct}% · 订单 ${p.maxOrders}/天 …`;
  $("rerun-result").textContent = "";
  await new Promise((r) => requestAnimationFrame(() => setTimeout(r, 30)));
  try {
    const run = runWorldSync(p);
    if (seq !== runSeq) return; // a newer run superseded this one
    // Tax callout needs a tax-0 baseline for the same world.
    baselineGini = null; baselineRich = null; baselinePoor = null;
    if (p.taxPct > 0 && Engine) {
      try {
        const base = runWorldSync({ ...p, taxPct: 0 });
        baselineGini = base.final.wealth.gini;
        baselineRich = base.residents[0] ? base.residents[0].wealth : null;
        baselinePoor = base.residents.length ? base.residents[base.residents.length - 1].wealth : null;
      } catch (e) { baselineGini = null; baselineRich = null; baselinePoor = null; }
    }
    current = run;
    renderAll(run, p);
  } catch (err) {
    if (err.message === "need-server") {
      $("pg-status").textContent = "本地文件模式：只能显示种子 42 的存档世界。想改参数实时重算，请用 cd frontend && python -m http.server 打开这个页面。";
    } else {
      $("pg-status").textContent = "计算失败：" + err.message;
    }
  }
  btn.disabled = false; btn.textContent = "运行这个世界";
}

async function rerunSame() {
  if (!current) return;
  const btn = $("btn-rerun");
  btn.disabled = true; btn.textContent = "再算中…";
  await new Promise((r) => requestAnimationFrame(() => setTimeout(r, 30)));
  try {
    const again = runWorldSync(currentParams);
    const same = again.digest === current.digest;
    $("rerun-result").innerHTML = same
      ? `摘要不变 ✓ —— 同样的参数重跑一遍，摘要还是 <code class="mono">${again.digest.slice(0, 16)}…</code>。这就是确定性。`
      : `摘要变了 ✗ —— 同样的参数跑出不同摘要，这不应该发生（期望 ${current.digest.slice(0, 16)}…，得到 ${again.digest.slice(0, 16)}…）。`;
    $("rerun-result").className = "pg-rerun " + (same ? "ok" : "bad");
  } catch (err) {
    $("rerun-result").textContent = err.message === "need-server"
      ? "本地文件模式下无法重算，请用 python -m http.server 打开。"
      : "重算失败：" + err.message;
    $("rerun-result").className = "pg-rerun bad";
  }
  btn.disabled = false; btn.textContent = "再算一次";
}

function renderAll(run, p) {
  const f = run.final, w = f.wealth;
  const firstGini = run.trajectory.length ? run.trajectory[0].gini : w.gini;
  const rich = run.residents[0] || null, poor = run.residents.length ? run.residents[run.residents.length - 1] : null;

  $("pg-status").textContent =
    `种子 ${p.seed} · ${p.days} 天 · ${p.residents} 人 · 税 ${p.taxPct}% · 订单 ${p.maxOrders}/天` +
    (run.source === "live" ? ` · 浏览器实时算出，用时 ${Math.round(run.ms || 0)} ms` : " · 本地文件模式：种子 42 存档数据") +
    ` · ${fmt(f.events)} 条事件 · 不变量 OK`;

  /* callouts: cause -> effect */
  const taxBox = $("pg-callout-tax");
  if (p.taxPct > 0) {
    taxBox.hidden = false;
    taxBox.innerHTML = baselineGini !== null
      ? `<b>税率 ${p.taxPct}% → 基尼系数 ${g3(baselineGini)} → ${g3(w.gini)}</b>：同样的世界，只加了税。最富从 ${baselineRich !== null ? money(baselineRich) : "—"} 掉到 ${rich ? money(rich.wealth) : "—"}，最穷从 ${baselinePoor !== null ? money(baselinePoor) : "—"} 涨到 ${poor ? money(poor.wealth) : "—"} —— 改规则，摘要就变，证明也得重新做。`
      : `<b>税率 ${p.taxPct}% → 基尼系数 ${g3(w.gini)}</b>：税把交易里的钱重新分了一遍，差距变小了，摘要也变了。`;
  } else taxBox.hidden = true;
  const deadBox = $("pg-callout-dead");
  if (p.maxOrders <= 2 || f.population.alive === 0) {
    deadBox.hidden = false;
    deadBox.innerHTML = f.population.alive === 0
      ? `<b>市场关闭 → 小镇死亡：</b>订单上限 ${p.maxOrders}/天，${p.days} 天只成交 ${fmt(f.trades.trades)} 笔，居民买不到吃的，${f.population.total} 人全部死亡。没有市场，就没有小镇 —— 但钱还在，货币供给仍是 ${money(f.moneySupply)} credits。`
      : `<b>市场快死了：</b>订单上限只有 ${p.maxOrders}/天，${p.days} 天只成交 ${fmt(f.trades.trades)} 笔，已有 ${f.population.dead} 人死亡，仅剩 ${f.population.alive} 人存活。`;
  } else deadBox.hidden = true;

  /* KPI cards */
  const cards = [
    { num: g3(w.gini), label: "基尼系数 Gini", sub: `第 ${run.trajectory[0]?.day ?? 0} 天 ${g3(firstGini)} → 第 ${f.day} 天 ${g3(w.gini)}` },
    { num: money(w.mean), label: "人均财富 credits", sub: `中位 ${money(w.median)}` },
    { num: rich ? money(rich.wealth) : "—", label: "最富", sub: rich ? `${rich.name} · ${OCC_NAMES[rich.occupation].split(" ")[0]}` : "无人存活" },
    { num: poor ? money(poor.wealth) : "—", label: "最穷", sub: poor ? `${poor.name} · ${OCC_NAMES[poor.occupation].split(" ")[0]}` : "无人存活" },
    { num: f.meanHealth.toFixed(1), label: "平均健康", sub: f.population.alive ? `${f.population.alive} 人存活` : "无人存活" },
    { num: `${f.population.alive}<small> / ${f.population.total}</small>`, label: "存活人口", sub: `${f.population.dead} 人死亡` },
    { num: fmt(f.trades.trades), label: "累计交易", sub: `${fmt(f.trades.units)} 单位 · ${money(f.trades.value)} credits` },
    { num: run.digest.slice(0, 16), label: "世界摘要", sub: `${fmt(f.events)} 条事件 · 完整摘要见下方` },
  ];
  $("kpi-grid").innerHTML = cards
    .map((c) => `<div class="kpi"><div class="kpi-num">${c.num}</div><div class="kpi-label">${c.label}</div><div class="kpi-sub">${c.sub}</div></div>`)
    .join("");

  /* digest + anchor line */
  $("pg-digest-full").textContent = run.digest;
  $("pg-anchor-line").innerHTML = isAnchored(run.digest)
    ? `● 已上链 ✓ —— 这个摘要就是链上锚定的那个世界，<a href="${chainExplorer()}/tx/${chainAnchorTx()}" target="_blank" rel="noopener">锚定交易 ↗</a>`
    : `● 未锚定 —— 这是你的世界，还没上链。改一个参数，摘要就变，证明也得重新做。`;

  drawChart(run);
  $("pg-chart-note").textContent =
    `第 ${run.trajectory[0]?.day ?? 0} 天 ${g3(firstGini)} → 第 ${f.day} 天 ${g3(w.gini)}：` +
    (w.gini > firstGini ? "没有出生、继承和资本，财富差距仍在缓慢拉大。" : "差距没有拉大 —— 看看是不是税率或市场把它压住了。");

  /* day-by-day table */
  $("traj-body").innerHTML = run.trajectory.map((t) =>
    `<tr><td>Day ${t.day}</td><td class="num">${t.trades}</td><td class="num">${t.units}</td>` +
    `<td class="num">${money(t.value)}</td><td class="num">${Number(t.health).toFixed(1)}</td>` +
    `<td class="num">${g3(t.gini)}</td><td class="num">${t.population}</td></tr>`).join("");

  /* resident ranking: top 5 + bottom 5 */
  const row = (r, i) => `<tr class="${i < 3 ? "top3" : ""}"><td>${i + 1}</td><td>${esc(r.name)}</td><td>${OCC_NAMES[r.occupation].split(" ")[0]}</td><td class="num">${money(r.wealth)}</td></tr>`;
  $("rank-top").innerHTML = run.residents.length
    ? run.residents.slice(0, 5).map(row).join("")
    : `<tr><td colspan="4">无人存活 —— 小镇已经死了。</td></tr>`;
  $("rank-bottom").innerHTML = run.residents.length
    ? run.residents.slice(-5).reverse().map((r, i) => row(r, run.residents.length - 5 + i)).join("")
    : `<tr><td colspan="4">无人存活 —— 小镇已经死了。</td></tr>`;

  renderMarket(run);
  renderResidents(run);
  renderAnchorYour(run);
  renderRepro(p);
  initTown(run);
}

function drawChart(run) {
  const canvas = $("gini-chart");
  if (!canvas || !canvas.getContext) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return; // e.g. headless DOM without canvas: skip chart, keep rendering
  const W = canvas.width, H = canvas.height, padL = 44, padR = 34, padT = 18, padB = 30;
  ctx.clearRect(0, 0, W, H);
  const pts = run.trajectory;
  if (!pts.length) return;
  const d0 = pts[0].day, d1 = pts[pts.length - 1].day;
  const maxG = Math.max(0.35, ...pts.map((p) => p.gini)) * 1.1;
  const x = (day) => padL + ((day - d0) / Math.max(1, d1 - d0)) * (W - padL - padR);
  const y = (g) => H - padB - (g / maxG) * (H - padT - padB);
  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.fillStyle = "#6b7280";
  ctx.font = "11px ui-monospace, monospace";
  ctx.textAlign = "right";
  [0, 0.1, 0.2, 0.3].forEach((g) => {
    if (g > maxG) return;
    ctx.beginPath(); ctx.moveTo(padL, y(g)); ctx.lineTo(W - padR, y(g)); ctx.stroke();
    ctx.fillText(g.toFixed(1), padL - 8, y(g) + 4);
  });
  const grad = ctx.createLinearGradient(0, padT, 0, H - padB);
  grad.addColorStop(0, "rgba(131,110,249,0.30)");
  grad.addColorStop(1, "rgba(131,110,249,0.02)");
  ctx.beginPath();
  pts.forEach((p, i) => (i === 0 ? ctx.moveTo(x(p.day), y(p.gini)) : ctx.lineTo(x(p.day), y(p.gini))));
  ctx.lineTo(x(d1), H - padB); ctx.lineTo(x(d0), H - padB); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();
  ctx.beginPath();
  pts.forEach((p, i) => (i === 0 ? ctx.moveTo(x(p.day), y(p.gini)) : ctx.lineTo(x(p.day), y(p.gini))));
  ctx.strokeStyle = "#836ef9"; ctx.lineWidth = 2.5; ctx.stroke();
  pts.forEach((p, i) => {
    const sel = i === pts.length - 1;
    ctx.beginPath(); ctx.arc(x(p.day), y(p.gini), sel ? 6 : 3.5, 0, Math.PI * 2);
    ctx.fillStyle = sel ? "#e8b34b" : "#836ef9"; ctx.fill();
    if (sel) { ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5; ctx.stroke(); }
  });
  ctx.fillStyle = "#6b7280"; ctx.textAlign = "center";
  pts.forEach((p) => ctx.fillText(`D${p.day}`, x(p.day), H - 10));
}

function renderMarket(run) {
  const f = run.final;
  const maxPrice = Math.max(...Object.values(f.prices), 0.01);
  $("market-grid").innerHTML = Object.keys(RES_META).map((res) => {
    const m = RES_META[res];
    const pct = Math.round((f.prices[res] / maxPrice) * 100);
    const barClass = res === "food" ? "bar-food" : res === "wood" ? "bar-wood" : "bar-stone";
    return `<div class="market-row">
      <div class="res-icon">${m.icon}</div>
      <div><h3>${m.name}</h3><div class="res-en">${m.en}</div></div>
      <div class="price">${f.prices[res].toFixed(2)}<small> credits / 单位</small></div>
      <div>
        <div class="bar-track"><div class="bar-fill ${barClass}" style="width:${pct}%"></div></div>
        <div class="res-stats" style="margin-top:10px">
          <div><span>持有</span><b>${fmt(f.holdings[res])}</b></div>
          <div><span>累计生产</span><b>${fmt(f.produced[res])}</b></div>
          <div><span>累计消费</span><b>${fmt(f.consumed[res])}</b></div>
        </div>
      </div>
    </div>`;
  }).join("");
  $("market-sub").textContent = `第 ${f.day} 天的价格（credits / 单位）· 跟着上面的试玩参数一起变`;
  $("market-foot").textContent =
    `${f.day} 天累计：${fmt(f.trades.trades)} 笔交易 · ${fmt(f.trades.units)} 单位 · ${money(f.trades.value)} credits。` +
    `生产：食物 ${fmt(f.produced.food)} / 木材 ${fmt(f.produced.wood)} / 石头 ${fmt(f.produced.stone)}；` +
    `消费：食物 ${fmt(f.consumed.food)} / 木材 ${fmt(f.consumed.wood)} / 石头 ${fmt(f.consumed.stone)}。` +
    `货币供给恒定 ${money(f.moneySupply)} credits —— 没有凭空印钱，也没有钱消失。`;
}

function renderResidents(run) {
  const f = run.final;
  const occ = f.occupations;
  const total = Object.values(occ).reduce((a, b) => a + b, 0);
  let acc = 0;
  const stops = Object.keys(occ).map((k) => {
    const start = total ? (acc / total) * 360 : 0; acc += occ[k];
    const end = total ? (acc / total) * 360 : 0;
    return `${OCC_COLORS[k]} ${start}deg ${end}deg`;
  }).join(", ");
  $("donut").style.background = total ? `conic-gradient(${stops})` : "#222";
  $("donut-total").textContent = total;
  $("occ-legend").innerHTML = Object.keys(occ).map((k) =>
    `<li><span class="swatch" style="background:${OCC_COLORS[k]}"></span>${OCC_NAMES[k]}<b>${occ[k]} 人</b></li>`).join("");
  const w = f.wealth;
  $("wealth-stats").innerHTML = [
    [`${money(w.mean)}`, "平均财富"],
    [`${money(w.median)}`, "中位财富"],
    [`${money(w.min)}`, "最穷"],
    [`${money(w.max)}`, "最富"],
  ].map(([b, s]) => `<div class="ws"><b>${b}</b><span>${s}</span></div>`).join("");
  const rich = run.residents[0], poor = run.residents.length ? run.residents[run.residents.length - 1] : null;
  $("people-sub").textContent = run.residents.length
    ? `第 ${f.day} 天 · 按财富排序 · 财富 = 现金 + 库存按市价折算 · 最富 ${rich.name} ${money(rich.wealth)}，最穷 ${poor.name} ${money(poor.wealth)}`
    : `第 ${f.day} 天 · 无人存活 —— 小镇已经死了。`;
  renderResidentTable(run);
  $("btn-more-residents").textContent = showAllResidents ? "收起" : `展开全部 ${run.residents.length} 人`;
}

function renderResidentTable(run) {
  const rows = showAllResidents ? run.residents : run.residents.slice(0, 8);
  $("resident-table").querySelector("tbody").innerHTML = rows.length ? rows.map((r) => {
    const rank = run.residents.indexOf(r) + 1;
    return `<tr class="${rank <= 3 ? "top3" : ""}">
      <td>${rank}</td><td>${esc(r.name)}</td><td>${OCC_NAMES[r.occupation].split(" ")[0]}</td>
      <td class="num">${r.health}</td><td class="num">${money(r.cash)}</td><td class="num">${money(r.wealth)}</td>
    </tr>`;
  }).join("") : `<tr><td colspan="6">无人存活。</td></tr>`;
}

/* ---------- compare ---------- */
function snapshot(run, label) {
  const f = run.final, w = f.wealth;
  const rich = run.residents[0], poor = run.residents.length ? run.residents[run.residents.length - 1] : null;
  return {
    label,
    gini: g3(w.gini),
    richest: rich ? `${rich.name} ${money(rich.wealth)}` : "—",
    poorest: poor ? `${poor.name} ${money(poor.wealth)}` : "—",
    mean: money(w.mean),
    health: f.meanHealth.toFixed(1),
    alive: `${f.population.alive} / ${f.population.total}`,
    trades: fmt(f.trades.trades),
    digest: run.digest,
  };
}
function renderCompare() {
  const table = $("compare-table");
  if (!savedA || !savedB) { table.hidden = true; return; }
  table.hidden = false;
  $("compare-label-a").textContent = "A · " + savedA.label;
  $("compare-label-b").textContent = "B · " + savedB.label;
  const rows = [
    ["基尼系数", savedA.gini, savedB.gini],
    ["最富", savedA.richest, savedB.richest],
    ["最穷", savedA.poorest, savedB.poorest],
    ["人均财富", savedA.mean, savedB.mean],
    ["平均健康", savedA.health, savedB.health],
    ["存活", savedA.alive, savedB.alive],
    ["交易", savedA.trades, savedB.trades],
  ];
  const sameDigest = savedA.digest === savedB.digest;
  $("compare-body").innerHTML = rows.map(([k, a, b]) =>
    `<tr><td>${k}</td><td class="mono">${a}</td><td class="mono">${b}</td></tr>`).join("") +
    `<tr><td>世界摘要</td><td class="mono">${savedA.digest.slice(0, 24)}…</td><td class="mono">${savedB.digest.slice(0, 24)}…</td></tr>` +
    `<tr><td>摘要相同？</td><td colspan="2"><span class="badge ${sameDigest ? "badge-ok" : "badge-warn"}">${sameDigest ? "相同 · 同一个世界" : "不同 · 两个世界"}</span></td></tr>`;
  $("compare-note").textContent = sameDigest
    ? "两个摘要一字不差 —— 参数相同，世界就相同。"
    : "摘要不同 —— 参数变了，世界就变了，证明也得重新做。";
}
async function presetCompare(kind) {
  if (!Engine) {
    $("compare-note").textContent = "本地文件模式下跑不了对照：请用 python -m http.server 打开。";
    return;
  }
  const base = { ...currentParams };
  const note = $("compare-note");
  note.textContent = "正在跑两组对照…";
  await new Promise((r) => requestAnimationFrame(() => setTimeout(r, 30)));
  try {
    let pa, pb, la, lb;
    if (kind === "seeds") {
      pa = { ...base, seed: 42 }; pb = { ...base, seed: 43 };
      la = `种子 42 · ${base.days} 天`; lb = `种子 43 · ${base.days} 天`;
    } else {
      pa = { ...base, taxPct: 0 }; pb = { ...base, taxPct: 10 };
      la = `税 0% · 种子 ${base.seed}`; lb = `税 10% · 种子 ${base.seed}`;
    }
    savedA = snapshot(runWorldSync(pa), la);
    savedB = snapshot(runWorldSync(pb), lb);
    renderCompare();
  } catch (err) {
    note.textContent = "对照失败：" + err.message;
  }
}

/* ---------- anchor your world ---------- */
function renderAnchorYour(run) {
  const f = run.final;
  $("ay-digest").textContent = run.digest;
  const anchored = isAnchored(run.digest);
  $("ay-badge").innerHTML = anchored
    ? `<span class="badge badge-ok">● 已上链 ✓</span>`
    : `<span class="badge badge-warn">● 未锚定</span>`;
  $("ay-state").innerHTML = anchored
    ? `已上链 ✓ —— 这个摘要就是链上锚定的那个世界。锚定交易 <a class="mono" href="${chainExplorer()}/tx/${chainAnchorTx()}" target="_blank" rel="noopener">${chainAnchorTx().slice(0, 10)}…${chainAnchorTx().slice(-6)} ↗</a>，任何人都能查到。`
    : `未锚定 — 需要一个有测试 MON 的钱包才能上链。这个摘要是你的世界的指纹：换一个参数，它就变了。`;
  $("ay-cmd").textContent =
    `python main.py monad anchor --digest 0x${run.digest} --day ${f.day} ` +
    `--population ${f.population.alive} --trades ${f.trades.trades} --contract ${chainContract()}`;
}

function renderRepro(p) {
  $("py-cmd").textContent =
    `python main.py play --seed ${p.seed} --days ${p.days} --tax-bps ${p.taxPct * 100} --max-orders ${p.maxOrders}`;
}

/* ================= LIVING TOWN (driven by the current run) ================= */
const TOWN_W = 1280, TOWN_H = 720;
let townResidents = [];
let townRun = null;
let townDayIdx = 0;
let townPhase = 0.3;
let townPaused = false;
let townVisible = true;
let townLast = null;
let townDayTimer = 0;
let townStarted = false;

function mulberry(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function initTown(run) {
  const canvas = $("town");
  if (!canvas || !canvas.getContext) return;
  townRun = run;
  townResidents = [];
  townDayIdx = Math.min(townDayIdx, Math.max(0, run.trajectory.length - 1));
  const rnd = mulberry(42);
  const zones = {
    farmer: { work: [0.16, 0.66], home: [0.10, 0.86] },
    woodcutter: { work: [0.86, 0.40], home: [0.72, 0.86] },
    miner: { work: [0.88, 0.62], home: [0.55, 0.88] },
  };
  run.residents.forEach((r) => {
    const z = zones[r.occupation];
    const jx = (rnd() - 0.5) * 0.10, jy = (rnd() - 0.5) * 0.06;
    const kx = (rnd() - 0.5) * 0.08, ky = (rnd() - 0.5) * 0.05;
    townResidents.push({
      name: r.name, occ: r.occupation,
      home: [z.home[0] + jx, z.home[1] + jy],
      work: [z.work[0] + kx, z.work[1] + ky],
      market: [0.5 + (rnd() - 0.5) * 0.16, 0.62 + (rnd() - 0.5) * 0.08],
      phase: rnd() * Math.PI * 2,
      speed: 0.6 + rnd() * 0.7,
    });
  });
  if (!townStarted) {
    townStarted = true;
    const wrap = document.querySelector(".town-wrap");
    if ("IntersectionObserver" in window && wrap) {
      new IntersectionObserver((es) => { townVisible = es[0].isIntersecting; }).observe(wrap);
    }
    requestAnimationFrame(drawTown);
  }
  updateTownHud();
}

function updateTownHud() {
  if (!townRun || !townRun.trajectory.length) return;
  const tp = townRun.trajectory[Math.min(townDayIdx, townRun.trajectory.length - 1)];
  $("town-gini").textContent = g3(tp.gini);
  $("town-trades").textContent = tp.trades;
  $("town-pop").textContent = tp.population;
}

function lerp(a, b, t) { return a + (b - a) * t; }
function smooth(t) { return t * t * (3 - 2 * t); }
function residentPos(r, phase, t) {
  let from, to, u;
  if (phase < 0.3) { from = r.home; to = r.work; u = smooth(phase / 0.3); }
  else if (phase < 0.55) { from = r.work; to = r.work; u = 0; }
  else if (phase < 0.75) { from = r.work; to = r.market; u = smooth((phase - 0.55) / 0.2); }
  else if (phase < 0.9) { from = r.market; to = r.home; u = smooth((phase - 0.75) / 0.15); }
  else { from = r.home; to = r.home; u = 0; }
  const wob = Math.sin(t * r.speed + r.phase) * 0.004;
  return [lerp(from[0], to[0], u) + wob, lerp(from[1], to[1], u) + Math.abs(Math.sin(t * 2 * r.speed + r.phase)) * 0.003];
}

function reducedMotion() {
  return typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function drawTown(now) {
  const canvas = $("town");
  if (!canvas) return;
  if (reducedMotion()) {
    if (townRun && townRun.trajectory.length) drawTownFrame(canvas, 12000, 0.3, townRun.trajectory[townDayIdx]);
    return;
  }
  requestAnimationFrame(drawTown);
  if (document.hidden || !townVisible || townPaused || !townRun || !townRun.trajectory.length) { townLast = now; return; }
  if (townLast === null) townLast = now;
  const dt = Math.min(0.1, (now - townLast) / 1000);
  townLast = now;
  townPhase += dt / 14;
  if (townPhase >= 1) {
    townPhase -= 1;
    townDayTimer += 1;
    if (townDayTimer >= 2) {
      townDayTimer = 0;
      townDayIdx = (townDayIdx + 1) % townRun.trajectory.length;
      updateTownHud();
    }
  }
  drawTownFrame(canvas, now / 1000, townPhase, townRun.trajectory[townDayIdx]);
}

function drawTownFrame(canvas, t, phase, tp) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return; // no canvas backend: skip frame, keep everything else working
  const W = TOWN_W, H = TOWN_H;
  const stops = [
    [0.0, "#2b3a67", "#e8a56b"], [0.25, "#7fb2e5", "#cfe8f5"],
    [0.5, "#3a4a7a", "#e07856"], [0.75, "#070a18", "#0b1030"], [1.0, "#2b3a67", "#e8a56b"],
  ];
  let skyTop = "#0b1030", skyBot = "#070a18";
  for (let i = 0; i < stops.length - 1; i++) {
    const [p0, a0, b0] = stops[i], [p1, a1, b1] = stops[i + 1];
    if (phase >= p0 && phase <= p1) {
      const u = (phase - p0) / (p1 - p0);
      skyTop = mixColor(a0, a1, u); skyBot = mixColor(b0, b1, u);
      break;
    }
  }
  const sky = ctx.createLinearGradient(0, 0, 0, H * 0.55);
  sky.addColorStop(0, skyTop); sky.addColorStop(1, skyBot);
  ctx.fillStyle = sky; ctx.fillRect(0, 0, W, H * 0.56);
  const night = phase > 0.72 || phase < 0.06 ? 1 : phase > 0.55 ? (phase - 0.55) / 0.17 : 0;
  const dayFrac = Math.max(0, 1 - night);
  if (night > 0.1) {
    const rnd = mulberry(7);
    ctx.fillStyle = "#fff";
    for (let i = 0; i < 90; i++) {
      const sx = rnd() * W, sy = rnd() * H * 0.42, sr = rnd() * 1.4 + 0.4;
      ctx.globalAlpha = night * (0.25 + 0.75 * Math.abs(Math.sin(t + i)));
      ctx.beginPath(); ctx.arc(sx, sy, sr, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1;
  }
  const sunA = Math.PI * (1 - phase);
  const sunX = W * 0.5 + Math.cos(sunA) * W * 0.42;
  const sunY = H * 0.52 - Math.sin(sunA) * H * 0.38;
  if (phase < 0.62) {
    ctx.beginPath(); ctx.arc(sunX, sunY, 26, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(232,179,75,0.9)"; ctx.fill();
    ctx.beginPath(); ctx.arc(sunX, sunY, 40, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(232,179,75,0.18)"; ctx.fill();
  } else {
    ctx.beginPath(); ctx.arc(W * 0.82, H * 0.14, 20, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(226,232,240,0.9)"; ctx.fill();
  }
  const gnd = ctx.createLinearGradient(0, H * 0.5, 0, H);
  gnd.addColorStop(0, mixColor("#3f5a3a", "#141a12", night * 0.7));
  gnd.addColorStop(1, mixColor("#2c3d28", "#0c100a", night * 0.7));
  ctx.fillStyle = gnd; ctx.fillRect(0, H * 0.52, W, H * 0.48);
  ctx.save();
  ctx.fillStyle = mixColor("#5a7a3a", "#1c2416", night * 0.7);
  ctx.fillRect(W * 0.03, H * 0.58, W * 0.26, H * 0.22);
  ctx.strokeStyle = mixColor("#8a9a4b", "#2c341f", night * 0.7);
  ctx.lineWidth = 2;
  for (let i = 0; i < 6; i++) {
    const y = H * 0.60 + i * H * 0.033;
    ctx.beginPath(); ctx.moveTo(W * 0.04, y); ctx.lineTo(W * 0.28, y); ctx.stroke();
  }
  ctx.restore();
  for (let i = 0; i < 14; i++) {
    const fx = W * (0.74 + (i % 7) * 0.035), fy = H * (0.34 + Math.floor(i / 7) * 0.07);
    ctx.fillStyle = mixColor("#2f5d33", "#0f1f12", night * 0.7);
    ctx.beginPath(); ctx.moveTo(fx, fy - 22); ctx.lineTo(fx - 13, fy + 10); ctx.lineTo(fx + 13, fy + 10); ctx.closePath(); ctx.fill();
    ctx.fillStyle = mixColor("#4a2f1d", "#1a110a", night * 0.7);
    ctx.fillRect(fx - 2, fy + 10, 4, 8);
  }
  ctx.fillStyle = mixColor("#5b6470", "#232830", night * 0.7);
  ctx.beginPath(); ctx.moveTo(W * 0.78, H * 0.78); ctx.lineTo(W * 0.88, H * 0.50); ctx.lineTo(W * 0.98, H * 0.78); ctx.closePath(); ctx.fill();
  ctx.fillStyle = mixColor("#e8eaf2", "#5a6474", night * 0.7);
  ctx.beginPath(); ctx.moveTo(W * 0.88, H * 0.50); ctx.lineTo(W * 0.85, H * 0.57); ctx.lineTo(W * 0.91, H * 0.57); ctx.closePath(); ctx.fill();
  ctx.fillStyle = "#0a0a0a";
  ctx.beginPath(); ctx.arc(W * 0.88, H * 0.76, 14, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "rgba(232,179,75,0.9)";
  ctx.beginPath(); ctx.arc(W * 0.88, H * 0.76, 3, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = mixColor("#6b5a3e", "#241d12", night * 0.7);
  ctx.beginPath(); ctx.ellipse(W * 0.5, H * 0.66, W * 0.11, H * 0.055, 0, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = "rgba(232,179,75,0.55)"; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.ellipse(W * 0.5, H * 0.66, W * 0.11, H * 0.055, 0, 0, Math.PI * 2); ctx.stroke();
  [[0.42, 0.60], [0.58, 0.60], [0.5, 0.72]].forEach(([fx, fy]) => {
    ctx.fillStyle = mixColor("#8a6a3f", "#332613", night * 0.7);
    ctx.fillRect(W * fx - 16, H * fy - 8, 32, 14);
    ctx.fillStyle = mixColor("#e8b34b", "#7a5c1d", night * 0.7);
    ctx.beginPath(); ctx.moveTo(W * fx - 20, H * fy - 8); ctx.lineTo(W * fx + 20, H * fy - 8); ctx.lineTo(W * fx + 14, H * fy - 18); ctx.lineTo(W * fx - 14, H * fy - 18); ctx.closePath(); ctx.fill();
  });
  /* houses: one per resident slot of the current world (empty when dead) */
  const homes = townResidents.length ? townResidents : [];
  homes.forEach((r) => {
    const hx = r.home[0] * W, hy = r.home[1] * H;
    ctx.fillStyle = mixColor("#7a5c38", "#2c2113", night * 0.7);
    ctx.fillRect(hx - 13, hy - 14, 26, 18);
    ctx.fillStyle = mixColor("#a34d3f", "#3d1d17", night * 0.7);
    ctx.beginPath(); ctx.moveTo(hx - 16, hy - 14); ctx.lineTo(hx, hy - 28); ctx.lineTo(hx + 16, hy - 14); ctx.closePath(); ctx.fill();
    ctx.fillStyle = night > 0.4 ? "rgba(255,205,110,0.95)" : "rgba(20,24,32,0.85)";
    ctx.fillRect(hx - 6, hy - 9, 7, 7);
  });
  if (phase > 0.55 && phase < 0.9) {
    const atMarket = townResidents.filter((r) => {
      const p = residentPos(r, phase, t);
      return Math.abs(p[0] - 0.5) < 0.14 && Math.abs(p[1] - 0.66) < 0.1;
    });
    ctx.strokeStyle = "rgba(232,179,75,0.75)"; ctx.lineWidth = 1.6;
    for (let i = 0; i + 1 < atMarket.length; i += 2) {
      const a = residentPos(atMarket[i], phase, t), b = residentPos(atMarket[i + 1], phase, t);
      const mx = ((a[0] + b[0]) / 2) * W, my = Math.min(a[1], b[1]) * H - 26 - 10 * Math.abs(Math.sin(t * 2 + i));
      ctx.beginPath(); ctx.moveTo(a[0] * W, a[1] * H);
      ctx.quadraticCurveTo(mx, my, b[0] * W, b[1] * H); ctx.stroke();
    }
  }
  townResidents.forEach((r) => {
    const [px, py] = residentPos(r, phase, t);
    ctx.beginPath(); ctx.arc(px * W, py * H, 4.6, 0, Math.PI * 2);
    ctx.fillStyle = OCC_COLORS[r.occ]; ctx.fill();
    ctx.strokeStyle = "rgba(7,8,13,0.8)"; ctx.lineWidth = 1.4; ctx.stroke();
  });
  ctx.font = "600 11px ui-monospace, monospace"; ctx.textAlign = "left";
  ctx.fillStyle = `rgba(232,234,242,${0.35 + 0.4 * dayFrac})`;
  ctx.fillText("田地 · FIELDS", W * 0.04, H * 0.565);
  ctx.fillText("森林 · FOREST", W * 0.74, H * 0.315);
  ctx.fillText("矿山 · MINE", W * 0.845, H * 0.49);
  ctx.fillText("集市 · MARKET", W * 0.44, H * 0.585);
  const label = phase < 0.12 ? "☀ 黎明" : phase < 0.5 ? "☀ 正午" : phase < 0.72 ? "🌇 黄昏" : "🌙 深夜";
  const clock = $("town-clock");
  if (clock) clock.textContent = `${label} · DAY ${tp.day}`;
}

function mixColor(hexA, hexB, u) {
  const pa = [1, 3, 5].map((i) => parseInt(hexA.substr(i, 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(hexB.substr(i, 2), 16));
  const c = pa.map((v, i) => Math.round(v + (pb[i] - v) * Math.min(1, Math.max(0, u))));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

/* ---------- scroll: back-to-top ---------- */
function initScroll() {
  const topBtn = $("top-btn");
  const onScroll = () => {
    const y = window.scrollY || 0;
    if (topBtn) topBtn.classList.toggle("on", y > window.innerHeight * 0.8);
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
  if (topBtn) topBtn.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: reducedMotion() ? "auto" : "smooth" });
  });
}

/* ---------- boot ---------- */
document.addEventListener("DOMContentLoaded", async () => {
  try { Engine = await import("./engine.js"); } catch (e) { Engine = null; }
  await loadChain();
  if (!Engine && typeof EMBEDDED_DATA === "undefined") {
    document.querySelector("main").insertAdjacentHTML("afterbegin",
      `<div style="max-width:1160px;margin:20px auto;padding:16px 24px;background:#3f1d1d;border:1px solid #f87171;border-radius:12px;">数据加载失败：浏览器既加载不了 engine.js，也找不到 data.js。请用 python -m http.server 打开 frontend/。</div>`);
    return;
  }
  initScroll();
  syncControlLabels();
  initGame();

  /* controls: live re-run (debounced) + explicit Run button */
  let debounce = null;
  const scheduleRun = () => {
    syncControlLabels();
    clearTimeout(debounce);
    debounce = setTimeout(() => runPlayground(readParams()), 350);
  };
  ["in-seed", "in-days", "in-residents", "in-tax", "in-orders"].forEach((id) =>
    $(id).addEventListener("input", scheduleRun));
  $("btn-run").addEventListener("click", () => { clearTimeout(debounce); runPlayground(readParams()); });
  $("btn-rerun").addEventListener("click", rerunSame);
  $("btn-copy-digest").addEventListener("click", (e) =>
    copyText($("pg-digest-full").textContent, e.currentTarget));
  $("btn-copy-cast").addEventListener("click", (e) =>
    copyText($("cast-cmd").textContent, e.currentTarget));
  $("btn-copy-ay-cmd").addEventListener("click", (e) =>
    copyText($("ay-cmd").textContent, e.currentTarget));
  $("btn-copy-py").addEventListener("click", (e) =>
    copyText($("py-cmd").textContent, e.currentTarget));
  $("btn-more-residents").addEventListener("click", () => {
    showAllResidents = !showAllResidents;
    if (current) renderResidents(current);
  });
  $("btn-town").addEventListener("click", () => {
    townPaused = !townPaused;
    $("btn-town").textContent = townPaused ? "▶ 继续小镇" : "⏸ 暂停小镇";
  });
  $("btn-save-a").addEventListener("click", () => {
    if (!current) return;
    savedA = snapshot(current, `种子 ${current.seed} · 税 ${current.taxPct}% · 订单 ${current.maxOrders}`);
    renderCompare();
  });
  $("btn-save-b").addEventListener("click", () => {
    if (!current) return;
    savedB = snapshot(current, `种子 ${current.seed} · 税 ${current.taxPct}% · 订单 ${current.maxOrders}`);
    renderCompare();
  });
  $("btn-preset-seeds").addEventListener("click", () => presetCompare("seeds"));
  $("btn-preset-tax").addEventListener("click", () => presetCompare("tax"));
  window.addEventListener("resize", () => { if (current) drawChart(current); });

  /* default world on load: seed 42, 100 days, 20 residents */
  await runPlayground({ ...DEFAULT_PARAMS });
});
