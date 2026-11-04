// Movement along the town's streets, and the reduced-motion preference.
import { useEffect, useRef, useState } from 'react';
import { WAYPOINT } from './Scene';
import type { Place, PlayerSprite } from './Scene';

const MAIN_STREET_X = 90;
const MS_PER_PIXEL = 14;

export function useMediaQuery(media: string): boolean {
  const read = () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(media).matches : false);
  const [matches, setMatches] = useState(read);
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const query = window.matchMedia(media);
    const update = () => setMatches(query.matches);
    update();
    query.addEventListener?.('change', update);
    return () => query.removeEventListener?.('change', update);
  }, [media]);
  return matches;
}

export function usePrefersReducedMotion(): boolean {
  return useMediaQuery('(prefers-reduced-motion: reduce)');
}

/** Street route between two places: along the branch, the main street, the other branch. */
export function route(from: Place, to: Place): [number, number][] {
  const [fx, fy] = WAYPOINT[from];
  const [tx, ty] = WAYPOINT[to];
  if (from === to) return [[tx, ty]];
  const points: [number, number][] = [[MAIN_STREET_X, fy], [MAIN_STREET_X, ty], [tx, ty]];
  return points.filter(([x, y], i) => i === points.length - 1 || x !== fx || y !== fy);
}

/** Walks the player to `target`, one street segment at a time; calls `onArrive` at the end. */
export function useWalker(target: Place, reduced: boolean, onArrive: (place: Place) => void): PlayerSprite {
  const [player, setPlayer] = useState<PlayerSprite>(() => ({ x: WAYPOINT.plaza[0], y: WAYPOINT.plaza[1], facing: 1, walking: false, ms: 0 }));
  const at = useRef<Place>('plaza');
  const position = useRef<[number, number]>([...WAYPOINT.plaza]);
  const arrive = useRef(onArrive);
  arrive.current = onArrive;

  useEffect(() => {
    if (target === at.current) return;
    const points = route(at.current, target);
    const previous = { place: at.current, position: position.current };
    let finished = false;
    at.current = target;
    const timers: number[] = [];
    if (reduced) {
      const last = points[points.length - 1] ?? position.current;
      position.current = last;
      setPlayer({ x: last[0], y: last[1], facing: 1, walking: false, ms: 0 });
      arrive.current(target);
      return;
    }
    let delay = 0;
    points.forEach(([x, y]) => {
      const [px, py] = position.current;
      const ms = Math.max(120, (Math.abs(x - px) + Math.abs(y - py)) * MS_PER_PIXEL);
      const facing: 1 | -1 = x < px ? -1 : 1;
      timers.push(window.setTimeout(() => setPlayer({ x, y, facing, walking: true, ms }), delay));
      position.current = [x, y];
      delay += ms;
    });
    timers.push(window.setTimeout(() => {
      finished = true;
      setPlayer((old) => ({ ...old, walking: false, ms: 0 }));
      arrive.current(target);
    }, delay));
    return () => {
      timers.forEach((t) => window.clearTimeout(t));
      if (!finished) {
        // Interrupted (or StrictMode's double effect): forget the half-walked move.
        at.current = previous.place;
        position.current = previous.position;
      }
    };
  }, [target, reduced]);

  return player;
}
