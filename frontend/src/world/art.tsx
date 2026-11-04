/** Original, code-authored pixel art. No third-party game assets. */
import type { PlaceId } from "./engine";

export type PortraitKind = PlaceId | "nomi" | "menu";
const nomi = [
  "....oo........oo....",
  "...ovvo......ovvo...",
  "...ovvvo....ovvvo...",
  "....ovvvooovvvvo....",
  ".....ovvvvvvvvo.....",
  "....ovvllllllvvo....",
  "...ovllhhhhhhllvo...",
  "..ovllhddddddhllvo..",
  "..ovlhddddddddhlvo..",
  "..ovlhddwwddwwhlvo..",
  "..ovlhddwwddwwhlvo..",
  "..ovlhddddddddhlvo..",
  "...ovlhddddddhlvo...",
  "...ovllhhhhhhllvo...",
  "....ovllllllllvo....",
  "...ovvvllllllvvvo...",
  "..ovvvvlpppplvvvvo..",
  "..ovovvlpwwplvvovo..",
  "..oo.ovlpwwplvo.oo..",
  ".....ovvppppvvo.....",
  ".....ovvvvvvvvo.....",
  "......ovvvvvvo......",
  "......obboobbo......",
  ".....obbboobbbo.....",
];
const resident = [
  "......oooooo......",
  ".....ohhhhhhho....",
  "....ohhhhhhhhho...",
  "...ohhHHHHHHhhho..",
  "...ohHssssssHhho..",
  "...ohsseesseesho..",
  "....osssssssso....",
  ".....osssssso.....",
  "......osssso......",
  ".....occcccco.....",
  "....occcccccco....",
  "...occccaacccco...",
  "...oscCCAACCcso...",
  "...ossCCAACCsso...",
  "....ooCAAAACoo....",
  "......oAAAAo......",
  "......occcco......",
  "......obbbbo......",
  ".....obbobbo......",
  ".....obb.obbo.....",
];
export const pixelPalette = {
  o: "#171b32",
  v: "#795da9",
  l: "#b5a1df",
  h: "#59476f",
  d: "#25283f",
  w: "#fff1cc",
  p: "#7152c9",
  b: "#423955",
};
const people: Record<string, Record<string, string>> = {
  alice: {
    h: "#493c57",
    H: "#725372",
    s: "#e2b8a6",
    e: "#302539",
    c: "#6a75a1",
    C: "#8996be",
    a: "#b7accd",
    A: "#dfd4cb",
    b: "#39394e",
  },
  relay: {
    h: "#3b495e",
    H: "#586882",
    s: "#d4b6a5",
    e: "#273044",
    c: "#547d7d",
    C: "#7ca49c",
    a: "#b7bd98",
    A: "#dbd1ad",
    b: "#343f53",
  },
  bob: {
    h: "#925b55",
    H: "#c27b63",
    s: "#e2b29b",
    e: "#432f43",
    c: "#8e668a",
    C: "#b489a0",
    a: "#bdad93",
    A: "#e5d3b1",
    b: "#493d52",
  },
  warehouse: {
    h: "#414254",
    H: "#5c5c71",
    s: "#c9b39f",
    e: "#262b3c",
    c: "#56596f",
    C: "#73758a",
    a: "#8c8797",
    A: "#aaa1ad",
    b: "#2e3449",
  },
  workshop: {
    h: "#584869",
    H: "#84618d",
    s: "#d4afa0",
    e: "#302439",
    c: "#72558c",
    C: "#a180b0",
    a: "#caaa83",
    A: "#edc893",
    b: "#363046",
  },
};
export function spriteFor(kind: PortraitKind) {
  return kind === "nomi" || kind === "menu" || kind === "wallet"
    ? { art: nomi, palette: pixelPalette }
    : { art: resident, palette: { o: "#171b32", ...people[kind] } };
}
export function paintSprite(
  ctx: CanvasRenderingContext2D,
  kind: PortraitKind,
  x: number,
  y: number,
  step = 1,
  facing = 1,
) {
  const { art, palette } = spriteFor(kind);
  ctx.save();
  ctx.translate(Math.round(x), Math.round(y));
  ctx.scale(facing, 1);
  for (let row = 0; row < art.length; row++)
    for (let col = 0; col < art[row]!.length; col++) {
      const key = art[row]![col]!;
      const color = (palette as Record<string, string>)[key];
      if (color) {
        ctx.fillStyle = color;
        ctx.fillRect(
          (col - art[0]!.length / 2) * step,
          (row - art.length) * step,
          step,
          step,
        );
      }
    }
  ctx.restore();
}
export function PixelPortrait({ kind }: { kind: PortraitKind }) {
  const { art, palette } = spriteFor(kind);
  return (
    <svg viewBox="0 0 32 36" aria-hidden="true" shapeRendering="crispEdges">
      <rect width="32" height="36" fill="#25283e" />
      <path d="M0 30L32 9V36H0Z" fill="#34324f" />
      {art.flatMap((row, y) =>
        [...row].map((key, x) => {
          const fill = (palette as Record<string, string>)[key];
          return fill ? (
            <rect
              key={`${x}-${y}`}
              x={x + (32 - art[0]!.length) / 2}
              y={y + 36 - art.length - 4}
              width="1"
              height="1"
              fill={fill}
            />
          ) : null;
        }),
      )}
    </svg>
  );
}
