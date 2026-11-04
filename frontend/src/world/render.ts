import type { Result } from "../api";
import { HEIGHT, places, WIDTH, World } from "./engine";
import { paintSprite } from "./art";
import { noise, paths, trees } from "./landscape";

// Two world units per art pixel; only the final blit scales the pixel buffer.
const UNIT = 2;
const P = {
  ink: "#171c30",
  grass: "#344c50",
  grassLight: "#3f5a56",
  moss: "#576957",
  dark: "#263e45",
  path: "#74766b",
  stone: "#565b6a",
  water: "#263f60",
  gold: "#e9bd86",
};
export function camera(world: World, width: number, height: number) {
  const scale = width < 700 ? 1.2 : 1.35;
  return {
    scale,
    x: Math.max(
      0,
      Math.min(Math.max(0, WIDTH - width / scale), world.x - width / scale / 2),
    ),
    y: Math.max(
      0,
      Math.min(
        Math.max(0, HEIGHT - height / scale),
        world.y - height / scale / 2,
      ),
    ),
  };
}
function canvas(w: number, h: number) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
}
function rect(
  c: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  color: string,
) {
  c.fillStyle = color;
  c.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h));
}
function line(
  c: CanvasRenderingContext2D,
  points: number[][],
  color: string,
  width = 1,
) {
  c.strokeStyle = color;
  c.lineWidth = width;
  c.beginPath();
  points.forEach(([x, y], i) => {
    if (i) c.lineTo(x!, y!);
    else c.moveTo(x!, y!);
  });
  c.stroke();
}
function ground() {
  const sheet = canvas(WIDTH / UNIT, HEIGHT / UNIT),
    c = sheet.getContext("2d")!;
  rect(c, 0, 0, sheet.width, sheet.height, P.dark);
  for (let y = 22; y < sheet.height - 20; y += 8)
    for (let x = 22; x < sheet.width - 20; x += 8) {
      const n = noise(x, y);
      rect(c, x, y, 8, 8, [P.grass, P.grass, "#375053", "#324a4e"][n % 4]!);
      if (n % 3 === 0) {
        rect(c, x + (n % 5), y + ((n >>> 4) % 6), 1, 2, P.moss);
        rect(c, x + (n % 5) + 2, y + ((n >>> 4) % 6) + 1, 1, 1, P.moss);
      }
      if (n % 37 === 0) {
        rect(c, x + 3, y + 3, 2, 1, "#7e8a75");
        rect(c, x + 4, y + 2, 1, 1, "#c2b4a0");
      }
    }
  for (const path of paths) {
    const points = path.map(([x, y]) => [x / UNIT, y / UNIT]);
    line(c, points, "#2c4449", 30);
    line(c, points, "#5b665d", 24);
    line(c, points, P.path, 18);
  }
  // Broken stone plaza; trails are intentionally narrow and irregular.
  for (let y = 205; y < 278; y += 9)
    for (let x = 353; x < 447; x += 13) {
      if (Math.hypot((x - 400) * 0.8, y - 242) < 39)
        rect(
          c,
          x + (y % 2) * 3,
          y,
          11,
          7,
          noise(x, y) % 3 === 0 ? "#858779" : "#626d69",
        );
    }
  for (const path of paths)
    for (let i = 1; i < path.length; i++) {
      const a = path[i - 1]!,
        b = path[i]!;
      for (let t = 0; t < 1; t += 0.045) {
        const x = (a[0] + (b[0] - a[0]) * t) / UNIT,
          y = (a[1] + (b[1] - a[1]) * t) / UNIT,
          n = noise(Math.round(x), Math.round(y));
        rect(
          c,
          x + (n % 9) - 4,
          y + ((n >>> 5) % 11) - 5,
          3 + (n % 4),
          1,
          n % 2 ? "#888b7b" : "#656f65",
        );
      }
    }
  // The water uses the same rectangular bounds as engine collision.
  rect(c, 274, 89, 207, 87, P.ink);
  rect(c, 277, 92, 201, 81, "#666b77");
  rect(c, 280, 95, 195, 75, P.water);
  for (let i = 0; i < 70; i++) {
    const n = noise(i, 74);
    rect(
      c,
      281 + (n % 191),
      96 + ((n >>> 8) % 72),
      3 + (n % 10),
      1,
      n % 2 ? "#304d6c" : "#2c4664",
    );
  }
  for (let x = 276; x < 480; x += 13) {
    rect(c, x, 88, 10, 4, "#7d7e85");
    rect(c, x, 173, 10, 3, "#4b5f60");
  }
  for (let x = 281; x < 479; x += 23) {
    rect(c, x, 167, 2, 7, "#62765e");
    rect(c, x - 2, 169, 1, 5, "#849173");
  }
  for (const [x, y, length] of [
    [112, 188, 52],
    [112, 455, 37],
    [585, 318, 65],
    [675, 450, 57],
  ]) {
    rect(c, x!, y! + 3, length!, 2, "#59606a");
    rect(c, x!, y! + 9, length!, 2, "#444b5a");
    for (let i = 0; i < length!; i += 10) rect(c, x! + i, y!, 3, 15, "#7d7c7c");
  }
  for (const [x, y] of [
    [360, 230],
    [437, 225],
    [443, 265],
  ]) {
    rect(c, x!, y!, 6, 12, P.ink);
    rect(c, x! + 1, y! + 1, 4, 8, "#7a7a8c");
    rect(c, x! + 2, y! + 3, 2, 3, "#b39ada");
  }
  return sheet;
}
function tree(variant: number) {
  const sheet = canvas(54, 66),
    c = sheet.getContext("2d")!;
  rect(c, 10, 57, 36, 5, "#233944");
  rect(c, 25, 39, 6, 23, "#363341");
  rect(c, 27, 43, 2, 18, "#776063");
  const colors =
    variant === 2
      ? ["#353e59", "#46516c", "#5b6480", "#777591"]
      : ["#213e46", "#2c5151", "#42655b", "#607e68"];
  for (const [x, y, w, h, color] of [
    [19, 0, 16, 5, 0],
    [10, 5, 33, 7, 0],
    [5, 12, 42, 10, 0],
    [1, 22, 50, 19, 0],
    [6, 41, 42, 9, 0],
    [12, 50, 29, 5, 0],
    [16, 5, 18, 7, 1],
    [8, 12, 35, 15, 1],
    [5, 25, 38, 15, 1],
    [11, 39, 27, 8, 1],
    [16, 10, 14, 5, 2],
    [11, 16, 24, 8, 2],
    [8, 28, 22, 7, 2],
    [16, 13, 10, 3, 3],
  ])
    rect(c, x!, y!, w!, h!, colors[color!]!);
  for (let i = 0; i < 16; i++) {
    const n = noise(i, variant);
    rect(c, 8 + (n % 31), 14 + ((n >>> 8) % 29), 3, 1, colors[(n % 2) + 1]!);
  }
  return sheet;
}
function building(id: string) {
  const sheet = canvas(144, 142),
    c = sheet.getContext("2d")!;
  if (id === "wallet") {
    rect(c, 44, 117, 58, 8, P.ink);
    rect(c, 50, 109, 46, 8, "#6c7180");
    rect(c, 54, 104, 38, 5, "#9492a1");
    rect(c, 57, 65, 32, 39, "#252c47");
    rect(c, 60, 68, 26, 29, "#625278");
    rect(c, 63, 72, 20, 19, "#252e46");
    rect(c, 66, 75, 14, 2, "#c8b8e4");
    rect(c, 69, 80, 8, 7, "#8b70db");
    rect(c, 65, 99, 16, 2, P.gold);
    rect(c, 52, 54, 42, 9, "#2b2b46");
    rect(c, 58, 48, 30, 6, "#7a698f");
    rect(c, 65, 43, 16, 5, "#a793bb");
    return sheet;
  }
  const color =
    id === "alice"
      ? "#807091"
      : id === "bob"
        ? "#8f6776"
        : id === "relay"
          ? "#527d83"
          : id === "workshop"
            ? "#6f6089"
            : "#555e70";
  rect(c, 13, 111, 121, 15, "#22343e");
  rect(c, 20, 65, 106, 53, "#3a3449");
  rect(c, 24, 65, 97, 48, "#b3a193");
  for (let y = 70; y < 109; y += 8) {
    rect(c, 25, y, 95, 1, "#968b87");
    for (let x = 28 + (y % 3) * 9; x < 119; x += 22)
      rect(c, x, y, 1, 7, "#968b87");
  }
  rect(c, 22, 103, 101, 10, "#696273");
  rect(c, 18, 111, 111, 4, "#8e8190");
  rect(c, 62, 82, 24, 33, P.ink);
  rect(c, 65, 85, 18, 27, "#62526b");
  rect(c, 67, 86, 2, 24, "#82708c");
  rect(c, 79, 99, 2, 2, P.gold);
  for (const x of [32, 98]) {
    rect(c, x, 78, 17, 21, P.ink);
    rect(c, x + 2, 80, 13, 16, "#a77d71");
    rect(c, x + 3, 81, 10, 12, P.gold);
    rect(c, x + 8, 80, 1, 16, "#6d5a6b");
    rect(c, x + 2, 87, 13, 1, "#6d5a6b");
    rect(c, x - 1, 99, 19, 3, "#5c576a");
  }
  for (let row = 0; row < 10; row++) {
    const left = 10 + row * 5,
      right = 136 - row * 5,
      y = 65 - row * 4;
    rect(c, left - 3, y + 3, right - left + 8, 5, P.ink);
    rect(c, left, y, right - left, 5, color);
    for (let x = left + (row % 2) * 5; x < right - 3; x += 12)
      rect(c, x, y + 3, 8, 1, "#302c49");
    if (row % 2 === 0)
      rect(
        c,
        left + 2,
        y,
        right - left - 4,
        1,
        id === "relay" ? "#749c9e" : "#aa91b1",
      );
  }
  rect(c, 102, 22, 10, 29, "#3c364c");
  rect(c, 104, 23, 7, 23, "#8d7c89");
  rect(c, 101, 20, 12, 4, "#b6a2a7");
  rect(c, 57, 43, 33, 12, "#343049");
  rect(c, 60, 46, 27, 1, "#e1c59c");
  rect(c, 65, 49, 17, 2, "#ab91c3");
  rect(c, 125, 80, 3, 27, "#4d4457");
  rect(c, 124, 81, 14, 13, "#3a3149");
  rect(c, 126, 83, 10, 8, color);
  rect(c, 17, 99, 14, 13, "#443a49");
  rect(c, 19, 101, 10, 9, "#8b6f6d");
  rect(c, 18, 105, 12, 2, "#342d40");
  for (let i = 0; i < 4; i++) {
    rect(c, 35 + i * 4, 110 - (i % 2) * 3, 2, 7, "#70846a");
    rect(c, 34 + i * 4, 109 - (i % 2) * 3, 4, 2, "#b095b9");
  }
  if (id === "relay") {
    rect(c, 11, 70, 6, 28, "#292e43");
    rect(c, 9, 64, 10, 9, "#ccb899");
    rect(c, 11, 66, 6, 4, "#f1d6a5");
  }
  if (id === "workshop") {
    rect(c, 89, 113, 23, 8, "#40354e");
    rect(c, 93, 108, 15, 5, "#9b819f");
    rect(c, 99, 103, 3, 6, "#dfb16d");
  }
  return sheet;
}
interface Scene {
  ground: HTMLCanvasElement;
  trees: HTMLCanvasElement[];
  buildings: Map<string, HTMLCanvasElement>;
  frame: HTMLCanvasElement;
}
const scenes = new WeakMap<CanvasRenderingContext2D, Scene>();
function sceneFor(ctx: CanvasRenderingContext2D) {
  let scene = scenes.get(ctx);
  if (!scene) {
    scene = {
      ground: ground(),
      trees: [tree(0), tree(1), tree(2)],
      buildings: new Map(places.map((p) => [p.id, building(p.id)])),
      frame: canvas(1, 1),
    };
    scenes.set(ctx, scene);
  }
  return scene;
}
export function renderWorld(
  ctx: CanvasRenderingContext2D,
  world: World,
  width: number,
  height: number,
  time: number,
  result: Result | null,
  reducedMotion = false,
) {
  const scene = sceneFor(ctx),
    view = camera(world, width, height),
    pixel = UNIT * view.scale;
  const w = Math.ceil(width / pixel),
    h = Math.ceil(height / pixel);
  if (scene.frame.width !== w || scene.frame.height !== h) {
    scene.frame.width = w;
    scene.frame.height = h;
  }
  const c = scene.frame.getContext("2d")!;
  c.imageSmoothingEnabled = false;
  rect(c, 0, 0, w, h, P.ink);
  const cx = Math.floor(view.x / UNIT),
    cy = Math.floor(view.y / UNIT);
  c.save();
  c.translate(-cx, -cy);
  c.drawImage(scene.ground, 0, 0);
  const clock = reducedMotion ? 0 : time;
  for (let i = 0; i < 8; i++)
    rect(
      c,
      289 + i * 22,
      110 + (i % 3) * 16,
      9 + Math.round(Math.sin(clock + i) * 4),
      1,
      "#55758d",
    );
  const objects: { y: number; draw: () => void }[] = [];
  for (const t of trees) {
    if (
      t.x / 2 < cx - 55 ||
      t.x / 2 > cx + w + 55 ||
      t.y / 2 < cy - 10 ||
      t.y / 2 > cy + h + 70
    )
      continue;
    objects.push({
      y: t.y,
      draw: () =>
        c.drawImage(
          scene.trees[t.variant]!,
          Math.round(t.x / 2 - 27),
          Math.round(t.y / 2 - 62),
        ),
    });
  }
  for (const p of places) {
    objects.push({
      y: p.y - 58,
      draw: () =>
        c.drawImage(scene.buildings.get(p.id)!, p.x / 2 - 72, p.y / 2 - 142),
    });
    if (p.id !== "wallet")
      objects.push({
        y: p.y - 7,
        draw: () => paintSprite(c, p.id, p.x / 2 + 19, p.y / 2 - 4),
      });
  }
  const foot = world.moving ? Math.round(Math.sin(clock * 15)) : 0;
  const jump =
    world.hops > 0
      ? Math.round(Math.sin((world.hops / 0.5) * Math.PI) * 14)
      : 0;
  objects.push({
    y: world.y,
    draw: () => {
      rect(c, world.x / 2 - 10, world.y / 2 - 1, 20, 4, "#23343e");
      paintSprite(
        c,
        "nomi",
        world.x / 2,
        world.y / 2 + foot - jump,
        1,
        world.facing,
      );
      if (world.sprint && world.moving)
        for (let i = 1; i < 4; i++)
          rect(
            c,
            world.x / 2 - world.facing * i * 8,
            world.y / 2 + 2,
            3 - i * 0.5,
            1,
            "#b5af92",
          );
    },
  });
  objects.sort((a, b) => a.y - b.y).forEach((o) => o.draw());
  const parcel = (x: number, y: number, color = "#a486c5") => {
    rect(c, x - 6, y - 6, 12, 11, P.ink);
    rect(c, x - 5, y - 5, 10, 8, color);
    rect(c, x - 1, y - 5, 2, 8, "#e5cda1");
    rect(c, x - 5, y - 1, 10, 1, "#786279");
  };
  if (result)
    for (const v of result.variants) {
      if (!v.transaction || v.transaction.status !== 1) continue;
      const to = v.transaction.to.label === "bob" ? places[2]! : places[4]!;
      line(
        c,
        [
          [400, 365],
          [to.x / 2, 365],
          [to.x / 2, to.y / 2],
        ],
        v.status === "passed" ? "#b29bd1" : "#d28c94",
      );
      const phase = (clock * 0.12) % 1;
      parcel(
        400 + (to.x / 2 - 400) * Math.min(1, phase / 0.72),
        phase < 0.72 ? 365 : 365 + ((to.y / 2 - 365) * (phase - 0.72)) / 0.28,
      );
    }
  for (const s of world.signals)
    if (!s.found) {
      const x = s.x / 2,
        y = s.y / 2 + Math.round(Math.sin(clock * 2 + s.x) * 2);
      rect(c, x - 1, y - 5, 3, 11, "#7460a3");
      rect(c, x - 4, y - 2, 9, 5, "#a386d7");
      rect(c, x - 1, y - 2, 3, 3, "#ded1f1");
    }
  parcel(
    world.parcel.x / 2,
    world.parcel.y / 2 - jump * (world.parcel.held ? 1 : 0),
  );
  for (const p of places) {
    const x = p.x / 2 - 43,
      y = p.y / 2 - 37;
    rect(c, x - 7, y - 5, 16, 16, "#e8bd7e12");
    rect(c, x - 4, y - 2, 10, 10, "#e8bd7e20");
    rect(c, x, y, 3, 5, P.gold);
  }
  for (let i = 0; i < 12; i++) {
    const n = noise(i, 55),
      x = 120 + (n % 560),
      y = 100 + ((n >>> 10) % 350);
    if (Math.sin(clock * 1.2 + i) > 0.1)
      rect(
        c,
        x + Math.round(Math.sin(clock * 0.4 + i) * 3),
        y,
        1,
        1,
        "#d2c7a1",
      );
  }
  if (world.toyDelivered) rect(c, 166, 448, 8, 2, P.gold);
  const nearby = world.nearby();
  if (nearby) {
    const x = nearby.x / 2,
      y = nearby.y / 2 - 48;
    rect(c, x - 5, y - 7, 10, 10, P.ink);
    rect(c, x - 4, y - 6, 8, 8, "#b59bd4");
    rect(c, x - 1, y - 4, 3, 1, P.ink);
    rect(c, x - 1, y - 2, 2, 1, P.ink);
  }
  c.restore();
  for (let i = 0; i < 5; i++) {
    c.fillStyle = "rgba(12,16,33," + (5 - i) * 0.018 + ")";
    c.fillRect(i, i, w - i * 2, 1);
    c.fillRect(i, h - i - 1, w - i * 2, 1);
    c.fillRect(i, i, 1, h - i * 2);
    c.fillRect(w - i - 1, i, 1, h - i * 2);
  }
  ctx.clearRect(0, 0, width, height);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(scene.frame, 0, 0, w * pixel, h * pixel);
}
