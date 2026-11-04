// The evidence book: collected cards, attempt history and technical details, kept out
// of the scene until the player opens it.
import { useEffect, useRef, useState } from 'react';
import type { ReactElement } from 'react';
import { EvidenceBody, evidenceTitle } from './cards';
import { CHOICE_ZH } from './text';
import type { Lab } from './useLab';

const WHERE: Record<string, string> = {
  'authorized-intent': 'Alice 的设计工作室',
  'payment-request': '支付中继站',
  'field-comparison': 'Bob 的画室',
  'chain-accounts': '链上档案馆',
  'transaction-draft': '钱包终端',
};

type Tab = 'cards' | 'history' | 'tech';

export function EvidenceBook({ lab, onClose }: { lab: Lab; onClose: () => void }): ReactElement {
  const [tab, setTab] = useState<Tab>('cards');
  const [confirmRestart, setConfirmRestart] = useState(false);
  const dialog = useRef<HTMLDivElement>(null);
  const session = lab.session;

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.querySelector<HTMLElement>('button')?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key !== 'Tab' || !dialog.current) return;
      const focusable = [...dialog.current.querySelectorAll<HTMLElement>('button:not([disabled]), summary, [href], input')];
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); previous?.focus?.(); };
  }, [onClose]);

  return (
    <div className="backdrop" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="book" role="dialog" aria-modal="true" aria-labelledby="book-title" ref={dialog}>
        <header className="book-head">
          <h2 id="book-title">证据册</h2>
          <button type="button" className="btn ghost close" onClick={onClose} aria-label="关闭证据册">关闭</button>
        </header>
        <div className="tabs" role="tablist">
          {([['cards', '证据卡'], ['history', '尝试记录'], ['tech', '技术详情']] as [Tab, string][]).map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={tab === id} className={tab === id ? 'tab on' : 'tab'} onClick={() => setTab(id)}>{label}</button>
          ))}
        </div>
        <div className="book-body">
          {tab === 'cards' && session?.evidence.map((e) => {
            const item = lab.evidence[e.id];
            return (
              <section key={e.id} className={`evidence-card${item ? '' : ' missing'}`}>
                <h3>{item ? '📄' : '❔'} {evidenceTitle(e.id, e.title)}</h3>
                {item
                  ? <><EvidenceBody item={item} /><details className="raw"><summary>原始 JSON</summary><pre>{JSON.stringify(item.content, null, 2)}</pre></details></>
                  : <p className="note">{e.locked ? '还需要先收集其他证据。' : '尚未收集。'}去 {WHERE[e.id] ?? '街区'} 看看。</p>}
              </section>
            );
          })}
          {tab === 'history' && (
            session?.history.length
              ? <ol className="history">{session.history.map((h) => <li key={h.attempt} className={h.passed ? 'ok' : 'bad'}>第 {h.attempt} 次 · {CHOICE_ZH[h.choice]?.label ?? h.label} · {h.passed ? '通过' : '未通过'}</li>)}</ol>
              : <p className="note">还没有运行过实验。在钱包终端选择规则后运行。</p>
          )}
          {tab === 'tech' && session && (
            <>
              <p className="note">本地链 {session.chain.chain_id} · 区块 #{session.chain.block_number}{session.chain.client_version ? ` · ${session.chain.client_version}` : ''} · 阶段 {session.stage} · 第 {session.attempt} 次</p>
              <div className="row">
                <button type="button" className="btn" disabled={Boolean(lab.busy) || !session.history.length} onClick={() => void lab.report()}>
                  {lab.busy === 'report' ? '正在生成…' : '下载 JSON 报告'}
                </button>
                <button type="button" className="btn ghost" disabled={Boolean(lab.busy)} onClick={() => {
                  if (!confirmRestart) { setConfirmRestart(true); return; }
                  setConfirmRestart(false);
                  void lab.start();
                  onClose();
                }}>{confirmRestart ? '确认：清空证据，重新开始' : '重新开始整个调查'}</button>
              </div>
              <h3>后端时间线</h3>
              <ol className="timeline">
                {session.timeline.map((t) => <li key={t.seq}><span className="seq">#{t.seq} · 第 {t.attempt} 次</span><strong>{t.title}</strong><p>{t.detail}</p></li>)}
              </ol>
              {lab.mission && (
                <details className="raw"><summary>信任边界与说明</summary>
                  <p>{lab.mission.trust_boundary.summary}</p>
                  <ul>{lab.mission.trust_boundary.steps.map((s) => <li key={s.actor}><strong>{s.actor}</strong>（{s.trust}）：{s.note}</li>)}</ul>
                  <p>{lab.mission.trust_boundary.disclaimer}</p>
                </details>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
