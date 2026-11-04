/** Presentation-only toy world. Chain decisions and grades never live here. */
import { trees } from "./landscape";
export const WIDTH = 1600;
export const HEIGHT = 1100;
export const places = [
  {
    id: "alice",
    name: "Alice 的工作室",
    x: 340,
    y: 350,
    color: "#b8b4fe",
    sign: "ALICE",
    evidence: "authorized-intent",
  },
  {
    id: "relay",
    name: "支付中继站",
    x: 1220,
    y: 350,
    color: "#a6bbcf",
    sign: "API",
    evidence: "payment-request",
  },
  {
    id: "bob",
    name: "Bob 的画室",
    x: 340,
    y: 890,
    color: "#d9b7c7",
    sign: "BOB",
    evidence: "field-comparison",
  },
  {
    id: "wallet",
    name: "付款终端",
    x: 800,
    y: 790,
    color: "#6e54ff",
    sign: "PAY",
    evidence: "transaction-draft",
  },
  {
    id: "warehouse",
    name: "另一间仓库",
    x: 1280,
    y: 890,
    color: "#b3acbd",
    sign: "???",
    evidence: "chain-accounts",
  },
  {
    id: "workshop",
    name: "合约工坊",
    x: 1260,
    y: 580,
    color: "#c2b6e8",
    sign: "BUILD",
    evidence: "",
  },
] as const;
export type PlaceId = (typeof places)[number]["id"];
export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}
export const obstacles: Rect[] = places
  .filter((p) => p.id !== "wallet")
  .map((p) => ({ x: p.x - 105, y: p.y - 185, w: 210, h: 125 }));
obstacles.push({ x: 560, y: 190, w: 390, h: 150 });
obstacles.push(
  ...trees.map((t) => ({ x: t.x - 10, y: t.y - 8, w: 20, h: 16 })),
);
export function canStand(x: number, y: number): boolean {
  return (
    x > 65 &&
    y > 65 &&
    x < WIDTH - 65 &&
    y < HEIGHT - 65 &&
    !obstacles.some(
      (o) =>
        x + 17 > o.x &&
        x - 17 < o.x + o.w &&
        y + 12 > o.y &&
        y - 12 < o.y + o.h,
    )
  );
}
export class World {
  x = 800;
  y = 500;
  facing = 1;
  moving = false;
  sprint = false;
  keys = new Set<string>();
  parcel = { x: 860, y: 505, vx: 0, vy: 0, held: false };
  hops = 0;
  target: { x: number; y: number } | null = null;
  toyDelivered = false;
  signals = [
    { x: 520, y: 570, found: false },
    { x: 1080, y: 430, found: false },
    { x: 980, y: 940, found: false },
  ];
  update(delta: number) {
    const dt = Math.min(0.05, Math.max(0, delta));
    let dx =
      Number(this.keys.has("d") || this.keys.has("arrowright")) -
      Number(this.keys.has("a") || this.keys.has("arrowleft"));
    let dy =
      Number(this.keys.has("s") || this.keys.has("arrowdown")) -
      Number(this.keys.has("w") || this.keys.has("arrowup"));
    if (dx || dy) this.target = null;
    else if (this.target) {
      dx = this.target.x - this.x;
      dy = this.target.y - this.y;
      if (Math.hypot(dx, dy) < 12) {
        this.target = null;
        dx = 0;
        dy = 0;
      }
    }
    this.moving = Boolean(dx || dy);
    this.sprint = this.keys.has("shift");
    if (this.moving) {
      const length = Math.hypot(dx, dy);
      dx /= length;
      dy /= length;
      if (dx) this.facing = dx < 0 ? -1 : 1;
      const speed = this.sprint ? 380 : 220;
      const beforeX = this.x,
        beforeY = this.y;
      if (canStand(this.x + dx * speed * dt, this.y)) this.x += dx * speed * dt;
      if (canStand(this.x, this.y + dy * speed * dt)) this.y += dy * speed * dt;
      if (this.x === beforeX && this.y === beforeY) this.target = null;
    }
    if (this.parcel.held) {
      this.parcel.x = this.x + this.facing * 25;
      this.parcel.y = this.y - 30;
    } else {
      const p = this.parcel;
      const x = p.x + p.vx * dt,
        y = p.y + p.vy * dt;
      if (canStand(x, p.y)) p.x = x;
      else p.vx *= -0.45;
      if (canStand(p.x, y)) p.y = y;
      else p.vy *= -0.45;
      const drag = Math.exp(-4 * dt);
      p.vx *= drag;
      p.vy *= drag;
    }
    this.hops = Math.max(0, this.hops - dt);
    for (const signal of this.signals)
      if (Math.hypot(this.x - signal.x, this.y - signal.y) < 40)
        signal.found = true;
    if (
      !this.parcel.held &&
      Math.hypot(this.parcel.x - 340, this.parcel.y - 890) < 65
    )
      this.toyDelivered = true;
  }
  space(): string {
    if (this.parcel.held) {
      this.parcel.held = false;
      this.parcel.vx = this.facing * 420;
      this.parcel.vy = -70;
      return "包裹抛出去了！这是道具动作，不会发送交易。";
    }
    if (Math.hypot(this.x - this.parcel.x, this.y - this.parcel.y) < 85) {
      this.parcel.held = true;
      return "拿到了练习包裹。再按空格可以抛出去。";
    }
    this.hops = 0.5;
    return "跳一下！靠近包裹时，空格可以拿起它。";
  }
  nearby(): (typeof places)[number] | undefined {
    return places.find((p) => Math.hypot(this.x - p.x, this.y - p.y) < 115);
  }
}
