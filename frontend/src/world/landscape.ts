/** Fixed scenery layout shared by pixel rendering and collision. World units. */
// Trails guide the eye; movement remains free.
export const paths: [number, number][][] = [
  [
    [340, 350],
    [410, 420],
    [560, 455],
    [800, 500],
  ],
  [
    [1220, 350],
    [1130, 410],
    [980, 445],
    [800, 500],
  ],
  [
    [800, 500],
    [750, 620],
    [800, 790],
  ],
  [
    [340, 890],
    [455, 850],
    [610, 860],
    [800, 790],
  ],
  [
    [1280, 890],
    [1190, 810],
    [1110, 750],
    [980, 735],
    [800, 790],
  ],
  [
    [1260, 580],
    [1150, 580],
    [1070, 520],
    [980, 445],
  ],
];
export function noise(x: number, y: number): number {
  let n = Math.imul(x + 193, 374761393) ^ Math.imul(y + 71, 668265263);
  n = Math.imul(n ^ (n >>> 13), 1274126177);
  return (n ^ (n >>> 16)) >>> 0;
}
function segmentDistance(
  x: number,
  y: number,
  a: [number, number],
  b: [number, number],
) {
  const dx = b[0] - a[0],
    dy = b[1] - a[1];
  const t = Math.max(
    0,
    Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy)),
  );
  return Math.hypot(x - a[0] - dx * t, y - a[1] - dy * t);
}
const clearings = [
  [340, 350],
  [1220, 350],
  [340, 890],
  [800, 790],
  [1280, 890],
  [1260, 580],
  [800, 500],
];
export const trees: { x: number; y: number; variant: number }[] = [];
for (let row = 0; row < 12; row++)
  for (let col = 0; col < 18; col++) {
    const n = noise(col, row),
      x = 95 + col * 82 + (n % 29),
      y = 110 + row * 78 + ((n >>> 5) % 23);
    if (
      x > 1510 ||
      y > 1030 ||
      clearings.some(
        ([cx, cy]) => Math.abs(x - cx!) < 150 && y > cy! - 230 && y < cy! + 115,
      )
    )
      continue;
    if (x > 520 && x < 1000 && y > 140 && y < 370) continue;
    if (
      paths.some((path) =>
        path.some(
          (a, i) => i > 0 && segmentDistance(x, y, path[i - 1]!, a) < 76,
        ),
      )
    )
      continue;
    trees.push({ x, y, variant: n % 3 });
  }
