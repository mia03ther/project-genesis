// Step through two complete addresses four hex digits at a time. Differences come from
// the backend's comparison (differing_positions); the UI only reveals them gradually.
import { useEffect, useState } from 'react';
import type { ReactElement } from 'react';

const GROUP = 4;
const GROUPS = 40 / GROUP;

export function extractAddress(text: string): string {
  return text.match(/0x[0-9a-fA-F]{40}/)?.[0]?.toLowerCase() ?? text;
}

export function CopyButton({ text, label }: { text: string; label: string }): ReactElement {
  const [state, setState] = useState<'idle' | 'done' | 'failed'>('idle');
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setState('done');
    } catch {
      setState('failed');
    }
  };
  return (
    <button type="button" className="mini" onClick={() => void copy()} aria-label={`复制${label}`}>
      {state === 'done' ? '已复制' : state === 'failed' ? '请长按选择复制' : '复制'}
    </button>
  );
}

function Hex({ address, positions, upTo, tone }: { address: string; positions: Set<number>; upTo: number; tone: 'auth' | 'req' }): ReactElement {
  const digits = address.slice(2);
  const groups = [];
  for (let g = 0; g < GROUPS; g += 1) {
    const shown = g < upTo;
    const chars = [];
    for (let i = 0; i < GROUP; i += 1) {
      const position = g * GROUP + i + 1;
      const differs = shown && positions.has(position);
      chars.push(<span key={i} className={differs ? `diff ${tone}` : undefined}>{digits[position - 1]}</span>);
    }
    groups.push(<span key={g} className={`grp${shown ? ' shown' : ''}${g === upTo - 1 ? ' cursor' : ''}`}>{chars}</span>);
  }
  return <span className="hex"><span className="pre">0x</span>{groups}</span>;
}

export function AddressCompare({ authorized, requested, positions, authorizedPreview, requestedPreview, onReveal }: {
  authorized: string; requested: string; positions: number[]; authorizedPreview: string; requestedPreview: string;
  /** Called once the player has reached the first difference, or checked all 40 digits. */
  onReveal?: () => void;
}): ReactElement {
  const [upTo, setUpTo] = useState(0);
  const wrong = new Set(positions);
  const firstBad = positions.length ? Math.ceil(Math.min(...positions) / GROUP) : null;
  const found = firstBad !== null && upTo >= firstBad;
  const done = upTo >= GROUPS;
  useEffect(() => { if (found || done) onReveal?.(); }, [found, done, onReveal]);
  return (
    <div className="compare">
      <div className="compare-row preview-row">
        <span className="tag">钱包预览</span>
        <code>{authorizedPreview}</code>
        <code>{requestedPreview}</code>
        <span className={authorizedPreview === requestedPreview ? 'same' : 'differs'}>{authorizedPreview === requestedPreview ? '看起来一样' : '预览就不同'}</span>
      </div>
      <div className="compare-row">
        <span className="tag auth">Alice 授权</span>
        <Hex address={authorized} positions={wrong} upTo={upTo} tone="auth" />
        <CopyButton text={authorized} label="授权地址" />
      </div>
      <div className="compare-row">
        <span className="tag req">API 请求</span>
        <Hex address={requested} positions={wrong} upTo={upTo} tone="req" />
        <CopyButton text={requested} label="请求地址" />
      </div>
      <p className="compare-status" aria-live="polite">
        {upTo === 0 && '从第 1 段开始，每段 4 位十六进制。'}
        {upTo > 0 && !found && !done && `第 ${upTo} 段一致（${upTo * GROUP}/40 位）。`}
        {found && `第 ${firstBad} 段出现不同：第 ${positions.join('、')} 位不一样。这是另一个完整地址。`}
        {done && !positions.length && '40 位全部一致：这是同一个地址。'}
      </p>
      <div className="row">
        <button type="button" className="btn" onClick={() => setUpTo((n) => Math.min(GROUPS, n + 1))} disabled={done}>
          {upTo === 0 ? '开始逐段核对' : '下一段 →'}
        </button>
        <button type="button" className="btn ghost" onClick={() => setUpTo(GROUPS)} disabled={done}>全部展开</button>
      </div>
    </div>
  );
}
