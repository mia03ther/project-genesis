// The pixel town: one SVG (180 x 240 pixels) plus accessible HTML hotspots over it.
import type { ReactElement } from 'react';
import { ALICE, ALICE_ART, ARCHIVIST, ARCHIVIST_ART, BOB, BOB_ART, Block, C, Cat, Coin, Detective, Lamp, Parcel, ROBOT, ROBOT_ART, Sprite, Tree } from './pixel';

export const WIDTH = 180;
export const HEIGHT = 240;

export type Place = 'plaza' | 'studio' | 'relay' | 'atelier' | 'terminal' | 'archive' | 'warehouse';

export const WAYPOINT: Record<Place, readonly [number, number]> = {
  plaza: [90, 112],
  studio: [37, 67],
  relay: [140, 67],
  atelier: [35, 151],
  terminal: [128, 151],
  archive: [64, 217],
  warehouse: [137, 217],
};

export interface PlaceInfo { id: Exclude<Place, 'plaza'>; name: string; who: string; box: [number, number, number, number] }
export const PLACES: PlaceInfo[] = [
  { id: 'studio', name: 'Alice 的设计工作室', who: 'Alice', box: [6, 6, 62, 54] },
  { id: 'relay', name: '支付中继站', who: '中继机器人', box: [110, 2, 64, 58] },
  { id: 'atelier', name: 'Bob 的画室', who: 'Bob', box: [4, 90, 62, 54] },
  { id: 'terminal', name: '钱包终端', who: '钱包终端', box: [110, 102, 54, 44] },
  { id: 'archive', name: '链上档案馆', who: '档案员', box: [42, 156, 46, 58] },
  { id: 'warehouse', name: '无主仓库', who: '无主仓库', box: [108, 172, 62, 42] },
];

export interface ParcelSprite { id: string; x: number; y: number; state: 'moving' | 'paid' | 'refused'; ms: number }
export interface PlayerSprite { x: number; y: number; facing: 1 | -1; walking: boolean; ms: number }

const pct = (value: number, total: number) => `${(value / total) * 100}%`;

function Grass(): ReactElement {
  const tufts: ReactElement[] = [];
  for (let i = 0; i < 170; i += 1) {
    const x = (i * 37 + (i % 7) * 11) % 178;
    const y = (i * 53 + (i % 5) * 7) % 238;
    tufts.push(<rect key={i} x={x} y={y} width={i % 3 === 0 ? 2 : 1} height={1} fill={i % 4 === 0 ? C.grassDark : C.grass2} />);
  }
  const flowers: ReactElement[] = [];
  const spots: [number, number][] = [[14, 80], [60, 84], [116, 84], [168, 96], [6, 128], [104, 132], [170, 132], [12, 166], [38, 172], [100, 168], [168, 168], [8, 224], [40, 228], [96, 232], [160, 232], [174, 200]];
  spots.forEach(([x, y], i) => {
    flowers.push(<rect key={`f${i}`} x={x} y={y} width={1} height={1} fill={i % 2 ? C.flower1 : C.flower2} />, <rect key={`g${i}`} x={x} y={y + 1} width={1} height={1} fill={C.grassDark} />);
  });
  return <g><rect width={WIDTH} height={HEIGHT} fill={C.grass} />{tufts}{flowers}</g>;
}

function Paths(): ReactElement {
  const stones: ReactElement[] = [];
  const lanes: [number, number, number, number][] = [[82, 66, 16, 162], [20, 62, 142, 10], [18, 146, 136, 10], [48, 212, 104, 10]];
  lanes.forEach(([x, y, w, h], li) => {
    for (let sx = x + 2; sx < x + w - 2; sx += 6) for (let sy = y + 2; sy < y + h - 1; sy += 4) {
      if ((sx + sy + li) % 3 === 0) stones.push(<rect key={`${li}-${sx}-${sy}`} x={sx} y={sy} width={2} height={1} fill={C.path2} />);
    }
  });
  return (
    <g>
      {lanes.map(([x, y, w, h], i) => <rect key={`e${i}`} x={x - 1} y={y - 1} width={w + 2} height={h + 2} fill={C.pathEdge} />)}
      {lanes.map(([x, y, w, h], i) => <rect key={`p${i}`} x={x} y={y} width={w} height={h} fill={C.path} />)}
      <rect x={67} y={94} width={46} height={34} fill={C.pathEdge} />
      <rect x={68} y={95} width={44} height={32} fill={C.path} />
      {stones}
    </g>
  );
}

function Fountain(): ReactElement {
  return (
    <g>
      <Block x={80} y={100} w={20} h={10} fill={C.stone} />
      <rect x={82} y={102} width={16} height={6} fill={C.water} />
      <rect x={89} y={96} width={2} height={6} fill={C.stone} />
      <rect className="sparkle" x={88} y={94} width={4} height={2} fill={C.white} />
      <rect className="sparkle delay" x={84} y={103} width={2} height={1} fill={C.white} />
    </g>
  );
}

function Roof({ x, y, w, h, fill, dark }: { x: number; y: number; w: number; h: number; fill: string; dark: string }): ReactElement {
  const rows: ReactElement[] = [];
  for (let i = 0; i < h; i += 1) {
    const inset = Math.max(0, Math.floor((h - i) / 2) - 1);
    rows.push(<rect key={i} x={x + inset} y={y + i} width={w - inset * 2} height={1} fill={i % 3 === 2 ? dark : fill} />);
  }
  return <g><rect x={x + Math.floor(h / 2) - 2} y={y - 1} width={w - (Math.floor(h / 2) - 2) * 2} height={1} fill={C.ink} />{rows}<rect x={x - 1} y={y + h} width={w + 2} height={1} fill={C.ink} /></g>;
}

function Window({ x, y, w, h, lit = true }: { x: number; y: number; w: number; h: number; lit?: boolean }): ReactElement {
  return (
    <g>
      <Block x={x} y={y} w={w} h={h} fill={lit ? C.light : C.glass} />
      <rect x={x + Math.floor(w / 2)} y={y} width={1} height={h} fill={C.woodDark} />
      <rect x={x} y={y + Math.floor(h / 2)} width={w} height={1} fill={C.woodDark} />
      <rect x={x - 1} y={y + h + 1} width={w + 2} height={1} fill={C.woodDark} />
    </g>
  );
}

function Door({ x, y, fill = C.wood }: { x: number; y: number; fill?: string }): ReactElement {
  return <g><Block x={x} y={y} w={8} h={12} fill={fill} /><rect x={x + 6} y={y + 6} width={1} height={1} fill={C.gold} /><rect x={x + 1} y={y + 1} width={6} height={1} fill={C.woodDark} /></g>;
}

function Studio(): ReactElement {
  return (
    <g>
      <rect className="smoke" x={53} y={2} width={3} height={2} fill={C.white} opacity={0.7} />
      <rect className="smoke delay" x={56} y={0} width={2} height={2} fill={C.white} opacity={0.5} />
      <Block x={52} y={8} w={6} h={10} fill={C.pinkDark} />
      <Block x={10} y={31} w={54} h={28} fill={C.cream} />
      {[35, 40, 45, 50, 55].map((yy) => <rect key={yy} x={10} y={yy} width={54} height={1} fill={C.creamShade} />)}
      <Roof x={8} y={14} w={58} h={17} fill={C.pink} dark={C.pinkDark} />
      <Window x={15} y={37} w={13} h={9} />
      <Window x={46} y={37} w={13} h={9} />
      <rect x={17} y={41} width={4} height={4} fill={C.pink} />
      <Block x={28} y={40} w={18} h={5} fill={C.wood} />
      <rect x={30} y={42} width={14} height={1} fill={C.light} />
      <Door x={33} y={47} />
      <Block x={12} y={50} w={8} h={8} fill={C.greenDark} />
      <rect x={13} y={49} width={2} height={2} fill={C.flower1} /><rect x={17} y={49} width={2} height={2} fill={C.flower2} />
    </g>
  );
}

function Relay(): ReactElement {
  return (
    <g>
      <rect x={158} y={6} width={2} height={19} fill={C.slateDark} />
      <rect x={150} y={13} width={10} height={1} fill={C.slateDark} />
      <Sprite art={['..KKKK..', '.KSSSSK.', 'KSSSSSSK', '.KSSSSK.', '..KKKK..']} palette={{ K: C.ink, S: C.stone }} x={146} y={6} />
      <rect className="blink" x={158} y={3} width={2} height={2} fill={C.red} />
      <Block x={113} y={31} w={56} h={28} fill={C.slate} />
      <rect x={113} y={24} width={56} height={7} fill={C.teal} />
      <rect x={112} y={23} width={58} height={1} fill={C.ink} />
      <rect x={113} y={29} width={56} height={1} fill={C.tealDark} />
      {[118, 152].map((xx) => <g key={xx}><Block x={xx} y={36} w={12} h={7} fill={C.screenDark} /><rect className="scan" x={xx + 1} y={38} width={8} height={1} fill={C.screen} /><rect x={xx + 1} y={40} width={5} height={1} fill={C.screen} /></g>)}
      <Block x={128} y={36} w={20} h={5} fill={C.slateDark} />
      <rect x={130} y={38} width={16} height={1} fill={C.gold} />
      <Door x={136} y={47} fill={C.slateDark} />
      <rect x={116} y={50} width={14} height={8} fill={C.slateDark} />
      <rect x={117} y={51} width={4} height={3} fill={C.cream} /><rect x={122} y={51} width={4} height={3} fill={C.cream} /><rect x={119} y={55} width={4} height={3} fill={C.cream} />
    </g>
  );
}

function Atelier(): ReactElement {
  return (
    <g>
      <Block x={9} y={117} w={52} h={26} fill={C.cream} />
      {[121, 126, 131, 136].map((yy) => <rect key={yy} x={9} y={yy} width={52} height={1} fill={C.creamShade} />)}
      <Roof x={7} y={100} w={56} h={17} fill={C.green} dark={C.greenDark} />
      <Block x={13} y={122} w={15} h={11} fill={C.glass} />
      <rect x={15} y={124} width={8} height={7} fill={C.white} />
      <rect x={16} y={126} width={3} height={2} fill={C.pink} /><rect x={19} y={127} width={3} height={2} fill={C.water} />
      <Door x={31} y={131} />
      <Block x={41} y={124} w={10} h={4} fill={C.gold} />
      <Window x={53} y={122} w={6} h={7} />
      <Sprite art={['..K..K..', '..KWWK..', '.KWPWWK.', '.KWWBWK.', '..KWWK..', '.K....K.', 'K......K']} palette={{ K: C.woodDark, W: C.white, P: C.pink, B: C.water }} x={0} y={134} />
      <g transform="translate(14 95)"><Cat /></g>
    </g>
  );
}

function Terminal({ mood }: { mood: 'idle' | 'pass' | 'fail' }): ReactElement {
  const screen = mood === 'pass' ? C.green : mood === 'fail' ? C.red : C.screen;
  return (
    <g>
      <Block x={114} y={140} w={46} h={4} fill={C.stone} />
      <Sprite art={['RWRWRWRWRWRWRWRWRWRWRWRWRWRWRW']} palette={{ R: C.red, W: C.white }} x={115} y={108} />
      <Sprite art={['RWRWRWRWRWRWRWRWRWRWRWRWRWRWRW']} palette={{ R: C.white, W: C.red }} x={115} y={109} />
      <rect x={114} y={110} width={32} height={1} fill={C.ink} />
      <Block x={120} y={114} w={20} h={26} fill={C.slate} />
      <Block x={123} y={117} w={14} h={10} fill={C.ink} />
      <rect className={mood === 'idle' ? 'scan' : ''} x={124} y={118} width={12} height={8} fill={screen} opacity={0.85} />
      <rect x={125} y={120} width={8} height={1} fill={C.ink} /><rect x={125} y={123} width={5} height={1} fill={C.ink} />
      {[0, 1, 2].map((r) => [0, 1, 2].map((c) => <rect key={`${r}${c}`} x={124 + c * 4} y={130 + r * 3} width={3} height={2} fill={C.stone} />))}
      <Block x={146} y={128} w={12} h={4} fill={C.wood} />
      <rect x={147} y={132} width={1} height={8} fill={C.woodDark} /><rect x={156} y={132} width={1} height={8} fill={C.woodDark} />
    </g>
  );
}

function Archive(): ReactElement {
  return (
    <g>
      <Block x={49} y={177} w={30} h={36} fill={C.stone} />
      {[182, 188, 194, 200, 206].map((yy, i) => <g key={yy}><rect x={49} y={yy} width={30} height={1} fill={C.slate} />{[0, 1, 2].map((k) => <rect key={k} x={52 + k * 9 + (i % 2) * 4} y={yy - 5} width={1} height={5} fill={C.slate} />)}</g>)}
      <Roof x={46} y={160} w={36} h={17} fill={C.slate} dark={C.slateDark} />
      <rect className="blink slow" x={63} y={156} width={2} height={3} fill={C.gold} />
      {[0, 1, 2].map((i) => <g key={i}><Block x={53 + i * 8} y={183} w={6} h={5} fill={C.gold} />{i < 2 && <rect x={59 + i * 8} y={185} width={2} height={1} fill={C.goldDark} />}</g>)}
      <Door x={60} y={201} fill={C.slateDark} />
    </g>
  );
}

function Warehouse({ revealed }: { revealed: boolean }): ReactElement {
  if (!revealed) {
    const posts: ReactElement[] = [];
    for (let x = 110; x <= 166; x += 6) posts.push(<rect key={x} x={x} y={196} width={2} height={12} fill={C.woodDark} />);
    return (
      <g>
        <rect x={110} y={199} width={58} height={2} fill={C.wood} /><rect x={110} y={204} width={58} height={2} fill={C.wood} />
        {posts}
        <Block x={134} y={184} w={8} h={8} fill={C.cream} />
        <Sprite art={['.KKK.', 'K...K', '...K.', '..K..', '.....', '..K..']} palette={{ K: C.ink }} x={135} y={185} />
        <rect x={137} y={192} width={2} height={6} fill={C.woodDark} />
      </g>
    );
  }
  return (
    <g>
      <Block x={113} y={187} w={50} h={26} fill={C.grey} />
      {[192, 198, 204].map((yy) => <rect key={yy} x={113} y={yy} width={50} height={1} fill={C.greyDark} />)}
      <rect x={112} y={180} width={52} height={7} fill={C.greyDark} />
      <rect x={111} y={179} width={54} height={1} fill={C.ink} />
      <Block x={132} y={197} w={11} h={16} fill={C.greyDark} />
      {[199, 202, 205, 208, 211].map((yy) => <rect key={yy} x={132} y={yy} width={11} height={1} fill={C.grey} />)}
      <Block x={146} y={191} w={10} h={4} fill={C.gold} />
      <Window x={117} y={192} w={8} h={6} lit={false} />
    </g>
  );
}

export interface SceneProps {
  player: PlayerSprite;
  active: Place | null;
  revealed: boolean;
  done: Record<string, boolean>;
  plaques: Record<string, string>;
  mood: 'idle' | 'pass' | 'fail';
  parcels: ParcelSprite[];
  disabled: boolean;
  onSelect: (place: Exclude<Place, 'plaza'>) => void;
}

export function Scene({ player, active, revealed, done, plaques, mood, parcels, disabled, onSelect }: SceneProps): ReactElement {
  return (
    <div className="scene" style={{ aspectRatio: `${WIDTH} / ${HEIGHT}` }}>
      <svg className="town" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} shapeRendering="crispEdges" role="img" aria-label="像素街区：设计工作室、支付中继站、画室、钱包终端、链上档案馆">
        <Grass />
        <Paths />
        <Fountain />
        {[[2, 72], [166, 76], [102, 116], [2, 160], [166, 158], [10, 182], [26, 202], [166, 222]].map(([x, y]) => <g key={`${x}-${y}`} transform={`translate(${x} ${y})`}><Tree /></g>)}
        {[[74, 72], [103, 72], [74, 136], [103, 136]].map(([x, y]) => <g key={`l${x}-${y}`} transform={`translate(${x} ${y})`}><Lamp /></g>)}
        <Studio />
        <Relay />
        <Atelier />
        <Terminal mood={mood} />
        <Archive />
        <Warehouse revealed={revealed} />
        <g transform="translate(20 43)"><Sprite art={ALICE_ART} palette={ALICE} /></g>
        <g transform="translate(43 127)"><Sprite art={BOB_ART} palette={BOB} /></g>
        <g transform="translate(118 46)"><Sprite art={ROBOT_ART} palette={ROBOT} /></g>
        <g transform="translate(70 200)"><Sprite art={ARCHIVIST_ART} palette={ARCHIVIST} /></g>
        {parcels.map((p) => (
          <g key={p.id} className={`parcel ${p.state}`} style={{ transform: `translate(${p.x - 5}px, ${p.y - 7}px)`, transitionDuration: `${p.ms}ms` }}>
            {p.state === 'refused' ? <Parcel /> : <g transform="translate(1 -1)"><Coin /></g>}
            {p.state === 'refused' && <Sprite art={['KK..KK', '.KKKK.', '..KK..', '.KKKK.', 'KK..KK']} palette={{ K: C.red }} x={2} y={1} />}
          </g>
        ))}
        <g className="player" style={{ transform: `translate(${player.x - 6}px, ${player.y - 15}px)`, transitionDuration: `${player.ms}ms` }}>
          <g style={{ transform: player.facing === -1 ? 'translateX(12px) scaleX(-1)' : undefined }}><Detective walking={player.walking} /></g>
        </g>
      </svg>
      {PLACES.map((place) => {
        if (place.id === 'warehouse' && !revealed) return null;
        const [x, y, w, h] = place.box;
        const plaque = plaques[place.id];
        return (
          <button
            key={place.id}
            type="button"
            className={`hotspot${active === place.id ? ' active' : ''}${done[place.id] ? ' done' : ''}`}
            style={{ left: pct(x, WIDTH), top: pct(y, HEIGHT), width: pct(w, WIDTH), height: pct(h, HEIGHT) }}
            onClick={() => onSelect(place.id)}
            disabled={disabled}
            aria-label={`${place.name}${done[place.id] ? '（已调查）' : ''}`}
          >
            <span className="plate">{done[place.id] && <span aria-hidden="true">✓ </span>}{place.name}</span>
            {plaque && <span className="plaque">{plaque}</span>}
          </button>
        );
      })}
    </div>
  );
}
