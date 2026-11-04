import { describe, expect, it } from "vitest";
import { canStand, HEIGHT, places, WIDTH, World } from "./engine";
import { camera } from "./render";

function advance(world: World, frames = 20) {
  for (let i = 0; i < frames; i++) world.update(0.01);
}

describe("Free roaming presentation physics (never a chain simulation)", () => {
  it("keeps every resident reachable through the forest from the plaza", () => {
    const queue: [number, number][] = [[800, 500]];
    const seen = new Set(["800,500"]);
    for (let index = 0; index < queue.length; index++) {
      const [x, y] = queue[index]!;
      for (const [dx, dy] of [
        [20, 0],
        [-20, 0],
        [0, 20],
        [0, -20],
      ]) {
        const nx = x + dx!,
          ny = y + dy!,
          key = `${nx},${ny}`;
        if (
          !seen.has(key) &&
          canStand(nx, ny) &&
          canStand(x + dx! / 2, y + dy! / 2)
        ) {
          seen.add(key);
          queue.push([nx, ny]);
        }
      }
    }
    for (const place of places)
      expect(
        queue.some(([x, y]) => Math.hypot(place.x - x, place.y - y) < 90),
        place.id,
      ).toBe(true);
  });
  it("supports WASD and arrows, normalizes diagonals and sprints", () => {
    const straight = new World();
    straight.keys.add("d");
    advance(straight);
    const diagonal = new World();
    diagonal.keys.add("d");
    diagonal.keys.add("s");
    advance(diagonal);
    expect(straight.x - 800).toBeCloseTo(44);
    expect(Math.hypot(diagonal.x - 800, diagonal.y - 500)).toBeCloseTo(44);
    const sprint = new World();
    sprint.keys.add("arrowright");
    sprint.keys.add("shift");
    advance(sprint);
    expect(sprint.x - 800).toBeCloseTo(76);
    sprint.keys.clear();
    advance(sprint);
    expect(sprint.moving).toBe(false);
  });
  it("blocks buildings, water and bounds even after a slow frame", () => {
    const world = new World();
    world.x = 340;
    world.y = 320;
    world.keys.add("w");
    world.keys.add("shift");
    for (let i = 0; i < 100; i++) world.update(2);
    expect(canStand(world.x, world.y)).toBe(true);
    expect(world.y).toBeGreaterThanOrEqual(302);
    expect(canStand(700, 250)).toBe(false);
    expect(canStand(0, 500)).toBe(false);
    world.x = WIDTH - 70;
    world.y = 500;
    world.keys.clear();
    world.keys.add("d");
    advance(world, 100);
    expect(world.x).toBeLessThan(WIDTH - 65);
    world.x = 800;
    world.y = HEIGHT - 70;
    world.keys.clear();
    world.keys.add("s");
    advance(world, 100);
    expect(world.y).toBeLessThan(HEIGHT - 65);
  });
  it("allows approaching every interaction and stops click walking at walls", () => {
    const world = new World();
    for (const place of places) {
      world.x = place.x;
      world.y = place.y;
      expect(canStand(world.x, world.y)).toBe(true);
      expect(world.nearby()?.id).toBe(place.id);
    }
    world.x = 340;
    world.y = 340;
    world.target = { x: 340, y: 200 };
    advance(world, 200);
    expect(canStand(world.x, world.y)).toBe(true);
    expect(world.target).toBeNull();
    world.x = 800;
    world.y = 500;
    world.target = { x: 900, y: 500 };
    world.keys.add("a");
    world.update(0.05);
    expect(world.target).toBeNull();
    expect(world.x).toBeLessThan(800);
  });
  it("carries, throws and delivers a toy parcel independently of any API", () => {
    const world = new World();
    expect(world.space()).toContain("拿到");
    world.update(0.01);
    expect(world.parcel.held).toBe(true);
    expect(world.parcel.x).toBe(world.x + 25);
    world.x = 340;
    world.y = 890;
    world.update(0.01);
    expect(world.space()).toContain("抛出");
    world.update(0.01);
    expect(world.toyDelivered).toBe(true);
    expect(world.parcel.held).toBe(false);
    world.x = 1000;
    world.y = 600;
    expect(world.space()).toContain("跳");
    advance(world, 60);
    expect(world.hops).toBe(0);
    const oldX = world.parcel.x;
    advance(world, 100);
    expect(world.parcel.x).toBeGreaterThan(oldX);
    expect(canStand(world.parcel.x, world.parcel.y)).toBe(true);
  });
  it("collects exploration signals once and clamps the camera on large displays", () => {
    const world = new World();
    for (const signal of world.signals) {
      world.x = signal.x;
      world.y = signal.y;
      world.update(0.01);
    }
    expect(world.signals.filter((s) => s.found)).toHaveLength(3);
    expect(camera(world, 4000, 3000)).toMatchObject({ x: 0, y: 0 });
  });
});
