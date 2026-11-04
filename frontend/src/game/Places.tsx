// What happens at each place: character lines, the backend action available there,
// and the evidence it yields. Facts are always taken from backend responses.
import { useState } from 'react';
import type { ReactElement, ReactNode } from 'react';
import type { AuthorizationContent, ChainContent, ComparisonContent, EvidenceItem, RequestContent, Result, TransactionContent, VariantResult } from '../api';
import { AddressCompare, extractAddress } from './AddressCompare';
import { AuthorizationCard, ChainCard, ComparisonFields, RequestCard, TransactionCard } from './cards';
import { ALICE, ALICE_ART, ARCHIVIST, ARCHIVIST_ART, BOB, BOB_ART, C, Detective, ROBOT, ROBOT_ART, Sprite } from './pixel';
import type { Palette } from './pixel';
import type { Place } from './Scene';
import { CHECK_ZH, CHOICE_ZH, ether, VARIANT_ZH, zh } from './text';
import type { Lab } from './useLab';

export function Portrait({ who }: { who: 'alice' | 'bob' | 'robot' | 'archivist' | 'terminal' | 'detective' }): ReactElement {
  const art: Record<string, [readonly string[], Palette]> = {
    alice: [ALICE_ART, ALICE], bob: [BOB_ART, BOB], robot: [ROBOT_ART, ROBOT], archivist: [ARCHIVIST_ART, ARCHIVIST],
  };
  const chosen = art[who];
  return (
    <svg className="portrait" viewBox="-2 -2 16 20" shapeRendering="crispEdges" aria-hidden="true">
      <rect x={-2} y={-2} width={16} height={20} fill={C.cream} />
      {chosen ? <Sprite art={chosen[0]} palette={chosen[1]} /> : who === 'terminal'
        ? <g><rect x={1} y={2} width={10} height={14} fill={C.slate} /><rect x={2} y={3} width={8} height={6} fill={C.screen} /><rect x={3} y={11} width={6} height={3} fill={C.stone} /></g>
        : <Detective walking={false} />}
    </svg>
  );
}

function Say({ who, name, children }: { who: Parameters<typeof Portrait>[0]['who']; name: string; children: ReactNode }): ReactElement {
  return (
    <div className="say">
      <Portrait who={who} />
      <div className="bubble"><span className="speaker">{name}</span>{children}</div>
    </div>
  );
}

const inspected = (lab: Lab, id: string) => Boolean(lab.session?.evidence.find((e) => e.id === id)?.inspected);
const locked = (lab: Lab, id: string) => Boolean(lab.session?.evidence.find((e) => e.id === id)?.locked);
function item<C>(lab: Lab, id: string): EvidenceItem<C> | undefined { return lab.evidence[id] as EvidenceItem<C> | undefined; }

function Action({ lab, label, onClick, busy, disabled }: { lab: Lab; label: string; onClick: () => void; busy: Lab['busy']; disabled?: boolean }): ReactElement {
  const running = lab.busy === busy;
  return (
    <button type="button" className="btn primary" onClick={onClick} disabled={Boolean(lab.busy) || disabled} aria-busy={running}>
      {running ? '正在向本地实验服务请求…' : label}
    </button>
  );
}

function GoTo({ place, label, onGo }: { place: Place; label: string; onGo: (p: Place) => void }): ReactElement {
  return <button type="button" className="btn ghost" onClick={() => onGo(place)}>{label} →</button>;
}

export function StudioPanel({ lab, onGo }: { lab: Lab; onGo: (p: Place) => void }): ReactElement {
  const intent = item<AuthorizationContent>(lab, 'authorized-intent');
  if (!intent) {
    return (
      <>
        <Say who="alice" name="Alice">侦探，你来了！昨天我批准了一笔付款，给替我画 logo 的插画师 Bob。</Say>
        <Say who="alice" name="Alice">今早支付 API 发来了付款请求，钱包预览看着眼熟……可我总觉得不踏实。先看看我当初到底批准了什么。</Say>
        <Action lab={lab} busy="inspect" label="查看原始授权" onClick={() => void lab.inspect('authorized-intent')} />
      </>
    );
  }
  return (
    <>
      <div className="card"><h3>证据：原始授权</h3><AuthorizationCard c={intent.content} /></div>
      <Say who="alice" name="Alice">这份授权是我唯一亲手批准的东西。API 说什么都只是“请求”，要拿它来对照这份授权。</Say>
      {!inspected(lab, 'payment-request') && <GoTo place="relay" label="去支付中继站读取请求" onGo={onGo} />}
    </>
  );
}

export function RelayPanel({ lab, onGo }: { lab: Lab; onGo: (p: Place) => void }): ReactElement {
  const request = item<RequestContent>(lab, 'payment-request');
  if (!request) {
    return (
      <>
        <Say who="robot" name="中继机器人 R-402">哔。这里是支付中继站，我把支付 API 的消息转交给钱包。</Say>
        <Say who="robot" name="中继机器人 R-402">我只转发，不检查内容。今早那条消息还在缓存里，要读吗？</Say>
        <Action lab={lab} busy="inspect" label="读取 API 消息" onClick={() => void lab.inspect('payment-request')} />
      </>
    );
  }
  return (
    <>
      <div className="card"><h3>证据：API 付款请求</h3><RequestCard c={request.content} /></div>
      <Say who="robot" name="中继机器人 R-402">格式完全正常。至于收款地址是不是 Bob 本人的……那不归中继管。哔。</Say>
      {!inspected(lab, 'field-comparison') && <GoTo place="atelier" label="带着两份地址去 Bob 的画室" onGo={onGo} />}
    </>
  );
}

export function AtelierPanel({ lab, onGo }: { lab: Lab; onGo: (p: Place) => void }): ReactElement {
  const comparison = item<ComparisonContent>(lab, 'field-comparison');
  const intent = item<AuthorizationContent>(lab, 'authorized-intent');
  const request = item<RequestContent>(lab, 'payment-request');
  const [finished, setFinished] = useState(false);
  if (!comparison) {
    if (locked(lab, 'field-comparison')) {
      return (
        <>
          <Say who="bob" name="Bob">你好，我是 Bob。想核对收款地址？要比对，手上得有两份东西：</Say>
          <ul className="todo">
            <li className={inspected(lab, 'authorized-intent') ? 'ok' : ''}>Alice 的原始授权（设计工作室）</li>
            <li className={inspected(lab, 'payment-request') ? 'ok' : ''}>API 发来的付款请求（支付中继站）</li>
          </ul>
          <GoTo place={inspected(lab, 'authorized-intent') ? 'relay' : 'studio'} label="去取证据" onGo={onGo} />
        </>
      );
    }
    return (
      <>
        <Say who="bob" name="Bob">我门牌上写着地址缩写 <code>{intent?.content.recipient.preview ?? '…'}</code>。但缩写说明不了什么，我们把两份完整地址摊开，一段一段对。</Say>
        <Action lab={lab} busy="inspect" label="摊开两份完整地址" onClick={() => void lab.inspect('field-comparison')} />
      </>
    );
  }
  const recipient = comparison.content.fields.find((f) => f.field === 'recipient');
  const authorized = intent?.content.recipient.address ?? extractAddress(recipient?.authorized ?? '');
  const requested = request?.content.pay_to.address ?? extractAddress(recipient?.requested ?? '');
  return (
    <>
      <div className="card">
        <h3>证据：完整地址核对</h3>
        <AddressCompare
          authorized={authorized}
          requested={requested}
          positions={recipient?.differing_positions ?? []}
          authorizedPreview={intent?.content.recipient.preview ?? ''}
          requestedPreview={request?.content.pay_to.preview ?? ''}
          onReveal={() => setFinished(true)}
        />
      </div>
      {finished && (
        <>
          <div className="card"><h3>其他字段</h3><ComparisonFields c={comparison.content} /></div>
          <Say who="bob" name="Bob">
            {recipient && !recipient.passed
              ? '那不是我的地址。缩写一模一样，可只要差一位，就是别人的账户。'
              : '40 位都对上了，这确实是我的地址。'}
          </Say>
          <GoTo place={inspected(lab, 'chain-accounts') ? 'terminal' : 'archive'} label={inspected(lab, 'chain-accounts') ? '去钱包终端' : '去链上档案馆查这个地址'} onGo={onGo} />
        </>
      )}
    </>
  );
}

export function ArchivePanel({ lab, onGo }: { lab: Lab; onGo: (p: Place) => void }): ReactElement {
  const chain = item<ChainContent>(lab, 'chain-accounts');
  if (!chain) {
    return (
      <>
        <Say who="archivist" name="档案员 Ledger">链上档案馆。每个地址的余额、nonce、有没有合约代码，这里都能直接从本地链上读出来。</Say>
        <Action lab={lab} busy="inspect" label="查询链上档案" onClick={() => void lab.inspect('chain-accounts')} />
      </>
    );
  }
  const flagged = chain.content.accounts.find((a) => a.paid_by_request);
  return (
    <>
      <div className="card"><h3>证据：链上档案</h3><ChainCard c={chain.content} /></div>
      {flagged && (
        <Say who="archivist" name="档案员 Ledger">
          API 请求要付款的地址属于「{flagged.label}」，身份：{flagged.role === 'not in the authorization' ? '不在 Alice 的授权里' : flagged.role}。它的门牌缩写同样是 <code>{flagged.preview}</code>，就在街角那间仓库。
        </Say>
      )}
      <GoTo place="terminal" label="去钱包终端决定怎么验证" onGo={onGo} />
    </>
  );
}

export function WarehousePanel({ lab, onGo }: { lab: Lab; onGo: (p: Place) => void }): ReactElement {
  const chain = item<ChainContent>(lab, 'chain-accounts');
  const flagged = chain?.content.accounts.find((a) => a.paid_by_request);
  return (
    <>
      <Say who="detective" name="你">门牌上也写着 <code>{flagged?.preview ?? '…'}</code>，和 Bob 的画室一模一样。</Say>
      {flagged && <p className="note">档案记录：账户「{flagged.label}」· 余额 {ether(flagged.balance)} · nonce {flagged.nonce} · 完整地址 <code>{flagged.address}</code></p>}
      <GoTo place="terminal" label="回钱包终端" onGo={onGo} />
    </>
  );
}

export function TerminalPanel({ lab }: { lab: Lab }): ReactElement {
  const session = lab.session;
  const mission = lab.mission;
  const draft = lab.evidence['transaction-draft'];
  const [picked, setPicked] = useState<string | null>(session?.choice?.id ?? null);
  if (!session || !mission) return <></>;
  const missing = session.evidence.filter((e) => (e.kind === 'authorization' || e.kind === 'request') && !e.inspected);
  const selected = picked ?? session.choice?.id ?? null;
  return (
    <>
      <Say who="terminal" name="钱包终端">我会把你选的验证规则同时用在两笔请求上：一笔与授权一致，一笔就是今早那条。结果由本地链和裁判决定。</Say>
      {!draft
        ? <Action lab={lab} busy="inspect" label="预览待签交易" onClick={() => void lab.inspect('transaction-draft')} />
        : <details className="card" open={!session.choice}><summary><h3>证据：待签交易</h3></summary><TransactionCard c={draft.content as TransactionContent} /></details>}
      {missing.length > 0 ? (
        <p className="lock">🔒 终端需要先看到：{missing.map((e) => e.kind === 'authorization' ? '原始授权（设计工作室）' : 'API 请求（支付中继站）').join('、')}。</p>
      ) : (
        <fieldset className="strategies" disabled={Boolean(lab.busy) || !session.allowed.choose}>
          <legend>选择验证规则</legend>
          {mission.choices.map((choice) => {
            const text = CHOICE_ZH[choice.id];
            return (
              <label key={choice.id} className={`strategy${selected === choice.id ? ' picked' : ''}`}>
                <input type="radio" name="strategy" value={choice.id} checked={selected === choice.id} onChange={() => setPicked(choice.id)} />
                <span><strong>{text?.label ?? choice.label}</strong><small>{text?.detail ?? choice.detail}</small></span>
              </label>
            );
          })}
        </fieldset>
      )}
      {missing.length === 0 && session.stage !== 'replayed' && (
        <div className="row">
          <Action
            lab={lab}
            busy="choose"
            label={session.choice?.id === selected ? '规则已锁定' : '锁定这条规则'}
            disabled={!selected || session.choice?.id === selected || !session.allowed.choose}
            onClick={() => selected && void lab.choose(selected)}
          />
          <Action lab={lab} busy="replay" label="在本地链上运行两笔请求" disabled={!session.allowed.replay} onClick={() => void lab.replay()} />
        </div>
      )}
      {lab.busy === 'replay' && <p className="note" aria-live="polite">终端正在本地 Anvil 链上依次执行两笔请求，并在每笔之后恢复快照…</p>}
    </>
  );
}

function VariantCard({ v }: { v: VariantResult }): ReactElement {
  const tx = v.transaction;
  return (
    <article className={`variant ${v.status}`}>
      <h4>请求 {v.request.request_id} · {zh(VARIANT_ZH, v.id, v.title)}</h4>
      <p className="decision">
        {v.decision.accepted ? '规则决定：付款' : '规则决定：拒付'}
        {' · '}
        {tx
          ? <>交易已上链（区块 #{tx.block_number}，收据 status {tx.status}）：{ether(tx.value)} → <strong>{tx.to.label ?? tx.to.address}</strong></>
          : '没有发送任何交易'}
      </p>
      <table className="moves">
        <thead><tr><th>账户</th><th>之前</th><th>之后</th><th>变化</th></tr></thead>
        <tbody>
          {v.balances.map((b) => (
            <tr key={b.label} className={b.change.wei === '0' ? '' : b.change.wei.startsWith('-') ? 'down' : 'up'}>
              <td>{b.label}</td><td>{ether(b.before)}</td><td>{ether(b.after)}</td><td>{b.change.wei === '0' ? '—' : ether(b.change)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="verdict-line">裁判：{v.status === 'passed' ? '✓ 通过' : '✗ 未通过'} · {v.score}/{v.max_score} 分</p>
      <details>
        <summary>裁判细节与交易数据</summary>
        <ul className="checks">
          {v.criteria.map((c) => (
            <li key={c.id} className={c.passed ? 'ok' : 'bad'}>
              <span className="mark" aria-hidden="true">{c.passed ? '✓' : '✗'}</span>
              <strong>{zh(CHECK_ZH, c.check, c.description)}</strong> {c.awarded}/{c.points}
              <p>{c.explanation}</p>
            </li>
          ))}
        </ul>
        {tx && <p className="tech">tx <code>{tx.hash}</code><br />gas {tx.gas_used} × {tx.effective_gas_price_wei} wei = 手续费 {ether(tx.fee)}</p>}
        <p className="tech">规则说明（后端）：{v.decision.summary}</p>
        <p className="tech">归一化摘要 {v.normalized_digest.slice(0, 16)} · 快照恢复已验证：{v.reset_verified ? '是' : '否'}</p>
      </details>
    </article>
  );
}

export function OutcomePanel({ lab, result, revealed, playing, onSkip, onBook }: {
  lab: Lab; result: Result; revealed: number; playing: boolean; onSkip: () => void; onBook: () => void;
}): ReactElement {
  const feedback = CHOICE_ZH[result.choice.id]?.feedback ?? result.choice.feedback;
  const done = revealed >= result.variants.length;
  return (
    <>
      <h3 className={`verdict ${done ? (result.passed ? 'pass' : 'fail') : ''}`}>
        {!done ? '本地链执行中的结果' : result.passed ? '意图守住了' : '验证没有守住'}
      </h3>
      <p className="note">规则：{CHOICE_ZH[result.choice.id]?.label ?? result.choice.label} · 第 {result.attempt} 次尝试</p>
      {result.variants.slice(0, revealed).map((v) => <VariantCard key={v.id} v={v} />)}
      {playing && <button type="button" className="btn ghost" onClick={onSkip}>跳过动画，直接看结果</button>}
      {done && (
        <>
          {result.passed
            ? <Say who="alice" name="Alice">Bob 收到了他的 1.5 ETH，那条换了收款人的请求在签名前就被挡下了。谢谢你，侦探。</Say>
            : <Say who="alice" name="Alice">结果不对……没关系，链只是本地实验，快照可以恢复。换一条规则再试。</Say>}
          <div className={`card feedback ${result.passed ? 'pass' : 'fail'}`}>
            <p>{feedback}</p>
            <details><summary>后端原文</summary><p>{result.choice.feedback}</p><p>{result.summary}</p></details>
          </div>
          <div className="row">
            <button type="button" className="btn primary" disabled={Boolean(lab.busy)} onClick={() => void lab.reset()}>
              {lab.busy === 'reset' ? '正在恢复链上快照…' : result.passed ? '恢复快照，再玩一次' : '回溯：恢复快照后重试'}
            </button>
            <button type="button" className="btn ghost" onClick={onBook}>打开证据册</button>
          </div>
        </>
      )}
    </>
  );
}
