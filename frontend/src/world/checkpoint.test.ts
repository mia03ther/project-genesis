import { afterEach, describe, expect, it } from "vitest";
import {
  EXPLORATION_KEY,
  restoreExploration,
  saveExploration,
} from "./checkpoint";
import { World } from "./engine";

afterEach(() => localStorage.clear());
describe("Local exploration checkpoint", () => {
  it("restores toys and location, drops a carried parcel safely, and stores no chain state", () => {
    const world = new World();
    world.x = 340;
    world.y = 350;
    world.parcel.held = true;
    world.signals[1]!.found = true;
    world.toyDelivered = true;
    expect(saveExploration(world, localStorage)).toBe(true);
    const loaded = restoreExploration(localStorage);
    expect([loaded.x, loaded.y]).toEqual([340, 350]);
    expect(loaded.parcel).toMatchObject({
      x: 340,
      y: 350,
      held: false,
      vx: 0,
      vy: 0,
    });
    expect(loaded.signals.map((s) => s.found)).toEqual([false, true, false]);
    expect(loaded.toyDelivered).toBe(true);
    expect(
      Object.keys(JSON.parse(localStorage.getItem(EXPLORATION_KEY)!)).sort(),
    ).toEqual([
      "delivered",
      "parcelX",
      "parcelY",
      "signals",
      "version",
      "x",
      "y",
    ]);
  });
  it("rejects invalid versions, positions and malformed saves", () => {
    for (const data of [
      "broken",
      "null",
      JSON.stringify({ version: 99, x: 340, y: 350 }),
      JSON.stringify({ version: 1, x: 700, y: 250, parcelX: -1, parcelY: 100 }),
    ]) {
      localStorage.setItem(EXPLORATION_KEY, data);
      const loaded = restoreExploration(localStorage);
      expect([loaded.x, loaded.y]).toEqual([800, 500]);
      expect(loaded.parcel.x).toBe(860);
    }
  });
  it("continues without storage access and reports failed writes", () => {
    const storage = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("quota");
      },
    };
    expect(restoreExploration(storage).x).toBe(800);
    expect(saveExploration(new World(), storage)).toBe(false);
  });
});
