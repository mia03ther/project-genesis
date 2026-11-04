import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactElement } from 'react';
import type { Result } from './api';
import { EvidenceBook } from './game/EvidenceBook';
import { route, useMediaQuery, usePrefersReducedMotion, useWalker } from './game/motion';
import { ArchivePanel, AtelierPanel, OutcomePanel, RelayPanel, StudioPanel, TerminalPanel, WarehousePanel } from './game/Places';
import { PLACES, Scene, WAYPOINT } from './game/Scene';
import type { ParcelSprite, Place } from './game/Scene';
import { HINT_ZH } from './game/text';
import { useLab } from './game/useLab';
import type { Lab } from './game/useLab';
import { Workshop } from './workshop/Workshop';

const DONE_BY: Record<string, string> = {
  studio: 'authorized-intent', relay: 'payment-request', atelier: 'field-comparison', archive: 'chain-accounts', terminal: 'transaction-draft',
};
const PARCEL_MS_PER_PIXEL = 18;

function objective(lab: Lab, playing = false): string {
  const s = lab.session;
  if (playing) return '观察包裹的去向：本地链正在执行两笔请求。';
  if (!s) return '开始调查：Alice 在设计工作室等你。';
  const has = (id: string) => Boolean(s.evidence.find((e) => e.id === id)?.inspected);
  if (s.stage === 'replayed') return lab.result?.passed ? '本关完成。可以恢复快照再玩一次。' : '实验没有守住意图：回溯快照，换一条规则重试。';
  if (!has('authorized-intent')) return '去 Alice 的设计工作室，查看她最初批准的付款。';
  if (!has('payment-request')) return '去支付中继站，读取支付 API 发来的请求。';
  if (!has('field-comparison')) return '去 Bob 的画室，逐段核对完整收款地址。';
  if (!has('chain-accounts')) return '去链上档案馆，查清请求里的地址属于谁。';
  if (s.stage === 'investigating') return '去钱包终端，选一条验证规则并锁定。';
  return '在钱包终端运行实验：两笔请求都会在本地链上真实执行。';
}

function useOutcome(result: Result | null, reduced: boolean) {
  const [parcels, setParcels] = useState<ParcelSprite[]>([]);
  const [revealed, setRevealed] = useState(0);
  const [playing, setPlaying] = useState(false);
  const timers = useRef<number[]>([]);

  const finalState = useCallback((r: Result): ParcelSprite[] => r.variants.map((v) => {
    const dest = destination(v.transaction?.to.label);
    const [x, y] = WAYPOINT[dest];
    return { id: v.id, x: x + (v.transaction ? 0 : v.id.length % 2 ? -8 : 8), y, state: v.transaction ? 'paid' : 'refused', ms: 0 };
  }), []);

  const skip = useCallback(() => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
    if (result) { setParcels(finalState(result)); setRevealed(result.variants.length); }
    setPlaying(false);
  }, [result, finalState]);

  useEffect(() => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
    if (!result) { setParcels([]); setRevealed(0); setPlaying(false); return; }
    if (reduced) { setParcels(finalState(result)); setRevealed(result.variants.length); setPlaying(false); return; }
    setPlaying(true);
    setRevealed(0);
    const [tx, ty] = WAYPOINT.terminal;
    setParcels([]);
    let delay = 200;
    const final = finalState(result);
    result.variants.forEach((v, index) => {
      const start: ParcelSprite = { id: v.id, x: tx, y: ty - 6, state: 'moving', ms: 0 };
      const at = (fn: () => void, ms: number) => timers.current.push(window.setTimeout(fn, ms));
      at(() => setParcels((old) => [...old.filter((p) => p.id !== v.id), start]), delay);
      delay += 250;
      if (v.transaction) {
        let [px, py] = [tx, ty];
        route('terminal', destination(v.transaction.to.label)).forEach(([x, y]) => {
          const ms = Math.max(200, (Math.abs(x - px) + Math.abs(y - py)) * PARCEL_MS_PER_PIXEL);
          at(() => setParcels((old) => old.map((p) => (p.id === v.id ? { ...p, x, y, ms } : p))), delay);
          delay += ms;
          [px, py] = [x, y];
        });
      } else {
        delay += 500;
      }
      const end = final[index];
      at(() => { setParcels((old) => old.map((p) => (p.id === v.id && end ? end : p))); setRevealed(index + 1); }, delay);
      delay += 600;
    });
    timers.current.push(window.setTimeout(() => setPlaying(false), delay));
    return () => timers.current.forEach((t) => window.clearTimeout(t));
  }, [result, reduced, finalState]);

  return { parcels, revealed, playing, skip };
}

function destination(label: string | null | undefined): Place {
  if (label === 'bob') return 'atelier';
  if (label === 'unknown') return 'warehouse';
  return 'terminal';
}

export function App(): ReactElement {
  const lab = useLab();
  const reduced = usePrefersReducedMotion();
  const narrow = useMediaQuery('(max-width: 899px)');
  const [target, setTarget] = useState<Place>('plaza');
  const [open, setOpen] = useState<Place | null>(null);
  const [book, setBook] = useState(false);
  const [workshop, setWorkshop] = useState(() => window.location.hash === '#workshop');
  useEffect(() => {
    if (workshop) window.history.replaceState(null, '', '#workshop');
    else if (window.location.hash === '#workshop') {
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
    }
  }, [workshop]);
  const player = useWalker(target, reduced, (place) => setOpen(place === 'plaza' ? null : place));
  const outcome = useOutcome(lab.result, reduced);
  const panelHeading = useRef<HTMLHeadingElement>(null);
  const hadSession = useRef(false);

  const go = useCallback((place: Place) => {
    if (place === target) { setOpen(place === 'plaza' ? null : place); return; }
    setOpen(null);
    setTarget(place);
  }, [target]);

  // A new case starts at Alice's studio; a resumed one at the next unvisited place.
  useEffect(() => {
    if (lab.session && !hadSession.current) {
      const seen = new Set(lab.session.evidence.filter((e) => e.inspected).map((e) => e.id));
      const next = (['studio', 'relay', 'atelier', 'archive'] as const).find((p) => !seen.has(DONE_BY[p] ?? ''));
      go(next ?? 'terminal');
    }
    hadSession.current = Boolean(lab.session);
  }, [lab.session, go]);
  // Restarting from the evidence book opens a new case at the studio too.
  const cases = useRef(lab.cases);
  useEffect(() => {
    if (lab.cases > cases.current && hadSession.current) go('studio');
    cases.current = lab.cases;
  }, [lab.cases, go]);

  // A fresh result plays out from the wallet terminal. On a phone the sheet would cover
  // the town, so it waits until the parcels have arrived.
  useEffect(() => {
    if (!lab.result) return;
    setOpen(narrow && outcome.playing ? null : 'terminal');
  }, [lab.result, narrow, outcome.playing]);

  useEffect(() => { if (open) panelHeading.current?.focus(); }, [open]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape' && open && !book) setOpen(null); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, book]);

  const session = lab.session;
  const evidenceDone = session?.evidence.filter((e) => e.inspected).length ?? 0;
  const evidenceTotal = session?.evidence.length ?? 5;
  const revealed = Boolean(lab.evidence['chain-accounts']) || outcome.parcels.some((p) => p.state !== 'refused' && p.x === WAYPOINT.warehouse[0]);
  const done = useMemo(() => {
    const out: Record<string, boolean> = {};
    for (const [place, id] of Object.entries(DONE_BY)) out[place] = Boolean(session?.evidence.find((e) => e.id === id)?.inspected);
    return out;
  }, [session]);
  const plaques = useMemo(() => {
    const out: Record<string, string> = {};
    const chain = lab.evidence['chain-accounts']?.content as { accounts?: { label: string; preview: string }[] } | undefined;
    const intent = lab.evidence['authorized-intent']?.content as { recipient?: { preview: string } } | undefined;
    const bob = chain?.accounts?.find((a) => a.label === 'bob')?.preview ?? intent?.recipient?.preview;
    if (bob) out.atelier = bob;
    const flagged = chain?.accounts?.find((a) => a.label === 'unknown')?.preview;
    if (flagged) out.warehouse = flagged;
    return out;
  }, [lab.evidence]);
  const mood = !lab.result || outcome.playing ? 'idle' : lab.result.passed ? 'pass' : 'fail';
  const info = PLACES.find((p) => p.id === open);

  let panel: ReactElement | null = null;
  if (open && session) {
    if (open === 'terminal' && lab.result) panel = <OutcomePanel lab={lab} result={lab.result} revealed={outcome.revealed} playing={outcome.playing} onSkip={outcome.skip} onBook={() => setBook(true)} />;
    else if (open === 'studio') panel = <StudioPanel lab={lab} onGo={go} />;
    else if (open === 'relay') panel = <RelayPanel lab={lab} onGo={go} />;
    else if (open === 'atelier') panel = <AtelierPanel lab={lab} onGo={go} />;
    else if (open === 'archive') panel = <ArchivePanel lab={lab} onGo={go} />;
    else if (open === 'warehouse') panel = <WarehousePanel lab={lab} onGo={go} />;
    else if (open === 'terminal') panel = <TerminalPanel key={`${session.attempt}-${session.stage}`} lab={lab} />;
  }

  if (workshop) return <Workshop onClose={() => setWorkshop(false)} />;

  return (
    <div className="app">
      <header className="hud">
        <div className="brand"><span className="logo" aria-hidden="true" />GENESIS<span className="level">第一关 · 错付疑云</span></div>
        <p className="objective" aria-live="polite"><span className="tag">目标</span>{objective(lab, outcome.playing)}</p>
        <div className="hud-actions">
          <button type="button" className="btn small" disabled={Boolean(lab.busy) || outcome.playing} onClick={() => setWorkshop(true)}>合约工坊</button>
          <span className="progress" aria-label={`调查进度 ${evidenceDone}/${evidenceTotal}`}>
            {Array.from({ length: evidenceTotal }, (_, i) => <span key={i} className={i < evidenceDone ? 'pip on' : 'pip'} />)}
            <span className="count">{evidenceDone}/{evidenceTotal}</span>
          </span>
          <button type="button" className="btn small" disabled={!session || Boolean(lab.busy) || !session.allowed.hint} onClick={() => void lab.hint()}>
            💡 提示 {session ? `${session.hints.revealed.length}/${session.hints.total}` : ''}
          </button>
          <button type="button" className="btn small" disabled={!session} onClick={() => setBook(true)}>📒 证据册</button>
        </div>
      </header>

      <main className="stage">
        <div className="scene-wrap">
          <Scene
            player={player}
            active={open}
            revealed={revealed}
            done={done}
            plaques={plaques}
            mood={mood}
            parcels={outcome.parcels}
            disabled={!session || player.walking}
            onSelect={go}
          />
          {!session && lab.loaded && (
            <div className="title-card">
              <p className="kicker">GENESIS · Web3 安全像素调查</p>
              <h1>错付疑云<span>{lab.mission?.title ?? 'The Wrong Recipient'}</span></h1>
              <p>一笔已经批准的付款，一条看起来没问题的付款请求。签名之前，查清楚它到底要付给谁。</p>
              <button type="button" className="btn primary big" disabled={Boolean(lab.busy) || !lab.mission} onClick={() => void lab.start()}>
                {lab.busy === 'start' ? '正在布置本地链…' : '开始调查'}
              </button>
              <p className="fine">全部资产均为本地 Anvil 测试链上的合成资产 · 不连接钱包或公共链</p>
            </div>
          )}
          {!lab.loaded && <div className="title-card"><p className="kicker">正在连接本地实验服务…</p></div>}
          {narrow && outcome.playing && (
            <div className="hint-toast playback" role="status">
              <p>本地链正在执行两笔请求：包裹的去向就是真实的转账结果。</p>
              <button type="button" className="btn small" onClick={outcome.skip}>跳过动画，直接看结果</button>
            </div>
          )}
          {lab.lastHint && (
            <div className="hint-toast" role="status">
              <strong>侦探笔记 · 提示 {session?.hints.revealed.length}/{session?.hints.total}</strong>
              <p>{HINT_ZH[lab.lastHint] ?? lab.lastHint}</p>
              <button type="button" className="btn small" onClick={lab.dismissHint}>知道了</button>
            </div>
          )}
        </div>

        <aside className={`panel${panel ? ' open' : ''}`} aria-label="对话与调查">
          {panel && info ? (
            <>
              <div className="panel-head">
                <h2 tabIndex={-1} ref={panelHeading}>{info.name}</h2>
                <button type="button" className="btn ghost small" onClick={() => setOpen(null)}>回到街区</button>
              </div>
              <div className="panel-body">{panel}</div>
            </>
          ) : session ? (
            <div className="panel-idle">
              <p>点击街区里的地点，侦探会走过去。</p>
              <p className="note">{objective(lab, outcome.playing)}</p>
            </div>
          ) : null}
        </aside>
      </main>

      {lab.error && (
        <div className="error-banner" role="alert">
          <p>{lab.error.message}</p>
          {lab.error.recover === 'reload' && <p className="note">本地服务启动方式：在项目根目录运行 <code>.\.venv\Scripts\python.exe -m genesis.lab</code>（需要 Anvil）。</p>}
          <div className="row">
            {lab.error.recover === 'reload' && <button type="button" className="btn primary small" disabled={Boolean(lab.busy)} onClick={() => void lab.load()}>重新连接</button>}
            {lab.error.recover === 'refresh' && <button type="button" className="btn primary small" disabled={Boolean(lab.busy)} onClick={() => void lab.load()}>同步最新状态</button>}
            {lab.error.recover === 'start' && <button type="button" className="btn primary small" disabled={Boolean(lab.busy)} onClick={() => void lab.start()}>重新开始调查</button>}
            <button type="button" className="btn ghost small" onClick={lab.dismissError}>关闭</button>
          </div>
        </div>
      )}

      {book && <EvidenceBook lab={lab} onClose={() => setBook(false)} />}
    </div>
  );
}
