// Pixel-art primitives: sprites are drawn from character maps, one SVG rect per
// horizontal run of same-coloured pixels, with crisp edges.
import type { ReactElement } from 'react';

export const C = {
  ink: '#2a2238', inkSoft: '#463a5c',
  grass: '#6aa84f', grass2: '#5b9845', grassDark: '#477a36', flower1: '#ff8fab', flower2: '#ffe066',
  path: '#e3d2ad', path2: '#cfbb90', pathEdge: '#b29c72', stone: '#9aa0ad',
  cream: '#f3e7cc', creamShade: '#dccaa3', wood: '#94603f', woodDark: '#6b412a',
  pink: '#e07a95', pinkDark: '#b2546f', teal: '#3f9aa3', tealDark: '#2d727a',
  green: '#78b660', greenDark: '#548c43', slate: '#5a6178', slateDark: '#40465a',
  screen: '#3ee6c8', screenDark: '#1e8f7c', gold: '#ffc94d', goldDark: '#d89a2b',
  glass: '#8fd3ea', light: '#ffe596', red: '#e5484d', white: '#fdf8ee',
  skin: '#f4c9a0', skinShade: '#d9a679', hair: '#7a4bd1', hairDark: '#5a33a3',
  brown: '#7a4e33', grey: '#8d8a83', greyDark: '#66635d', navy: '#2b3a67', water: '#5fb8d6',
} as const;

export type Palette = Record<string, string>;

/** Render a character map: each char is a palette key; '.' is transparent. */
export function Sprite({ art, palette, x = 0, y = 0, className }: { art: readonly string[]; palette: Palette; x?: number; y?: number; className?: string }): ReactElement {
  const rects: ReactElement[] = [];
  art.forEach((row, ry) => {
    let start = 0;
    for (let rx = 1; rx <= row.length; rx += 1) {
      const ch = row[start];
      if (rx === row.length || row[rx] !== ch) {
        const fill = ch !== undefined ? palette[ch] : undefined;
        if (ch !== '.' && fill) rects.push(<rect key={`${ry}-${start}`} x={x + start} y={y + ry} width={rx - start} height={1} fill={fill} />);
        start = rx;
      }
    }
  });
  return <g className={className}>{rects}</g>;
}

/** A filled block with a 1px ink outline: the basic building brick of the town. */
export function Block({ x, y, w, h, fill, outline = true }: { x: number; y: number; w: number; h: number; fill: string; outline?: boolean }): ReactElement {
  return (
    <g>
      {outline && <rect x={x - 1} y={y - 1} width={w + 2} height={h + 2} fill={C.ink} />}
      <rect x={x} y={y} width={w} height={h} fill={fill} />
    </g>
  );
}

// --- characters (12 x 16) ----------------------------------------------------------

const BODY_TOP_DETECTIVE = [
  '....HHHH....',
  '...HHHHHH...',
  '..HHHHHHHH..',
  '.KHHHHHHHHK.',
  '...SSSSSS...',
  '...SESSES...',
  '...SSSSSS...',
  '....SDDS....',
  '..CCCCCCCC..',
  '.CCCCYCCCCC.',
  '.SCCCYCCCCS.',
  '..CCCYCCCC..',
  '..CCCCCCCC..',
];
const LEGS_A = ['...PP..PP...', '...PP..PP...', '..BBB..BBB..'];
const LEGS_B = ['...PP...PP..', '..PP....PP..', '.BBB....BBB.'];
const DETECTIVE: Palette = { H: C.navy, K: C.ink, S: C.skin, E: C.ink, D: C.skinShade, C: C.screenDark, Y: C.gold, P: '#30344a', B: C.woodDark };

export function Detective({ walking }: { walking: boolean }): ReactElement {
  return (
    <g>
      <rect x={2} y={15} width={8} height={2} fill="rgba(42,34,56,.35)" />
      <Sprite art={BODY_TOP_DETECTIVE} palette={DETECTIVE} />
      <g className={walking ? 'legs legs-a walking' : 'legs legs-a'}><Sprite art={LEGS_A} palette={DETECTIVE} y={13} /></g>
      {walking && <g className="legs legs-b walking"><Sprite art={LEGS_B} palette={DETECTIVE} y={13} /></g>}
    </g>
  );
}

export const ALICE_ART = [
  '...HHHHHH...',
  '..HHHHHHHH..',
  '.HHHSSSSHHH.',
  '.HHSESSESHH.',
  '.HHSSSSSSHH.',
  '..HSSDDSSH..',
  '..HH.SS.HH..',
  '..MMMMMMMM..',
  '.MMMMWWMMMM.',
  '.SMMMMMMMMS.',
  '..MMMMMMMM..',
  '..MMMMMMMM..',
  '.MMMMMMMMMM.',
  '....SS.SS...',
  '....SS.SS...',
  '...BBB.BBB..',
];
export const ALICE: Palette = { H: C.hair, S: C.skin, E: C.ink, D: C.pinkDark, M: C.pink, W: C.white, B: C.ink };

export const BOB_ART = [
  '...RRRRR....',
  '..RRRRRRRR..',
  '..SSSSSSS...',
  '..SESSESS...',
  '..SSSSSSS...',
  '..BBSSSBB...',
  '...BBBBB....',
  '..WWWWWWWW..',
  '.WWAWWWWLWW.',
  '.SWWWWGWWWS.',
  '..WWWWWWWW..',
  '..WWLWWWAW..',
  '..WWWWWWWW..',
  '...PP..PP...',
  '...PP..PP...',
  '..KKK..KKK..',
];
export const BOB: Palette = { R: C.red, S: C.skin, E: C.ink, B: C.brown, W: C.white, A: C.water, L: C.gold, G: C.green, P: C.slate, K: C.ink };

export const ROBOT_ART = [
  '.....AA.....',
  '.....LL.....',
  '..GGGGGGGG..',
  '.GGSSSSSSGG.',
  '.GGSESSESGG.',
  '.GGSSSSSSGG.',
  '..GGGGGGGG..',
  '...DDDDDD...',
  '.GDGGGGGGDG.',
  '.GDGMMMMGDG.',
  '..DGGGGGGD..',
  '...GG..GG...',
  '..KKK..KKK..',
];
export const ROBOT: Palette = { A: C.red, L: C.ink, G: C.stone, S: C.screen, E: C.ink, D: C.slate, M: C.gold, K: C.ink };

export const ARCHIVIST_ART = [
  '...GGGGGG...',
  '..GGGGGGGG..',
  '..SSSSSSSS..',
  '..SOOSSOOS..',
  '..SSSSSSSS..',
  '...SSDDSS...',
  '..TTTTTTTT..',
  '.TTTTGGTTTT.',
  '.STTTTTTTTS.',
  '..TTTTTTTT..',
  '..TTTTTTTT..',
  '.TTTTTTTTTT.',
  '...KK..KK...',
];
export const ARCHIVIST: Palette = { G: C.grey, S: C.skin, O: C.ink, D: C.skinShade, T: C.tealDark, K: C.ink };

const CAT_ART = ['K.....K.', 'KK...KK.', 'KKKKKKK.', 'KEKKEKK.', 'KKKKKKKK', '.KKKKKKK', '.K.K.K.K'];
export function Cat(): ReactElement { return <Sprite art={CAT_ART} palette={{ K: C.ink, E: C.gold }} />; }

const COIN_ART = ['..GGGG..', '.GLLLLG.', 'GLGGGGLG', 'GLGDDGLG', 'GLGDDGLG', 'GLGGGGLG', '.GLLLLG.', '..GGGG..'];
export function Coin(): ReactElement { return <Sprite art={COIN_ART} palette={{ G: C.goldDark, L: C.light, D: C.gold }} />; }

const PARCEL_ART = ['.KKKKKKKK.', 'KWWWRRWWWK', 'KWWWRRWWWK', 'KRRRRRRRRK', 'KWWWRRWWWK', 'KWWWRRWWWK', '.KKKKKKKK.'];
export function Parcel(): ReactElement { return <Sprite art={PARCEL_ART} palette={{ K: C.ink, W: C.cream, R: C.gold }} />; }

const TREE_ART = [
  '....GGGG....', '..GGHGGGGG..', '.GGGGGGHGGG.', 'GGHGGGGGGGGG', 'GGGGGGHGGGHG', '.GGGHGGGGGG.',
  '..GGGGGGGG..', '....TTTT....', '.....TT.....', '.....TT.....',
];
export function Tree(): ReactElement { return <Sprite art={TREE_ART} palette={{ G: C.greenDark, H: C.green, T: C.woodDark }} />; }

const LAMP_ART = ['.KKK.', 'KLLLK', '.KKK.', '..K..', '..K..', '..K..', '..K..', '..K..', '.KKK.'];
export function Lamp(): ReactElement { return <Sprite art={LAMP_ART} palette={{ K: C.ink, L: C.light }} />; }
