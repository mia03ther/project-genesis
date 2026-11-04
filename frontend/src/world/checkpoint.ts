import { canStand, World } from "./engine";

export const EXPLORATION_KEY = "genesis.island.exploration.v1";
type StoragePort = Pick<Storage, "getItem" | "setItem">;
/** Only local toy progress. No sessions, balances, permissions or grades. */
export function restoreExploration(storage: StoragePort): World {
  const world = new World();
  try {
    const saved: unknown = JSON.parse(
      storage.getItem(EXPLORATION_KEY) ?? "null",
    );
    if (!saved || typeof saved !== "object") return world;
    const s = saved as Record<string, unknown>;
    if (s.version !== 1) return world;
    if (
      typeof s.x === "number" &&
      typeof s.y === "number" &&
      Number.isFinite(s.x) &&
      Number.isFinite(s.y) &&
      canStand(s.x, s.y)
    ) {
      world.x = s.x;
      world.y = s.y;
    }
    const signals = s.signals;
    if (Array.isArray(signals))
      world.signals.forEach((signal, i) => {
        signal.found = signals[i] === true;
      });
    world.toyDelivered = s.delivered === true;
    // Restore the toy parcel only if it is on walkable ground. A held parcel
    // rests beside the player on reload, avoiding a hidden/stuck carried item.
    if (
      typeof s.parcelX === "number" &&
      typeof s.parcelY === "number" &&
      Number.isFinite(s.parcelX) &&
      Number.isFinite(s.parcelY) &&
      canStand(s.parcelX, s.parcelY)
    ) {
      world.parcel.x = s.parcelX;
      world.parcel.y = s.parcelY;
    }
  } catch {
    /* Unavailable storage or malformed data starts a fresh exploration. */
  }
  return world;
}
export function saveExploration(world: World, storage: StoragePort): boolean {
  try {
    storage.setItem(
      EXPLORATION_KEY,
      JSON.stringify({
        version: 1,
        x: world.x,
        y: world.y,
        signals: world.signals.map((s) => s.found),
        delivered: world.toyDelivered,
        parcelX: world.parcel.held ? world.x : world.parcel.x,
        parcelY: world.parcel.held ? world.y : world.parcel.y,
      }),
    );
    return true;
  } catch {
    return false;
  }
}
