// GENESIS engine — a faithful, dependency-free ES-module port of the Python
// simulation in genesis/ (world.py, economy.py, agents.py, simulation.py,
// reporting.py play_summary). Runnable in Node and in a browser.
//
// Exactness notes (see the Python sources for the rules):
//  - RNG: CPython's random.Random — Mersenne Twister seeded via
//    init_by_array from int.from_bytes(utf8(seed) + sha512(utf8(seed)), 'big').
//  - Integer // is floor division (BigInt fallback for negative operands);
//    round() is Python half-even on the exact binary value (BigInt).
//  - Canonical JSON is Python json.dumps(sort_keys=True, separators=(",", ":")),
//    with Python float repr for the (few) floats in the digest payload.
//  - SHA-256 / SHA-512 are implemented here in pure JS (no Node crypto, no CDN).

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const RESOURCES = ["food", "wood", "stone"];
export const OCCUPATIONS = ["farmer", "woodcutter", "miner"];
export const PRODUCT = { farmer: "food", woodcutter: "wood", miner: "stone" };
export const MAX_HEALTH = 100;
export const BPS = 10000;

export const NAME_POOL = [
  "Ada", "Bram", "Chiara", "Dmitri", "Eshe", "Farid", "Greta", "Hiro", "Ines", "Jonas",
  "Kalani", "Lior", "Mei", "Nadia", "Omar", "Priya", "Quentin", "Rosa", "Sven", "Tamar",
  "Ulla", "Vikram", "Wanjiru", "Xavier", "Yara", "Zeno", "Amara", "Bilal", "Celine", "Darius",
  "Elena", "Femi", "Gael", "Hana", "Idris", "Juno", "Kofi", "Lena", "Mateo", "Noor",
];

export function defaultConfig() {
  return {
    num_residents: 20,
    initial_cash: 10000,
    initial_inventory: { food: 5, wood: 5, stone: 5 },
    initial_prices: { food: 300, wood: 400, stone: 500 },
    daily_needs: { food: 1, wood: 1, stone: 1 },
    unmet_need_penalty: { food: 20, wood: 5, stone: 3 },
    base_output: { farmer: 5, woodcutter: 4, miner: 3 },
    skill_min: 75,
    skill_max: 125,
    weather_min_pct: 90,
    weather_max_pct: 110,
    health_recovery: 5,
    rest_recovery: 5,
    min_price: 1,
    max_price: 1000000,
    max_orders_per_day: 10,
    max_order_quantity: 1000,
    no_trade_price_step_bps: 500,
    occupation_cooldown_days: 7,
  };
}

// ---------------------------------------------------------------------------
// Integer arithmetic: Python // (floor division), divmod, ceil division
// ---------------------------------------------------------------------------

// All engine divisions have non-negative operands; for those, double division
// is exact here (a proof: a wrong floor would need a+1 >= 2**53, but every
// dividend is < 2**40). The BigInt path covers negative operands exactly.
export function floorDiv(a, b) {
  if (a >= 0 && b > 0) return Math.floor(a / b);
  const A = BigInt(a), B = BigInt(b);
  let q = A / B;
  const r = A % B;
  if (r !== 0n && ((r < 0n) !== (B < 0n))) q -= 1n;
  return Number(q);
}

export function ceilDiv(a, b) {
  if (a >= 0 && b > 0) return Math.ceil(a / b);
  return -floorDiv(-a, b);
}

export function divmod(a, b) {
  const q = floorDiv(a, b);
  return [q, a - q * b];
}

// ---------------------------------------------------------------------------
// Python round(): half-even on the exact binary value, via BigInt.
// ---------------------------------------------------------------------------

export function pyRound(x, ndigits) {
  if (Number.isNaN(x)) return NaN;
  if (!Number.isFinite(x)) return x;
  const buf = new DataView(new ArrayBuffer(8));
  buf.setFloat64(0, x);
  const bits = buf.getBigUint64(0);
  const neg = (bits >> 63n) !== 0n;
  const expBits = Number((bits >> 52n) & 0x7ffn);
  let mant = bits & ((1n << 52n) - 1n);
  let exp2;
  if (expBits === 0) {
    exp2 = -1074; // subnormal: no implicit leading bit
  } else {
    mant |= 1n << 52n;
    exp2 = expBits - 1075;
  }
  // value = (-1)^neg * mant * 2^exp2 ; scale by 10^ndigits and round half-even.
  const ten = 10n ** BigInt(ndigits);
  let num = mant * ten;
  let den = 1n;
  if (exp2 >= 0) num <<= BigInt(exp2);
  else den = 1n << BigInt(-exp2);
  let q = num / den;
  const r = num % den;
  const twice = r * 2n;
  if (twice > den || (twice === den && q % 2n === 1n)) q += 1n;
  if (q === 0n) return neg ? -0 : 0;
  // q < 2**53 for every value this engine rounds, so Number(q) is exact and
  // the final division is a single correctly-rounded IEEE division.
  return Number(neg ? -q : q) / Number(ten);
}

// ---------------------------------------------------------------------------
// Python float repr (shortest round-trip), as used by json.dumps.
// ---------------------------------------------------------------------------

export function pyReprFloat(x) {
  if (Number.isNaN(x)) return "nan";
  if (x === Infinity) return "inf";
  if (x === -Infinity) return "-inf";
  if (x === 0) return Object.is(x, -0) ? "-0.0" : "0.0";
  const sign = x < 0 ? "-" : "";
  const ax = Math.abs(x);
  // Shortest digit string + decimal exponent from JS, then Python formatting.
  const s = String(ax);
  let digits, exp10;
  if (s.includes("e")) {
    const [mant, e] = s.split("e");
    const ei = parseInt(e, 10);
    const dot = mant.indexOf(".");
    if (dot === -1) { digits = mant; exp10 = ei; }
    else { digits = mant.slice(0, dot) + mant.slice(dot + 1); exp10 = ei + dot - 1; }
  } else {
    const dot = s.indexOf(".");
    if (dot === -1) {
      digits = s;
      exp10 = s.length - 1;
    } else {
      const intPart = s.slice(0, dot), fracPart = s.slice(dot + 1);
      if (intPart !== "0") {
        digits = intPart + fracPart;
        exp10 = intPart.length - 1;
      } else {
        let i = 0;
        while (fracPart[i] === "0") i++;
        digits = fracPart.slice(i);
        exp10 = -(i + 1);
      }
    }
    digits = digits.replace(/0+$/, "");
  }
  if (exp10 >= -4 && exp10 < 16) {
    // Fixed notation.
    if (exp10 >= digits.length - 1) {
      return sign + digits + "0".repeat(exp10 - digits.length + 1) + ".0";
    }
    if (exp10 >= 0) {
      return sign + digits.slice(0, exp10 + 1) + "." + digits.slice(exp10 + 1);
    }
    return sign + "0." + "0".repeat(-exp10 - 1) + digits;
  }
  // Scientific notation: d[.rest]e±XX (exponent always two digits).
  const mant = digits.length === 1 ? digits : digits[0] + "." + digits.slice(1);
  return sign + mant + "e" + (exp10 < 0 ? "-" : "+") + String(Math.abs(exp10)).padStart(2, "0");
}

// ---------------------------------------------------------------------------
// SHA-512 (32-bit hi/lo word pairs; used only for string seeding).
// K verified against the cube-root-of-primes derivation.
// ---------------------------------------------------------------------------

const K512_HI = new Int32Array(80);
const K512_LO = new Int32Array(80);
{
  const K = [
    0x428a2f98d728ae22n, 0x7137449123ef65cdn, 0xb5c0fbcfec4d3b2fn, 0xe9b5dba58189dbbcn,
    0x3956c25bf348b538n, 0x59f111f1b605d019n, 0x923f82a4af194f9bn, 0xab1c5ed5da6d8118n,
    0xd807aa98a3030242n, 0x12835b0145706fben, 0x243185be4ee4b28cn, 0x550c7dc3d5ffb4e2n,
    0x72be5d74f27b896fn, 0x80deb1fe3b1696b1n, 0x9bdc06a725c71235n, 0xc19bf174cf692694n,
    0xe49b69c19ef14ad2n, 0xefbe4786384f25e3n, 0x0fc19dc68b8cd5b5n, 0x240ca1cc77ac9c65n,
    0x2de92c6f592b0275n, 0x4a7484aa6ea6e483n, 0x5cb0a9dcbd41fbd4n, 0x76f988da831153b5n,
    0x983e5152ee66dfabn, 0xa831c66d2db43210n, 0xb00327c898fb213fn, 0xbf597fc7beef0ee4n,
    0xc6e00bf33da88fc2n, 0xd5a79147930aa725n, 0x06ca6351e003826fn, 0x142929670a0e6e70n,
    0x27b70a8546d22ffcn, 0x2e1b21385c26c926n, 0x4d2c6dfc5ac42aedn, 0x53380d139d95b3dfn,
    0x650a73548baf63den, 0x766a0abb3c77b2a8n, 0x81c2c92e47edaee6n, 0x92722c851482353bn,
    0xa2bfe8a14cf10364n, 0xa81a664bbc423001n, 0xc24b8b70d0f89791n, 0xc76c51a30654be30n,
    0xd192e819d6ef5218n, 0xd69906245565a910n, 0xf40e35855771202an, 0x106aa07032bbd1b8n,
    0x19a4c116b8d2d0c8n, 0x1e376c085141ab53n, 0x2748774cdf8eeb99n, 0x34b0bcb5e19b48a8n,
    0x391c0cb3c5c95a63n, 0x4ed8aa4ae3418acbn, 0x5b9cca4f7763e373n, 0x682e6ff3d6b2b8a3n,
    0x748f82ee5defb2fcn, 0x78a5636f43172f60n, 0x84c87814a1f0ab72n, 0x8cc702081a6439ecn,
    0x90befffa23631e28n, 0xa4506cebde82bde9n, 0xbef9a3f7b2c67915n, 0xc67178f2e372532bn,
    0xca273eceea26619cn, 0xd186b8c721c0c207n, 0xeada7dd6cde0eb1en, 0xf57d4f7fee6ed178n,
    0x06f067aa72176fban, 0x0a637dc5a2c898a6n, 0x113f9804bef90daen, 0x1b710b35131c471bn,
    0x28db77f523047d84n, 0x32caab7b40c72493n, 0x3c9ebe0a15c9bebcn, 0x431d67c49c100d4cn,
    0x4cc5d4becb3e42b6n, 0x597f299cfc657e2an, 0x5fcb6fab3ad6faecn, 0x6c44198c4a475817n,
  ];
  for (let i = 0; i < 80; i++) {
    K512_HI[i] = Number((K[i] >> 32n) & 0xffffffffn) | 0;
    K512_LO[i] = Number(K[i] & 0xffffffffn) | 0;
  }
}
const H512_HI = new Int32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
const H512_LO = new Int32Array([0xf3bcc908, 0x84caa73b, 0xfe94f82b, 0x5f1d36f1, 0xade682d1, 0x2b3e6c1f, 0xfb41bd6b, 0x137e2179]);

export function sha512Bytes(bytes) {
  const l = bytes.length;
  const paddedLen = Math.ceil((l + 17) / 128) * 128;
  const buf = new Uint8Array(paddedLen);
  buf.set(bytes);
  buf[l] = 0x80;
  const dv = new DataView(buf.buffer);
  dv.setUint32(paddedLen - 8, Math.floor((l * 8) / 0x100000000));
  dv.setUint32(paddedLen - 4, (l * 8) >>> 0);
  const wHi = new Int32Array(80), wLo = new Int32Array(80);
  let h0h = H512_HI[0], h0l = H512_LO[0], h1h = H512_HI[1], h1l = H512_LO[1];
  let h2h = H512_HI[2], h2l = H512_LO[2], h3h = H512_HI[3], h3l = H512_LO[3];
  let h4h = H512_HI[4], h4l = H512_LO[4], h5h = H512_HI[5], h5l = H512_LO[5];
  let h6h = H512_HI[6], h6l = H512_LO[6], h7h = H512_HI[7], h7l = H512_LO[7];
  for (let off = 0; off < paddedLen; off += 128) {
    for (let i = 0; i < 16; i++) {
      wHi[i] = dv.getInt32(off + i * 8);
      wLo[i] = dv.getInt32(off + i * 8 + 4);
    }
    for (let i = 16; i < 80; i++) {
      // s0 = rotr(w[i-15],1) ^ rotr(w[i-15],8) ^ shr(w[i-15],7)
      const xh = wHi[i - 15], xl = wLo[i - 15];
      const s0h = ((xh >>> 1) | (xl << 31)) ^ ((xh >>> 8) | (xl << 24)) ^ (xh >>> 7);
      const s0l = ((xl >>> 1) | (xh << 31)) ^ ((xl >>> 8) | (xh << 24)) ^ ((xl >>> 7) | (xh << 25));
      // s1 = rotr(w[i-2],19) ^ rotr(w[i-2],61) ^ shr(w[i-2],6)
      const yh = wHi[i - 2], yl = wLo[i - 2];
      const s1h = ((yh >>> 19) | (yl << 13)) ^ ((yl >>> 29) | (yh << 3)) ^ (yh >>> 6);
      const s1l = ((yl >>> 19) | (yh << 13)) ^ ((yh >>> 29) | (yl << 3)) ^ ((yl >>> 6) | (yh << 26));
      // w[i] = w[i-16] + s0 + w[i-7] + s1 (64-bit adds with carry)
      let lo = (wLo[i - 16] + s0l) | 0, carry = (lo >>> 0) < (wLo[i - 16] >>> 0) ? 1 : 0;
      let hi = (wHi[i - 16] + s0h + carry) | 0;
      let lo2 = (lo + wLo[i - 7]) | 0; carry = (lo2 >>> 0) < (lo >>> 0) ? 1 : 0;
      hi = (hi + wHi[i - 7] + carry) | 0; lo = lo2;
      lo2 = (lo + s1l) | 0; carry = (lo2 >>> 0) < (lo >>> 0) ? 1 : 0;
      hi = (hi + s1h + carry) | 0; lo = lo2;
      wHi[i] = hi; wLo[i] = lo;
    }
    let ah = h0h, al = h0l, bh = h1h, bl = h1l, ch = h2h, cl = h2l, dh = h3h, dl = h3l;
    let eh = h4h, el = h4l, fh = h5h, fl = h5l, gh = h6h, gl = h6l, hh = h7h, hl = h7l;
    for (let i = 0; i < 80; i++) {
      // S1 = rotr(e,14) ^ rotr(e,18) ^ rotr(e,41)
      const S1h = ((eh >>> 14) | (el << 18)) ^ ((eh >>> 18) | (el << 14)) ^ ((el >>> 9) | (eh << 23));
      const S1l = ((el >>> 14) | (eh << 18)) ^ ((el >>> 18) | (eh << 14)) ^ ((eh >>> 9) | (el << 23));
      const chH = (eh & fh) ^ (~eh & gh), chL = (el & fl) ^ (~el & gl);
      // t1 = h + S1 + ch + K[i] + w[i]
      let lo = (hl + S1l) | 0, carry = (lo >>> 0) < (hl >>> 0) ? 1 : 0;
      let hi = (hh + S1h + carry) | 0;
      let lo2 = (lo + chL) | 0; carry = (lo2 >>> 0) < (lo >>> 0) ? 1 : 0;
      hi = (hi + chH + carry) | 0; lo = lo2;
      lo2 = (lo + K512_LO[i]) | 0; carry = (lo2 >>> 0) < (lo >>> 0) ? 1 : 0;
      hi = (hi + K512_HI[i] + carry) | 0; lo = lo2;
      lo2 = (lo + wLo[i]) | 0; carry = (lo2 >>> 0) < (lo >>> 0) ? 1 : 0;
      hi = (hi + wHi[i] + carry) | 0; lo = lo2;
      const t1h = hi, t1l = lo;
      // S0 = rotr(a,28) ^ rotr(a,34) ^ rotr(a,39)
      const S0h = ((ah >>> 28) | (al << 4)) ^ ((al >>> 2) | (ah << 30)) ^ ((al >>> 7) | (ah << 25));
      const S0l = ((al >>> 28) | (ah << 4)) ^ ((ah >>> 2) | (al << 30)) ^ ((ah >>> 7) | (al << 25));
      const majH = (ah & bh) ^ (ah & ch) ^ (bh & ch), majL = (al & bl) ^ (al & cl) ^ (bl & cl);
      lo = (S0l + majL) | 0; carry = (lo >>> 0) < (S0l >>> 0) ? 1 : 0;
      const t2h = (S0h + majH + carry) | 0, t2l = lo;
      hh = gh; hl = gl; gh = fh; gl = fl; fh = eh; fl = el;
      lo = (dl + t1l) | 0; carry = (lo >>> 0) < (dl >>> 0) ? 1 : 0;
      eh = (dh + t1h + carry) | 0; el = lo;
      dh = ch; dl = cl; ch = bh; cl = bl; bh = ah; bl = al;
      lo = (t1l + t2l) | 0; carry = (lo >>> 0) < (t1l >>> 0) ? 1 : 0;
      ah = (t1h + t2h + carry) | 0; al = lo;
    }
    let lo = (h0l + al) | 0, carry = (lo >>> 0) < (h0l >>> 0) ? 1 : 0;
    h0h = (h0h + ah + carry) | 0; h0l = lo;
    lo = (h1l + bl) | 0; carry = (lo >>> 0) < (h1l >>> 0) ? 1 : 0;
    h1h = (h1h + bh + carry) | 0; h1l = lo;
    lo = (h2l + cl) | 0; carry = (lo >>> 0) < (h2l >>> 0) ? 1 : 0;
    h2h = (h2h + ch + carry) | 0; h2l = lo;
    lo = (h3l + dl) | 0; carry = (lo >>> 0) < (h3l >>> 0) ? 1 : 0;
    h3h = (h3h + dh + carry) | 0; h3l = lo;
    lo = (h4l + el) | 0; carry = (lo >>> 0) < (h4l >>> 0) ? 1 : 0;
    h4h = (h4h + eh + carry) | 0; h4l = lo;
    lo = (h5l + fl) | 0; carry = (lo >>> 0) < (h5l >>> 0) ? 1 : 0;
    h5h = (h5h + fh + carry) | 0; h5l = lo;
    lo = (h6l + gl) | 0; carry = (lo >>> 0) < (h6l >>> 0) ? 1 : 0;
    h6h = (h6h + gh + carry) | 0; h6l = lo;
    lo = (h7l + hl) | 0; carry = (lo >>> 0) < (h7l >>> 0) ? 1 : 0;
    h7h = (h7h + hh + carry) | 0; h7l = lo;
  }
  const out = new Uint8Array(64);
  const odv = new DataView(out.buffer);
  const H = [[h0h, h0l], [h1h, h1l], [h2h, h2l], [h3h, h3l], [h4h, h4l], [h5h, h5l], [h6h, h6l], [h7h, h7l]];
  for (let i = 0; i < 8; i++) {
    odv.setInt32(i * 8, H[i][0]);
    odv.setInt32(i * 8 + 4, H[i][1]);
  }
  return out;
}

// ---------------------------------------------------------------------------
// SHA-256 (32-bit ops; K verified against the cube-root-of-primes derivation).
// ---------------------------------------------------------------------------

const K256 = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

function rotr32(x, n) {
  return (x >>> n) | (x << (32 - n));
}

export function sha256Hex(bytes) {
  const l = bytes.length;
  const bitLen = l * 8;
  const paddedLen = Math.ceil((l + 9) / 64) * 64;
  const buf = new Uint8Array(paddedLen);
  buf.set(bytes);
  buf[l] = 0x80;
  const dv = new DataView(buf.buffer);
  // 64-bit big-endian length: high word then low word.
  dv.setUint32(paddedLen - 8, Math.floor(bitLen / 0x100000000));
  dv.setUint32(paddedLen - 4, bitLen >>> 0);
  let h0 = 0x6a09e667, h1 = 0xbb67ae85, h2 = 0x3c6ef372, h3 = 0xa54ff53a;
  let h4 = 0x510e527f, h5 = 0x9b05688c, h6 = 0x1f83d9ab, h7 = 0x5be0cd19;
  const w = new Uint32Array(64);
  const words32 = new Uint32Array(buf.buffer); // host is little-endian
  for (let off = 0; off < paddedLen; off += 64) {
    const base = off / 4;
    for (let i = 0; i < 16; i++) {
      const x = words32[base + i];
      w[i] = ((x << 24) | ((x & 0xff00) << 8) | ((x >> 8) & 0xff00) | (x >>> 24)) >>> 0;
    }
    for (let i = 16; i < 64; i++) {
      const s0 = rotr32(w[i - 15], 7) ^ rotr32(w[i - 15], 18) ^ (w[i - 15] >>> 3);
      const s1 = rotr32(w[i - 2], 17) ^ rotr32(w[i - 2], 19) ^ (w[i - 2] >>> 10);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) | 0;
    }
    let a = h0, b = h1, c = h2, d = h3, e = h4, f = h5, g = h6, h = h7;
    for (let i = 0; i < 64; i++) {
      const S1 = rotr32(e, 6) ^ rotr32(e, 11) ^ rotr32(e, 25);
      const ch = (e & f) ^ (~e & g);
      const t1 = (h + S1 + ch + K256[i] + w[i]) | 0;
      const S0 = rotr32(a, 2) ^ rotr32(a, 13) ^ rotr32(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + maj) | 0;
      h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
    }
    h0 = (h0 + a) | 0; h1 = (h1 + b) | 0; h2 = (h2 + c) | 0; h3 = (h3 + d) | 0;
    h4 = (h4 + e) | 0; h5 = (h5 + f) | 0; h6 = (h6 + g) | 0; h7 = (h7 + h) | 0;
  }
  const hex = (x) => (x >>> 0).toString(16).padStart(8, "0");
  return hex(h0) + hex(h1) + hex(h2) + hex(h3) + hex(h4) + hex(h5) + hex(h6) + hex(h7);
}

// ---------------------------------------------------------------------------
// CPython random.Random: Mersenne Twister + the Random methods the engine uses.
// ---------------------------------------------------------------------------

const MT_N = 624, MT_M = 397, MT_MATRIX_A = 0x9908b0df;
const MT_UPPER = 0x80000000, MT_LOWER = 0x7fffffff;

export class MT19937 {
  constructor() {
    this.mt = new Uint32Array(MT_N);
    this.index = MT_N + 1;
  }

  initGenrand(s) {
    this.mt[0] = s >>> 0;
    for (let i = 1; i < MT_N; i++) {
      const prev = this.mt[i - 1];
      this.mt[i] = (Math.imul(1812433253, prev ^ (prev >>> 30)) + i) >>> 0;
    }
    this.index = MT_N;
  }

  initByArray(key) {
    this.initGenrand(19650218);
    let i = 1, j = 0;
    const keyLen = key.length;
    let k = Math.max(MT_N, keyLen);
    for (; k; k--) {
      const prev = this.mt[i - 1];
      this.mt[i] = ((this.mt[i] ^ Math.imul(prev ^ (prev >>> 30), 1664525)) + key[j] + j) >>> 0;
      i++; j++;
      if (i >= MT_N) { this.mt[0] = this.mt[MT_N - 1]; i = 1; }
      if (j >= keyLen) j = 0;
    }
    for (k = MT_N - 1; k; k--) {
      const prev = this.mt[i - 1];
      this.mt[i] = ((this.mt[i] ^ Math.imul(prev ^ (prev >>> 30), 1566083941)) - i) >>> 0;
      i++;
      if (i >= MT_N) { this.mt[0] = this.mt[MT_N - 1]; i = 1; }
    }
    this.mt[0] = 0x80000000;
    this.index = MT_N;
  }

  // CPython random.seed(version=2) for a str: a = int.from_bytes(
  // utf8(s) + sha512(utf8(s)).digest()), then init_by_array over the
  // little-endian 32-bit words of that integer.
  seedString(s) {
    const bytes = new TextEncoder().encode(s);
    const digest = sha512Bytes(bytes);
    const total = new Uint8Array(bytes.length + digest.length);
    total.set(bytes);
    total.set(digest, bytes.length);
    const nWords = Math.ceil(total.length / 4);
    const key = new Uint32Array(nWords);
    for (let wIdx = 0; wIdx < nWords; wIdx++) {
      let word = 0;
      for (let b = 0; b < 4; b++) {
        const idx = total.length - 1 - (wIdx * 4 + b);
        if (idx >= 0) word |= total[idx] << (8 * b);
      }
      key[wIdx] = word >>> 0;
    }
    this.initByArray(key);
  }

  genrandInt32() {
    if (this.index >= MT_N) {
      const mt = this.mt;
      for (let kk = 0; kk < MT_N - MT_M; kk++) {
        const y = (mt[kk] & MT_UPPER) | (mt[kk + 1] & MT_LOWER);
        mt[kk] = (mt[kk + MT_M] ^ (y >>> 1) ^ (y & 1 ? MT_MATRIX_A : 0)) >>> 0;
      }
      for (let kk = MT_N - MT_M; kk < MT_N - 1; kk++) {
        const y = (mt[kk] & MT_UPPER) | (mt[kk + 1] & MT_LOWER);
        mt[kk] = (mt[kk + (MT_M - MT_N)] ^ (y >>> 1) ^ (y & 1 ? MT_MATRIX_A : 0)) >>> 0;
      }
      const y = (mt[MT_N - 1] & MT_UPPER) | (mt[0] & MT_LOWER);
      mt[MT_N - 1] = (mt[MT_M - 1] ^ (y >>> 1) ^ (y & 1 ? MT_MATRIX_A : 0)) >>> 0;
      this.index = 0;
    }
    let y = this.mt[this.index++];
    y ^= y >>> 11;
    y ^= (y << 7) & 0x9d2c5680;
    y ^= (y << 15) & 0xefc60000;
    y ^= y >>> 18;
    return y >>> 0;
  }

  // CPython getrandbits(k) for k <= 32: top k bits of one uint32.
  getrandbits(k) {
    if (k <= 0) return 0;
    if (k > 32) throw new Error("getrandbits > 32 not supported");
    return this.genrandInt32() >>> (32 - k);
  }

  // CPython random(): (a>>5)*2**26 + (b>>6), over 2**53.
  random() {
    const a = this.genrandInt32() >>> 5;
    const b = this.genrandInt32() >>> 6;
    return (a * 67108864 + b) / 9007199254740992;
  }

  // CPython _randbelow(n): k = n.bit_length(); reject while r >= n.
  randbelow(n) {
    const k = n.toString(2).length;
    let r = this.getrandbits(k);
    while (r >= n) r = this.getrandbits(k);
    return r;
  }

  randint(a, b) {
    return a + this.randbelow(b - a + 1);
  }

  randrange(n) {
    return this.randbelow(n);
  }

  // CPython shuffle: Fisher-Yates from the end, j = _randbelow(i+1).
  shuffle(arr) {
    for (let i = arr.length - 1; i >= 1; i--) {
      const j = this.randbelow(i + 1);
      const t = arr[i]; arr[i] = arr[j]; arr[j] = t;
    }
    return arr;
  }

  // CPython sample: pool path when n <= 21 + 4**ceil(log(k*3, 4)) (k > 5),
  // else the set path. The engine only samples 40 of 40 (pool path).
  sample(population, k) {
    const n = population.length;
    const setsize = 21 + (k > 5 ? 4 ** Math.ceil(Math.log(k * 3) / Math.log(4)) : 0);
    const result = new Array(k);
    if (n <= setsize) {
      const pool = population.slice();
      for (let i = 0; i < k; i++) {
        const j = this.randbelow(n - i);
        result[i] = pool[j];
        pool[j] = pool[n - i - 1];
      }
    } else {
      const selected = new Set();
      for (let i = 0; i < k; i++) {
        let j = this.randbelow(n);
        while (selected.has(j)) j = this.randbelow(n);
        selected.add(j);
        result[i] = population[j];
      }
    }
    return result;
  }
}

export function deriveRng(seed, day, stream) {
  const rng = new MT19937();
  rng.seedString(`genesis:${seed}:${day}:${stream}`);
  return rng;
}

// ---------------------------------------------------------------------------
// Canonical JSON: Python json.dumps(sort_keys=True, separators=(",", ":")).
// Floats appear only as PyFloat (stats mean_health/gini); plain numbers are
// always integers in the digest payload.
// ---------------------------------------------------------------------------

export class PyFloat {
  constructor(v) {
    this.v = v;
  }
}

function pyJsonString(s) {
  let out = '"';
  for (const ch of s) {
    const code = ch.codePointAt(0);
    if (ch === '"') out += '\\"';
    else if (ch === "\\") out += "\\\\";
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (ch === "\t") out += "\\t";
    else if (ch === "\b") out += "\\b";
    else if (ch === "\f") out += "\\f";
    else if (code < 0x20) out += "\\u" + code.toString(16).padStart(4, "0");
    else if (code < 0x7f) out += ch; // 0x20-0x7e pass through; 0x7f is escaped, like Python
    else if (code <= 0xffff) out += "\\u" + code.toString(16).padStart(4, "0");
    else {
      const v = code - 0x10000;
      const hi = 0xd800 + (v >> 10), lo = 0xdc00 + (v & 0x3ff);
      out += "\\u" + hi.toString(16).padStart(4, "0") + "\\u" + lo.toString(16).padStart(4, "0");
    }
  }
  return out + '"';
}

export function canonicalStringify(v) {
  if (v === null) return "null";
  if (v === true) return "true";
  if (v === false) return "false";
  if (v instanceof PyFloat) return pyReprFloat(v.v);
  if (typeof v === "number") {
    return Number.isInteger(v) ? String(v) : pyReprFloat(v);
  }
  if (typeof v === "string") return fastJsonString(v);
  if (Array.isArray(v)) return "[" + v.map(canonicalStringify).join(",") + "]";
  const keys = Object.keys(v).sort();
  return "{" + keys.map((k) => fastJsonString(k) + ":" + canonicalStringify(v[k])).join(",") + "}";
}

// For pure-ASCII strings the native JSON.stringify output is identical to
// Python's json.dumps(ensure_ascii=True); non-ASCII / control characters
// take the exact path below.
const ASCII_RE = /^[\x20-\x7e]*$/;
function fastJsonString(s) {
  return ASCII_RE.test(s) ? JSON.stringify(s) : pyJsonString(s);
}

function unwrap(v) {
  return v instanceof PyFloat ? v.v : v;
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function resMap(food, wood, stone) {
  return { food, wood, stone };
}
function occMap(farmer, woodcutter, miner) {
  return { farmer, woodcutter, miner };
}

function compareKeys(a, b) {
  if (Array.isArray(a) && Array.isArray(b)) {
    for (let i = 0; i < Math.min(a.length, b.length); i++) {
      if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
    }
    return a.length - b.length;
  }
  return a < b ? -1 : a > b ? 1 : 0;
}

// Python max(): the FIRST maximum on ties.
export function maxByFirst(arr, keyFn) {
  let best = arr[0];
  let bestKey = keyFn(arr[0]);
  for (let i = 1; i < arr.length; i++) {
    const k = keyFn(arr[i]);
    if (compareKeys(k, bestKey) > 0) {
      best = arr[i];
      bestKey = k;
    }
  }
  return best;
}

function minByFirst(arr, keyFn) {
  let best = arr[0];
  let bestKey = keyFn(arr[0]);
  for (let i = 1; i < arr.length; i++) {
    const k = keyFn(arr[i]);
    if (compareKeys(k, bestKey) < 0) {
      best = arr[i];
      bestKey = k;
    }
  }
  return best;
}

// ---------------------------------------------------------------------------
// World creation (genesis/world.py)
// ---------------------------------------------------------------------------

export function residentNames(rng, count) {
  const pool = rng.sample(NAME_POOL, NAME_POOL.length);
  const names = [];
  for (let index = 0; index < count; index++) {
    const generation = Math.floor(index / pool.length);
    const base = pool[index % pool.length];
    names.push(generation === 0 ? base : `${base} ${generation + 1}`);
  }
  return names;
}

export function createWorld(config, seed) {
  const rng = deriveRng(seed, 0, "genesis");
  const names = residentNames(rng, config.num_residents);
  const residents = [];
  for (let index = 0; index < config.num_residents; index++) {
    const skills = {};
    for (const occ of OCCUPATIONS) skills[occ] = rng.randint(config.skill_min, config.skill_max);
    const best = maxByFirst(OCCUPATIONS, (occ) => skills[occ]);
    residents.push({
      id: index + 1,
      name: names[index],
      occupation: best,
      skills,
      cash: config.initial_cash,
      inventory: { ...config.initial_inventory },
      health: MAX_HEALTH,
      alive: true,
      policy: "rule_based",
      last_occupation_change: null,
      died_on: null,
    });
  }
  const world = {
    seed,
    config,
    residents,
    market: {},
    ledger: {
      money_supply: config.initial_cash * config.num_residents,
      initial: {},
      produced: resMap(0, 0, 0),
      consumed: resMap(0, 0, 0),
    },
    day: 0,
    events: [],
    stats: [],
  };
  for (const r of RESOURCES) {
    world.market[r] = { price: config.initial_prices[r], demand: 0, supply: 0, volume: 0 };
    world.ledger.initial[r] = config.initial_inventory[r] * config.num_residents;
  }
  record(world, "world_created", null, null, {
    seed,
    residents: config.num_residents,
    money_supply: world.ledger.money_supply,
    prices: { ...prices(world) },
  });
  for (const r of residents) {
    record(world, "resident_created", r.id, null, {
      name: r.name,
      occupation: r.occupation,
      skills: { ...r.skills },
      cash: r.cash,
      inventory: { ...r.inventory },
      policy: r.policy,
    });
  }
  return world;
}

export function record(world, kind, residentId, counterpartyId, data) {
  const event = {
    seq: world.events.length + 1,
    day: world.day,
    kind,
    resident_id: residentId === undefined || residentId === null ? null : residentId,
    counterparty_id: counterpartyId === undefined || counterpartyId === null ? null : counterpartyId,
    data,
  };
  world.events.push(event);
  return event;
}

export function living(world) {
  return world.residents.filter((r) => r.alive);
}

export function prices(world) {
  const out = {};
  for (const r of RESOURCES) out[r] = world.market[r].price;
  return out;
}

export function holdings(world, livingOnly) {
  const totals = resMap(0, 0, 0);
  for (const r of world.residents) {
    if (livingOnly && !r.alive) continue;
    for (const res of RESOURCES) totals[res] += r.inventory[res];
  }
  return totals;
}

export function totalCash(world) {
  return world.residents.reduce((s, r) => s + r.cash, 0);
}

export function residentWealth(world, resident) {
  let w = resident.cash;
  for (const res of RESOURCES) w += resident.inventory[res] * world.market[res].price;
  return w;
}

// ---------------------------------------------------------------------------
// Serialisation (world.to_dict / state_digest)
// ---------------------------------------------------------------------------

export function configToDict(config) {
  return {
    num_residents: config.num_residents,
    initial_cash: config.initial_cash,
    initial_inventory: { ...config.initial_inventory },
    initial_prices: { ...config.initial_prices },
    daily_needs: { ...config.daily_needs },
    unmet_need_penalty: { ...config.unmet_need_penalty },
    base_output: { ...config.base_output },
    skill_min: config.skill_min,
    skill_max: config.skill_max,
    weather_min_pct: config.weather_min_pct,
    weather_max_pct: config.weather_max_pct,
    health_recovery: config.health_recovery,
    rest_recovery: config.rest_recovery,
    min_price: config.min_price,
    max_price: config.max_price,
    max_orders_per_day: config.max_orders_per_day,
    max_order_quantity: config.max_order_quantity,
    no_trade_price_step_bps: config.no_trade_price_step_bps,
    occupation_cooldown_days: config.occupation_cooldown_days,
  };
}

function residentToDict(r) {
  return {
    id: r.id,
    name: r.name,
    occupation: r.occupation,
    skills: { ...r.skills },
    cash: r.cash,
    inventory: { ...r.inventory },
    health: r.health,
    alive: r.alive,
    policy: r.policy,
    last_occupation_change: r.last_occupation_change,
    died_on: r.died_on,
  };
}

export function worldToDict(world) {
  return {
    seed: world.seed,
    day: world.day,
    config: configToDict(world.config),
    residents: world.residents.map(residentToDict),
    market: Object.fromEntries(RESOURCES.map((r) => [r, { ...world.market[r] }])),
    ledger: {
      money_supply: world.ledger.money_supply,
      initial: { ...world.ledger.initial },
      produced: { ...world.ledger.produced },
      consumed: { ...world.ledger.consumed },
    },
    events: world.events.map((e) => ({
      seq: e.seq,
      day: e.day,
      kind: e.kind,
      resident_id: e.resident_id,
      counterparty_id: e.counterparty_id,
      data: e.data,
    })),
    stats: world.stats.map((s) => ({ ...s })),
  };
}

export function stateDigest(world) {
  const payload = canonicalStringify(worldToDict(world));
  return sha256Hex(new TextEncoder().encode(payload));
}

// ---------------------------------------------------------------------------
// Economy (genesis/economy.py)
// ---------------------------------------------------------------------------

export function dailyWeather(config, rng) {
  const weather = {};
  for (const r of RESOURCES) weather[r] = rng.randint(config.weather_min_pct, config.weather_max_pct);
  return weather;
}

export function productionOutput(resident, config, weatherPct, rng) {
  const occupation = resident.occupation;
  const vitalityPct = 75 + floorDiv(resident.health, 4);
  const expectedMilli = floorDiv(
    config.base_output[occupation] * resident.skills[occupation] * vitalityPct * weatherPct,
    1000,
  );
  const [whole, fraction] = divmod(expectedMilli, 1000);
  return whole + (rng.randrange(1000) < fraction ? 1 : 0);
}

export function consumeNeeds(resident, config, rested) {
  const consumed = {};
  const unmet = {};
  let change = 0;
  for (const resource of RESOURCES) {
    const need = config.daily_needs[resource];
    const used = Math.min(need, resident.inventory[resource]);
    resident.inventory[resource] -= used;
    consumed[resource] = used;
    unmet[resource] = need - used;
    change -= unmet[resource] * config.unmet_need_penalty[resource];
  }
  if (!RESOURCES.some((r) => unmet[r] !== 0)) change += config.health_recovery;
  if (rested) change += config.rest_recovery;
  const before = resident.health;
  resident.health = Math.max(0, Math.min(MAX_HEALTH, before + change));
  return { consumed, unmet, health_before: before, health_after: resident.health };
}

export function parseOrder(request, config) {
  const side = request.side;
  const resource = request.resource;
  if (side !== "buy" && side !== "sell") return "malformed_order";
  if (!RESOURCES.includes(resource)) return "malformed_order";
  const quantity = request.quantity;
  const price = request.limit_price;
  if (!Number.isInteger(quantity) || !(1 <= quantity && quantity <= config.max_order_quantity)) {
    return "invalid_quantity";
  }
  if (!Number.isInteger(price) || !(config.min_price <= price && price <= config.max_price)) {
    return "invalid_price";
  }
  return [side, resource, quantity, price];
}

export function describeOrder(request) {
  return {
    side: request.side,
    resource: request.resource,
    quantity: request.quantity,
    limit_price: request.limit_price,
  };
}

export function validateOrders(submissions, config) {
  const accepted = [];
  const rejected = [];
  for (const [resident, requests] of submissions) {
    let cashReserved = 0;
    const goodsReserved = resMap(0, 0, 0);
    const sides = {};
    for (const request of requests.slice(0, config.max_orders_per_day)) {
      const parsed = parseOrder(request, config);
      let reason = null;
      if (typeof parsed === "string") {
        reason = parsed;
      } else {
        const [side, resource, quantity, price] = parsed;
        if ((resource in sides ? sides[resource] : side) !== side) {
          reason = "self_cross";
        } else if (side === "buy" && cashReserved + quantity * price > resident.cash) {
          reason = "insufficient_funds";
        } else if (side === "sell" && goodsReserved[resource] + quantity > resident.inventory[resource]) {
          reason = "insufficient_inventory";
        } else {
          if (side === "buy") cashReserved += quantity * price;
          else goodsReserved[resource] += quantity;
          sides[resource] = side;
          accepted.push({
            seq: accepted.length + 1,
            resident_id: resident.id,
            side,
            resource,
            quantity,
            limit_price: price,
          });
          continue;
        }
      }
      rejected.push({ resident_id: resident.id, reason, order: describeOrder(request) });
    }
    const excess = requests.length - config.max_orders_per_day;
    if (excess > 0) {
      rejected.push({ resident_id: resident.id, reason: "too_many_orders", order: { excess_orders: excess } });
    }
  }
  return [accepted, rejected];
}

export function clearAuction(resource, orders, referencePrice) {
  const bids = orders.filter((o) => o.resource === resource && o.side === "buy");
  const asks = orders.filter((o) => o.resource === resource && o.side === "sell");
  const demand = bids.reduce((s, o) => s + o.quantity, 0);
  const supply = asks.reduce((s, o) => s + o.quantity, 0);
  const bestBid = bids.length ? Math.max(...bids.map((o) => o.limit_price)) : null;
  const bestAsk = asks.length ? Math.min(...asks.map((o) => o.limit_price)) : null;
  if (bestBid === null || bestAsk === null || bestBid < bestAsk) {
    return {
      resource, clearing_price: null, demand, supply, volume: 0,
      trades: [], best_bid: bestBid, best_ask: bestAsk,
    };
  }
  const price = clearingPrice(bids, asks, referencePrice);
  const buyers = bids
    .filter((o) => o.limit_price >= price)
    .sort((a, b) => (b.limit_price - a.limit_price) || (a.seq - b.seq));
  const sellers = asks
    .filter((o) => o.limit_price <= price)
    .sort((a, b) => (a.limit_price - b.limit_price) || (a.seq - b.seq));
  const volume = Math.min(
    buyers.reduce((s, o) => s + o.quantity, 0),
    sellers.reduce((s, o) => s + o.quantity, 0),
  );
  const trades = matchTrades(resource, price, allocate(buyers, volume), allocate(sellers, volume));
  return {
    resource, clearing_price: price, demand, supply, volume,
    trades, best_bid: bestBid, best_ask: bestAsk,
  };
}

function clearingPrice(bids, asks, referencePrice) {
  const candidates = [...new Set([
    ...bids.map((o) => o.limit_price),
    ...asks.map((o) => o.limit_price),
    referencePrice,
  ])].sort((a, b) => a - b);
  let scored = [];
  for (const price of candidates) {
    const demand = bids.filter((o) => o.limit_price >= price).reduce((s, o) => s + o.quantity, 0);
    const supply = asks.filter((o) => o.limit_price <= price).reduce((s, o) => s + o.quantity, 0);
    if (Math.min(demand, supply) > 0) scored.push([price, Math.min(demand, supply), demand - supply]);
  }
  const bestVolume = Math.max(...scored.map((s) => s[1]));
  scored = scored.filter((s) => s[1] === bestVolume);
  const leastImbalance = Math.min(...scored.map((s) => Math.abs(s[2])));
  scored = scored.filter((s) => Math.abs(s[2]) === leastImbalance);
  if (scored.every((s) => s[2] > 0)) return Math.max(...scored.map((s) => s[0]));
  if (scored.every((s) => s[2] < 0)) return Math.min(...scored.map((s) => s[0]));
  return minByFirst(scored, (s) => [Math.abs(s[0] - referencePrice), s[0]])[0];
}

function allocate(orders, volume) {
  const fills = [];
  let remaining = volume;
  let index = 0;
  while (remaining > 0 && index < orders.length) {
    const price = orders[index].limit_price;
    const level = [];
    while (index < orders.length && orders[index].limit_price === price) {
      level.push(orders[index]);
      index++;
    }
    const levelQuantity = level.reduce((s, o) => s + o.quantity, 0);
    if (levelQuantity <= remaining) {
      for (const o of level) fills.push([o, o.quantity]);
      remaining -= levelQuantity;
      continue;
    }
    const shares = new Map();
    for (const o of level) shares.set(o.seq, floorDiv(o.quantity * remaining, levelQuantity));
    const leftover = remaining - [...shares.values()].reduce((a, b) => a + b, 0);
    const bySeq = [...level].sort((a, b) => a.seq - b.seq);
    for (const o of bySeq.slice(0, leftover)) shares.set(o.seq, shares.get(o.seq) + 1);
    for (const o of level) {
      const sh = shares.get(o.seq);
      if (sh > 0) fills.push([o, sh]);
    }
    remaining = 0;
  }
  return fills;
}

function matchTrades(resource, price, buys, sells) {
  const trades = [];
  let b = 0, s = 0;
  let buyLeft = buys.length ? buys[0][1] : 0;
  let sellLeft = sells.length ? sells[0][1] : 0;
  while (b < buys.length && s < sells.length) {
    const quantity = Math.min(buyLeft, sellLeft);
    trades.push({ resource, buyer_id: buys[b][0].resident_id, seller_id: sells[s][0].resident_id, quantity, price });
    buyLeft -= quantity;
    sellLeft -= quantity;
    if (buyLeft === 0) { b++; buyLeft = b < buys.length ? buys[b][1] : 0; }
    if (sellLeft === 0) { s++; sellLeft = s < sells.length ? sells[s][1] : 0; }
  }
  return trades;
}

export function settleTrades(trades, residentsById) {
  for (const trade of trades) {
    const buyer = residentsById[trade.buyer_id];
    const seller = residentsById[trade.seller_id];
    const value = trade.quantity * trade.price;
    buyer.cash -= value;
    seller.cash += value;
    seller.inventory[trade.resource] -= trade.quantity;
    buyer.inventory[trade.resource] += trade.quantity;
  }
}

function raisePrice(price, stepBps) {
  if (stepBps === 0) return price;
  return Math.max(price + 1, ceilDiv(price * (BPS + stepBps), BPS));
}

function lowerPrice(price, stepBps) {
  if (stepBps === 0) return price;
  return Math.min(price - 1, floorDiv(price * (BPS - stepBps), BPS));
}

export function nextReferencePrice(previous, result, config) {
  const step = config.no_trade_price_step_bps;
  let price;
  if (result.clearing_price !== null) {
    price = result.clearing_price;
  } else if (result.demand > 0 && result.supply === 0) {
    price = raisePrice(previous, step);
  } else if (result.supply > 0 && result.demand === 0) {
    price = lowerPrice(previous, step);
  } else if (result.best_bid !== null && result.best_ask !== null) {
    const midpoint = floorDiv(result.best_bid + result.best_ask, 2);
    price = Math.max(lowerPrice(previous, step), Math.min(raisePrice(previous, step), midpoint));
  } else {
    price = previous;
  }
  return Math.max(config.min_price, Math.min(config.max_price, price));
}

export function gini(values) {
  const count = values.length;
  const total = values.reduce((a, b) => a + b, 0);
  if (count === 0 || total === 0) return 0.0;
  const sorted = [...values].sort((a, b) => a - b);
  let weighted = 0;
  for (let i = 0; i < sorted.length; i++) weighted += (i + 1) * sorted[i];
  return (2 * weighted) / (count * total) - (count + 1) / count;
}

function medianOfSorted(ranked) {
  const n = ranked.length;
  if (n % 2 === 1) return ranked[(n - 1) / 2];
  return (ranked[n / 2 - 1] + ranked[n / 2]) / 2;
}

export function summarizeWealth(values) {
  if (values.length === 0) {
    return {
      count: 0, total: 0, mean: 0.0, median: 0.0, minimum: 0, maximum: 0,
      gini: 0.0, top_10_share: 0.0, bottom_50_share: 0.0,
    };
  }
  const ranked = [...values].sort((a, b) => a - b);
  const count = ranked.length;
  const total = ranked.reduce((a, b) => a + b, 0);
  const top = ranked.slice(-Math.max(1, ceilDiv(count, 10)));
  const bottom = ranked.slice(0, Math.floor(count / 2));
  const sumTop = top.reduce((a, b) => a + b, 0);
  const sumBottom = bottom.reduce((a, b) => a + b, 0);
  return {
    count,
    total,
    mean: pyRound(total / count, 2),
    median: pyRound(medianOfSorted(ranked), 2),
    minimum: ranked[0],
    maximum: ranked[count - 1],
    gini: pyRound(gini(ranked), 4),
    top_10_share: total ? pyRound(sumTop / total, 4) : 0.0,
    bottom_50_share: total ? pyRound(sumBottom / total, 4) : 0.0,
  };
}

// ---------------------------------------------------------------------------
// Agents (genesis/agents.py): estimates + the RuleBasedAgent policy.
// ---------------------------------------------------------------------------

export const AGENT_PARAMS = {
  buffer_days: 5,
  overstock_days: 20,
  anchor_days: 10,
  floor_pct: 90,
  review_interval_days: 7,
  switch_margin_pct: 5,
  urgent_premium_bps: 1500,
  low_premium_bps: 600,
  normal_premium_bps: 200,
  discount_bps: 100,
  surplus_discount_bps: 300,
  glut_discount_bps: 600,
  max_markup_bps: 500,
};

export function livingCost(observation) {
  const rules = observation.rules;
  return RESOURCES.reduce((s, r) => s + rules.daily_needs[r] * observation.market[r].price, 0);
}

export function workersNeeded(observation, occupation) {
  const rules = observation.rules;
  const output = rules.base_output[occupation];
  if (output === 0) return 0;
  const demand = rules.daily_needs[rules.products[occupation]] * observation.population;
  return ceilDiv(demand, output);
}

export function expectedSales(observation, occupation) {
  const rules = observation.rules;
  const product = rules.products[occupation];
  const producers = Math.max(1, observation.census[occupation] + (occupation === observation.occupation ? 0 : 1));
  const need = rules.daily_needs[product] * 100;
  const surplus = Math.max(0, rules.base_output[occupation] * observation.skills[occupation] - need);
  const share = floorDiv(
    rules.daily_needs[product] * Math.max(0, observation.population - producers) * 100,
    producers,
  );
  return Math.min(surplus, share);
}

export function expectedIncome(observation, occupation) {
  const product = observation.rules.products[occupation];
  return expectedSales(observation, occupation) * observation.market[product].price;
}

export function breakEvenPrice(observation, occupation) {
  const rules = observation.rules;
  const product = rules.products[occupation];
  let expenses = 0;
  for (const r of RESOURCES) {
    if (r !== product) expenses += rules.daily_needs[r] * observation.market[r].price;
  }
  return ceilDiv(expenses * 100, Math.max(1, expectedSales(observation, occupation)));
}

export function moneyCoverDays(observation) {
  return floorDiv(observation.money_supply, Math.max(1, observation.population * livingCost(observation)));
}

function bounded(price, observation) {
  return Math.max(observation.rules.min_price, Math.min(observation.rules.max_price, price));
}

function reviewOccupation(observation, p) {
  if (!observation.can_change_occupation) return null;
  if ((observation.day + observation.resident_id) % p.review_interval_days !== 0) return null;
  const current = observation.occupation;
  const census = observation.census;
  if (census[current] <= workersNeeded(observation, current)) return null;
  const shortfall = {};
  const income = {};
  for (const occ of OCCUPATIONS) {
    shortfall[occ] = workersNeeded(observation, occ) - census[occ];
    income[occ] = expectedIncome(observation, occ);
  }
  const understaffed = OCCUPATIONS.filter((occ) => shortfall[occ] > 0);
  if (understaffed.length) {
    return maxByFirst(understaffed, (occ) => [shortfall[occ], income[occ]]);
  }
  const best = maxByFirst(OCCUPATIONS, (occ) => income[occ]);
  if (income[best] - income[current] > p.switch_margin_pct * livingCost(observation)) return best;
  return null;
}

function buyOrders(observation, product, p) {
  const rules = observation.rules;
  // Most damaging unmet need first; the sort is stable, ties keep canonical order.
  const sorted = [...RESOURCES].sort(
    (a, b) => rules.unmet_need_penalty[b] - rules.unmet_need_penalty[a],
  );
  const wanted = [];
  for (const resource of sorted) {
    if (resource === product) continue;
    const need = rules.daily_needs[resource];
    const stock = observation.inventory[resource];
    const target = need * p.buffer_days;
    if (stock >= target) continue;
    let premium;
    if (stock < need) premium = p.urgent_premium_bps;
    else if (stock * 2 < target) premium = p.low_premium_bps;
    else premium = p.normal_premium_bps;
    const limit = bounded(ceilDiv(observation.market[resource].price * (BPS + premium), BPS), observation);
    wanted.push({ resource, limit, shortfall: Math.max(0, need - stock), gap: target - stock });
  }
  // Budget in two passes: first today's needs of every resource, then buffers.
  let budget = observation.cash;
  const quantities = {};
  for (const passIndex of [0, 1]) {
    for (const w of wanted) {
      const have = quantities[w.resource] ?? 0;
      const goal = passIndex === 0 ? w.shortfall : w.gap;
      const quantity = Math.max(
        0,
        Math.min(goal - have, floorDiv(budget, w.limit), rules.max_order_quantity - have),
      );
      quantities[w.resource] = have + quantity;
      budget -= quantity * w.limit;
    }
  }
  return wanted
    .filter((w) => (quantities[w.resource] ?? 0) > 0)
    .map((w) => ({
      side: "buy",
      resource: w.resource,
      quantity: quantities[w.resource],
      limit_price: w.limit,
    }));
}

function sellOrders(observation, occupation, p) {
  const rules = observation.rules;
  const product = rules.products[occupation];
  const pricesHigh = moneyCoverDays(observation) < p.anchor_days;
  const floor = floorDiv(breakEvenPrice(observation, occupation) * p.floor_pct, 100);
  const orders = [];
  for (const resource of RESOURCES) {
    const stock = observation.inventory[resource];
    const target = rules.daily_needs[resource] * p.buffer_days;
    let quantity;
    if (resource === product) {
      const pace = Math.max(1, floorDiv(rules.base_output[occupation] * observation.skills[occupation], 100));
      quantity = Math.min(stock - target, pace);
    } else if (stock > 2 * target) {
      quantity = stock - target;
    } else {
      continue;
    }
    if (quantity <= 0) continue;
    const reference = observation.market[resource].price;
    let discount;
    if (!pricesHigh) discount = 0;
    else if (stock >= 3 * target) discount = p.glut_discount_bps;
    else if (stock >= 2 * target) discount = p.surplus_discount_bps;
    else discount = p.discount_bps;
    let limit = floorDiv(reference * (BPS - discount), BPS);
    if (resource === product) {
      const ceiling = floorDiv(reference * (BPS + p.max_markup_bps), BPS);
      limit = Math.max(limit, Math.min(floor, ceiling));
    }
    quantity = Math.min(quantity, rules.max_order_quantity);
    orders.push({ side: "sell", resource, quantity, limit_price: bounded(limit, observation) });
  }
  return orders;
}

export function ruleBasedDecide(observation, params = AGENT_PARAMS) {
  const newOccupation = reviewOccupation(observation, params);
  const occupation = newOccupation === null ? observation.occupation : newOccupation;
  const product = observation.rules.products[occupation];
  const orders = [...buyOrders(observation, product, params), ...sellOrders(observation, occupation, params)];
  const overstock = Math.max(1, observation.rules.daily_needs[product] * params.overstock_days);
  return {
    activity: observation.inventory[product] >= overstock ? "rest" : "work",
    orders,
    new_occupation: newOccupation,
  };
}

// ---------------------------------------------------------------------------
// Simulation (genesis/simulation.py)
// ---------------------------------------------------------------------------

export function occupationCensus(residents) {
  const census = occMap(0, 0, 0);
  for (const r of residents) census[r.occupation]++;
  return census;
}

export function rulesFromConfig(config) {
  return {
    daily_needs: config.daily_needs,
    unmet_need_penalty: config.unmet_need_penalty,
    health_recovery: config.health_recovery,
    rest_recovery: config.rest_recovery,
    base_output: config.base_output,
    products: PRODUCT,
    min_price: config.min_price,
    max_price: config.max_price,
    max_orders_per_day: config.max_orders_per_day,
    max_order_quantity: config.max_order_quantity,
    occupation_cooldown_days: config.occupation_cooldown_days,
  };
}

export function buildObservation(world, resident, rules, population, census) {
  const lastChange = resident.last_occupation_change;
  return {
    day: world.day,
    resident_id: resident.id,
    name: resident.name,
    occupation: resident.occupation,
    can_change_occupation:
      lastChange === null || world.day - lastChange >= rules.occupation_cooldown_days,
    health: resident.health,
    cash: resident.cash,
    inventory: { ...resident.inventory },
    skills: { ...resident.skills },
    market: Object.fromEntries(RESOURCES.map((r) => [r, { ...world.market[r] }])),
    population,
    census: { ...census },
    money_supply: world.ledger.money_supply,
    rules,
  };
}

function decide(world, resident, rules, population, census) {
  const observation = buildObservation(world, resident, rules, population, census);
  return ruleBasedDecide(observation);
}

function changeOccupation(world, resident, requested) {
  if (requested === null || requested === undefined) return;
  const lastChange = resident.last_occupation_change;
  if (requested === resident.occupation) {
    record(world, "action_rejected", resident.id, null, {
      action: "change_occupation",
      reason: "already_in_occupation",
      value: `'${requested}'`,
    });
    return;
  }
  if (lastChange !== null && world.day - lastChange < world.config.occupation_cooldown_days) {
    record(world, "action_rejected", resident.id, null, {
      action: "change_occupation",
      reason: "occupation_cooldown",
      value: `'${requested}'`,
    });
    return;
  }
  record(world, "occupation_changed", resident.id, null, {
    previous: resident.occupation,
    occupation: requested,
  });
  resident.occupation = requested;
  resident.last_occupation_change = world.day;
}

function produce(world, livingList, decisions) {
  const weather = dailyWeather(world.config, deriveRng(world.seed, world.day, "weather"));
  const rng = deriveRng(world.seed, world.day, "production");
  const produced = resMap(0, 0, 0);
  let workers = 0;
  for (const resident of livingList) {
    if (decisions.get(resident.id).activity !== "work") continue;
    workers++;
    const resource = PRODUCT[resident.occupation];
    const quantity = productionOutput(resident, world.config, weather[resource], rng);
    resident.inventory[resource] += quantity;
    world.ledger.produced[resource] += quantity;
    produced[resource] += quantity;
    record(world, "production", resident.id, null, {
      resource,
      quantity,
      occupation: resident.occupation,
    });
  }
  return [produced, workers];
}

function tradePhase(world, livingList, decisions) {
  const arrival = [...livingList];
  deriveRng(world.seed, world.day, "market").shuffle(arrival);
  const [orders, rejections] = validateOrders(
    arrival.map((resident) => [resident, decisions.get(resident.id).orders]),
    world.config,
  );
  for (const rejection of rejections) {
    record(world, "order_rejected", rejection.resident_id, null, {
      reason: rejection.reason,
      order: rejection.order,
    });
  }
  const residentsById = {};
  for (const r of world.residents) residentsById[r.id] = r;
  const results = [];
  for (const resource of RESOURCES) {
    const quote = world.market[resource];
    const result = clearAuction(resource, orders, quote.price);
    settleTrades(result.trades, residentsById);
    for (const t of result.trades) {
      record(world, "trade", t.buyer_id, t.seller_id, {
        resource,
        quantity: t.quantity,
        price: t.price,
        value: t.quantity * t.price,
      });
    }
    const previous = quote.price;
    quote.price = nextReferencePrice(previous, result, world.config);
    quote.demand = result.demand;
    quote.supply = result.supply;
    quote.volume = result.volume;
    record(world, "market_cleared", null, null, {
      resource,
      previous_price: previous,
      price: quote.price,
      clearing_price: result.clearing_price,
      demand: result.demand,
      supply: result.supply,
      volume: result.volume,
      value: result.trades.reduce((s, t) => s + t.quantity * t.price, 0),
      trades: result.trades.length,
      best_bid: result.best_bid,
      best_ask: result.best_ask,
    });
    results.push(result);
  }
  return [results, rejections.length];
}

function consumePhase(world, livingList, decisions) {
  const consumed = resMap(0, 0, 0);
  const unmet = resMap(0, 0, 0);
  let deaths = 0;
  for (const resident of livingList) {
    const rested = decisions.get(resident.id).activity === "rest";
    const outcome = consumeNeeds(resident, world.config, rested);
    for (const resource of RESOURCES) {
      world.ledger.consumed[resource] += outcome.consumed[resource];
      consumed[resource] += outcome.consumed[resource];
      unmet[resource] += outcome.unmet[resource];
    }
    record(world, "consumption", resident.id, null, {
      consumed: { ...outcome.consumed },
      unmet: { ...outcome.unmet },
      health_before: outcome.health_before,
      health_after: outcome.health_after,
      rested,
    });
    if (outcome.health_after === 0) {
      resident.alive = false;
      resident.died_on = world.day;
      deaths++;
      record(world, "resident_died", resident.id, null, {
        cause: "unmet_needs",
        estate_cash: resident.cash,
        estate_inventory: { ...resident.inventory },
      });
    }
  }
  return [consumed, unmet, deaths];
}

function redistribute(world, livingList, taxRateBps) {
  if (taxRateBps <= 0 || livingList.length === 0) return;
  const taxes = {};
  for (const resident of livingList) taxes[resident.id] = floorDiv(resident.cash * taxRateBps, 10000);
  const pool = livingList.reduce((s, r) => s + taxes[r.id], 0);
  const [share, remainder] = divmod(pool, livingList.length);
  livingList.forEach((resident, index) => {
    const rebate = share + (index < remainder ? 1 : 0);
    resident.cash += rebate - taxes[resident.id];
    record(world, "tax", resident.id, null, {
      tax_paid: taxes[resident.id],
      rebate,
    });
  });
}

function dailyStats(world, args) {
  const livingList = living(world);
  const byResource = {};
  for (const result of args.results) byResource[result.resource] = result;
  const wealth = livingList.map((r) => residentWealth(world, r));
  return {
    day: world.day,
    population: livingList.length,
    deaths: args.deaths,
    working: args.workers,
    resting: args.started - args.workers,
    occupations: occupationCensus(livingList),
    prices: prices(world),
    production: { ...args.produced },
    consumption: { ...args.consumed },
    unmet_needs: { ...args.unmet },
    demand: Object.fromEntries(RESOURCES.map((r) => [r, byResource[r].demand])),
    supply: Object.fromEntries(RESOURCES.map((r) => [r, byResource[r].supply])),
    trade_volume: Object.fromEntries(RESOURCES.map((r) => [r, byResource[r].volume])),
    trade_value: Object.fromEntries(
      RESOURCES.map((r) => [r, byResource[r].trades.reduce((s, t) => s + t.quantity * t.price, 0)]),
    ),
    trade_count: args.results.reduce((s, result) => s + result.trades.length, 0),
    rejected_orders: args.rejectedOrders,
    holdings: holdings(world, false),
    money_supply: totalCash(world),
    mean_health: new PyFloat(
      livingList.length
        ? pyRound(livingList.reduce((s, r) => s + r.health, 0) / livingList.length, 2)
        : 0.0,
    ),
    total_wealth: wealth.reduce((a, b) => a + b, 0),
    gini: new PyFloat(pyRound(gini(wealth), 4)),
  };
}

export class Simulation {
  constructor(world, taxRateBps = 0) {
    this.world = world;
    this.rules = rulesFromConfig(world.config);
    this.taxRateBps = taxRateBps;
  }

  step() {
    const world = this.world;
    world.day += 1;
    const livingList = living(world);
    const census = occupationCensus(livingList);
    const decisions = new Map();
    for (const resident of livingList) {
      decisions.set(resident.id, decide(world, resident, this.rules, livingList.length, census));
    }
    for (const resident of livingList) {
      changeOccupation(world, resident, decisions.get(resident.id).new_occupation);
    }
    const [produced, workers] = produce(world, livingList, decisions);
    const [results, rejectedOrders] = tradePhase(world, livingList, decisions);
    const [consumed, unmet, deaths] = consumePhase(world, livingList, decisions);
    redistribute(world, living(world), this.taxRateBps);
    const stats = dailyStats(world, {
      started: livingList.length,
      workers,
      produced,
      consumed,
      unmet,
      results,
      rejectedOrders,
      deaths,
    });
    world.stats.push(stats);
    return stats;
  }

  run(days) {
    const out = [];
    for (let i = 0; i < days; i++) out.push(this.step());
    return out;
  }
}

// ---------------------------------------------------------------------------
// Reporting (genesis/reporting.py): play_summary / world_summary
// ---------------------------------------------------------------------------

export function tradeTotals(world) {
  const units = resMap(0, 0, 0);
  const value = resMap(0, 0, 0);
  let count = 0;
  for (const stats of world.stats) {
    count += stats.trade_count;
    for (const resource of RESOURCES) {
      units[resource] += stats.trade_volume[resource];
      value[resource] += stats.trade_value[resource];
    }
  }
  return {
    trades: count,
    units: units.food + units.wood + units.stone,
    value: value.food + value.wood + value.stone,
    units_by_resource: { ...units },
    value_by_resource: { ...value },
  };
}

export function worldSummary(world, digest = null) {
  const livingList = living(world);
  const estates = world.residents.filter((r) => !r.alive);
  const allHoldings = holdings(world, false);
  const livingHoldings = holdings(world, true);
  return {
    day: world.day,
    seed: world.seed,
    population: { alive: livingList.length, dead: estates.length, total: world.residents.length },
    occupations: Object.fromEntries(
      OCCUPATIONS.map((occ) => [occ, livingList.filter((r) => r.occupation === occ).length]),
    ),
    prices: prices(world),
    holdings: {
      total: { ...allHoldings },
      living: { ...livingHoldings },
      estates: Object.fromEntries(RESOURCES.map((r) => [r, allHoldings[r] - livingHoldings[r]])),
    },
    money_supply: world.ledger.money_supply,
    cash: {
      living: livingList.reduce((s, r) => s + r.cash, 0),
      estates: estates.reduce((s, r) => s + r.cash, 0),
    },
    produced: { ...world.ledger.produced },
    consumed: { ...world.ledger.consumed },
    trades: tradeTotals(world),
    mean_health: livingList.length
      ? pyRound(livingList.reduce((s, r) => s + r.health, 0) / livingList.length, 2)
      : 0.0,
    wealth: summarizeWealth(livingList.map((r) => residentWealth(world, r))),
    events: world.events.length,
    state_digest: digest === null ? stateDigest(world) : digest,
  };
}

export function playSummary(world, taxRateBps = 0) {
  // The digest is computed once and shared with the final summary (which
  // carries the same state_digest); computing it twice would double the
  // most expensive step of a long run.
  const digest = stateDigest(world);
  const step = Math.max(1, floorDiv(world.day, 10));
  const trajectory = world.stats
    .filter((s) => s.day % step === 0 || s.day === world.day)
    .map((s) => ({
      day: s.day,
      population: s.population,
      deaths: s.deaths,
      prices: { ...s.prices },
      trades: s.trade_count,
      units: RESOURCES.reduce((a, r) => a + s.trade_volume[r], 0),
      value: RESOURCES.reduce((a, r) => a + s.trade_value[r], 0),
      health: unwrap(s.mean_health),
      gini: unwrap(s.gini),
    }));
  const residents = [...living(world)]
    .sort((a, b) => residentWealth(world, b) - residentWealth(world, a))
    .map((r) => ({
      id: r.id,
      name: r.name,
      occupation: r.occupation,
      health: r.health,
      cash: r.cash,
      inventory: { ...r.inventory },
      wealth: residentWealth(world, r),
    }));
  return {
    config: configToDict(world.config),
    policy: {
      tax_rate_bps: taxRateBps,
      max_orders_per_day: world.config.max_orders_per_day,
    },
    seed: world.seed,
    days: world.day,
    digest,
    invariants: "OK",
    trajectory,
    final: worldSummary(world, digest),
    residents,
  };
}

// ---------------------------------------------------------------------------
// Public entry point
// ---------------------------------------------------------------------------

export function runWorld({ seed = 42, days = 100, residents = 20, taxBps = 0, maxOrders = 10 } = {}) {
  const config = defaultConfig();
  config.num_residents = residents;
  config.max_orders_per_day = maxOrders;
  const world = createWorld(config, seed);
  new Simulation(world, taxBps).run(days);
  return playSummary(world, taxBps);
}

// ---------------------------------------------------------------------------
// Epochs and play-money betting — the JS mirror of genesis/epoch.py and
// genesis/betting.py. Same rules, same integer cents, same digests.
//
// Rounding rule (pinned down once, shared by both ports): every amount is
// an integer number of cents; parimutuel shares use floor division
// (floorDiv) and the leftover cents — always fewer than the number of
// winning bets — go one cent each to the earliest winning bets in
// placement order, so payouts always sum to exactly the pool. The epoch
// digest payload contains only integers and strings (no floats), so
// canonicalStringify matches Python json.dumps(sort_keys=True,
// separators=(",", ":")) bit-for-bit. The winner tiebreak compares
// SHA-256 hex strings, which is a numeric comparison for equal-length hex.
// Play money is labelled PLAY_MONEY_LABEL everywhere it surfaces.
// ---------------------------------------------------------------------------

export const CIV_NAMES = ["Aurora", "Boreas", "Cinder", "Dune"];
export const EPOCH_MIN_DAYS = 30;
export const EPOCH_MAX_DAYS = 90;
export const EPOCH_MIN_CIVS = 2;
export const EPOCH_MAX_CIVS = CIV_NAMES.length;
export const EPOCH_DEFAULT_DAYS = 60;
export const EPOCH_DEFAULT_CIVS = 4;
export const EPOCH_DEFAULT_RESIDENTS_PER_CIV = 5;
export const EPOCH_MAX_SEED = 1e9;
export const PLAY_MONEY_CURRENCY = "play_credits";
export const PLAY_MONEY_LABEL = "演示积分 · 不是真钱";

export function civSeed(epochSeed, civIndex) {
  return epochSeed * 1000 + civIndex;
}

export function epochIdFor(seed, days, numCivs, residentsPerCiv, taxRateBps, maxOrdersPerDay) {
  return `epoch:${seed}:${days}:${numCivs}:${residentsPerCiv}:${taxRateBps}:${maxOrdersPerDay}`;
}

export function survivalScore(alive, wealthCents, totalHealth) {
  return alive * 1000000 + wealthCents + totalHealth * 100;
}

export function epochDigest(payload) {
  return sha256Hex(new TextEncoder().encode(canonicalStringify(payload)));
}

function winnerTiebreakHash(epochDigestHex, civId) {
  return sha256Hex(new TextEncoder().encode(`genesis:epoch-winner:${epochDigestHex}:${civId}`));
}

// scores: [{ civ, score }, ...]; pure function of the scores + epoch digest.
// Highest score wins; ties go to the smallest tiebreak hash (see Python).
export function deriveWinner(scores, epochDigestHex) {
  if (typeof epochDigestHex !== "string" || !/^[0-9a-f]{64}$/.test(epochDigestHex)) {
    throw new Error(`epochDigest must be a 64-hex string, got ${JSON.stringify(epochDigestHex)}`);
  }
  if (!Array.isArray(scores) || scores.length === 0) {
    throw new Error("scores must not be empty");
  }
  const ids = scores.map((s) => s.civ);
  if (new Set(ids).size !== ids.length) {
    throw new Error(`duplicate civilization ids in scores: ${JSON.stringify(ids)}`);
  }
  for (const s of scores) {
    if (!Number.isInteger(s.civ) || !Number.isInteger(s.score)) {
      throw new Error(`scores must be {civ, score} integer pairs, got ${JSON.stringify(s)}`);
    }
  }
  const best = Math.max(...scores.map((s) => s.score));
  const tied = scores.filter((s) => s.score === best).map((s) => s.civ);
  if (tied.length === 1) return tied[0];
  let winner = tied[0];
  let winnerHash = winnerTiebreakHash(epochDigestHex, winner);
  for (const civ of tied.slice(1)) {
    const hash = winnerTiebreakHash(epochDigestHex, civ);
    if (hash < winnerHash) { winner = civ; winnerHash = hash; }
  }
  return winner;
}

function validateEpochParams(seed, days, numCivs, residentsPerCiv, taxRateBps, maxOrdersPerDay) {
  if (!Number.isInteger(seed) || Math.abs(seed) > EPOCH_MAX_SEED) {
    throw new Error(`seed must be an integer with |seed| <= ${EPOCH_MAX_SEED}, got ${seed}`);
  }
  if (!Number.isInteger(days) || days < EPOCH_MIN_DAYS || days > EPOCH_MAX_DAYS) {
    throw new Error(`days must be ${EPOCH_MIN_DAYS}..${EPOCH_MAX_DAYS}, got ${days}`);
  }
  if (!Number.isInteger(numCivs) || numCivs < EPOCH_MIN_CIVS || numCivs > EPOCH_MAX_CIVS) {
    throw new Error(`numCivs must be ${EPOCH_MIN_CIVS}..${EPOCH_MAX_CIVS}, got ${numCivs}`);
  }
  if (!Number.isInteger(residentsPerCiv) || residentsPerCiv < 1 || residentsPerCiv > 20) {
    throw new Error(`residentsPerCiv must be 1..20, got ${residentsPerCiv}`);
  }
  if (!Number.isInteger(taxRateBps) || taxRateBps < 0 || taxRateBps > 10000) {
    throw new Error(`taxRateBps must be 0..10000, got ${taxRateBps}`);
  }
  if (!Number.isInteger(maxOrdersPerDay) || maxOrdersPerDay < 0 || maxOrdersPerDay > 10) {
    throw new Error(`maxOrdersPerDay must be 0..10, got ${maxOrdersPerDay}`);
  }
}

// Run one epoch: numCivs parallel mini-worlds, one winner. Returns the
// same JSON-ready object as Python genesis.epoch.run_epoch.
export function runEpoch({
  seed = 42,
  days = EPOCH_DEFAULT_DAYS,
  civs = EPOCH_DEFAULT_CIVS,
  residentsPerCiv = EPOCH_DEFAULT_RESIDENTS_PER_CIV,
  taxBps = 0,
  maxOrders = 10,
} = {}) {
  validateEpochParams(seed, days, civs, residentsPerCiv, taxBps, maxOrders);
  const civResults = [];
  for (let civId = 0; civId < civs; civId++) {
    const summary = runWorld({
      seed: civSeed(seed, civId),
      days,
      residents: residentsPerCiv,
      taxBps,
      maxOrders,
    });
    const alive = summary.final.population.alive;
    const wealth = summary.residents.reduce((s, r) => s + r.wealth, 0);
    const health = summary.residents.reduce((s, r) => s + r.health, 0);
    civResults.push({
      id: civId,
      name: CIV_NAMES[civId],
      seed: civSeed(seed, civId),
      digest: summary.digest,
      alive,
      wealth,
      health,
      score: survivalScore(alive, wealth, health),
      trades: summary.final.trades.trades,
      units: summary.final.trades.units,
      value: summary.final.trades.value,
    });
  }
  const payload = {
    epoch_id: epochIdFor(seed, days, civs, residentsPerCiv, taxBps, maxOrders),
    seed,
    days,
    num_civs: civs,
    residents_per_civ: residentsPerCiv,
    tax_rate_bps: taxBps,
    max_orders_per_day: maxOrders,
    civs: civResults,
  };
  const digest = epochDigest(payload);
  const winner = deriveWinner(civResults.map((c) => ({ civ: c.id, score: c.score })), digest);
  return {
    ...payload,
    currency: PLAY_MONEY_CURRENCY,
    play_money_note: PLAY_MONEY_LABEL,
    digest,
    winner,
    winner_name: CIV_NAMES[winner],
  };
}

// --- betting (mirror of genesis/betting.py) ---------------------------------

function isIntLike(v) {
  return typeof v === "number" && Number.isInteger(v);
}

// bets: [{ player, civ, amount, epoch_id }, ...]. Returns a NEW array.
export function placeBet(bets, { player, civ, amount, epochId, validCivs }) {
  if (typeof player !== "string" || !player.trim()) {
    throw new Error(`player must be a non-empty string, got ${JSON.stringify(player)}`);
  }
  if (!isIntLike(civ) || !validCivs.includes(civ)) {
    throw new Error(`civ must be one of ${JSON.stringify(validCivs)}, got ${JSON.stringify(civ)}`);
  }
  if (!isIntLike(amount) || amount <= 0) {
    throw new Error(`amount must be a positive integer (cents), got ${JSON.stringify(amount)}`);
  }
  if (typeof epochId !== "string" || !epochId) {
    throw new Error(`epochId must be a non-empty string, got ${JSON.stringify(epochId)}`);
  }
  for (const existing of bets) {
    if (existing.epoch_id !== epochId) {
      throw new Error(
        `cannot mix epochs: existing bets are for ${JSON.stringify(existing.epoch_id)}, `
        + `new bet is for ${JSON.stringify(epochId)}`,
      );
    }
  }
  return [...bets, { player, civ, amount, epoch_id: epochId }];
}

// epoch: a runEpoch result. Pure; payouts are in bet-placement order and
// always sum to exactly the pool (see the header comment for the rule).
export function settleEpoch(epoch, bets) {
  const epochId = epoch.epoch_id;
  const winner = epoch.winner;
  const civIds = epoch.civs.map((c) => c.id);
  if (!civIds.includes(winner)) {
    throw new Error(`epoch winner ${winner} is not one of the civilizations ${JSON.stringify(civIds)}`);
  }
  for (const bet of bets) {
    if (bet.epoch_id !== epochId) {
      throw new Error(`bet epoch ${JSON.stringify(bet.epoch_id)} does not match epoch ${JSON.stringify(epochId)}`);
    }
    if (!civIds.includes(bet.civ)) {
      throw new Error(`bet civ ${bet.civ} is not one of the civilizations ${JSON.stringify(civIds)}`);
    }
    if (!isIntLike(bet.amount) || bet.amount <= 0) {
      throw new Error(`bet amount must be positive, got ${JSON.stringify(bet.amount)}`);
    }
  }
  const pool = bets.reduce((s, b) => s + b.amount, 0);
  const winnerPool = bets.filter((b) => b.civ === winner).reduce((s, b) => s + b.amount, 0);
  const base = {
    epoch_id: epochId,
    winner,
    currency: PLAY_MONEY_CURRENCY,
    play_money_note: PLAY_MONEY_LABEL,
    house_fee_cents: 0,
    rollover_cents: 0,
    pool,
    winner_pool: winnerPool,
    loser_pool: pool - winnerPool,
    payouts: [],
  };
  if (bets.length === 0) return { ...base, outcome: "no_bets" };
  if (winnerPool === 0) {
    // Nobody backed the winner: refund every stake in full, roll over nothing.
    return {
      ...base,
      outcome: "refunded_no_winner_bets",
      payouts: bets.map((b) => ({ player: b.player, civ: b.civ, stake: b.amount, payout: b.amount, profit: 0 })),
    };
  }
  const winningPositions = bets.map((b, i) => (b.civ === winner ? i : -1)).filter((i) => i >= 0);
  const shares = new Map(winningPositions.map((i) => [i, floorDiv(bets[i].amount * pool, winnerPool)]));
  const leftover = pool - [...shares.values()].reduce((a, b) => a + b, 0);
  const bonus = new Set(winningPositions.slice(0, leftover));
  let paidOut = 0;
  const payouts = bets.map((bet, i) => {
    if (bet.civ === winner) {
      const payout = shares.get(i) + (bonus.has(i) ? 1 : 0);
      paidOut += payout;
      return { player: bet.player, civ: bet.civ, stake: bet.amount, payout, profit: payout - bet.amount };
    }
    return { player: bet.player, civ: bet.civ, stake: bet.amount, payout: 0, profit: -bet.amount };
  });
  if (paidOut !== pool) throw new Error(`payouts do not sum to the pool (paid ${paidOut}, pool ${pool})`);
  return { ...base, outcome: "settled", payouts };
}

// Browser global (Node: harmless — globalThis exists there too).
globalThis.GenesisEngine = {
  runWorld,
  createWorld,
  Simulation,
  playSummary,
  worldSummary,
  stateDigest,
  defaultConfig,
  MT19937,
  deriveRng,
  sha256Hex,
  sha512Bytes,
  pyRound,
  pyReprFloat,
  canonicalStringify,
  gini,
  summarizeWealth,
  ruleBasedDecide,
  clearAuction,
  validateOrders,
  RESOURCES,
  OCCUPATIONS,
  PRODUCT,
  NAME_POOL,
  // Epochs + betting.
  CIV_NAMES,
  EPOCH_MIN_DAYS,
  EPOCH_MAX_DAYS,
  EPOCH_DEFAULT_DAYS,
  EPOCH_DEFAULT_CIVS,
  EPOCH_DEFAULT_RESIDENTS_PER_CIV,
  PLAY_MONEY_CURRENCY,
  PLAY_MONEY_LABEL,
  civSeed,
  epochIdFor,
  survivalScore,
  epochDigest,
  deriveWinner,
  runEpoch,
  placeBet,
  settleEpoch,
};
