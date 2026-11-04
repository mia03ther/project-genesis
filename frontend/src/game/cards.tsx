// Readable evidence cards, built only from backend evidence content.
import type { ReactElement } from 'react';
import type { AuthorizationContent, ChainContent, ComparisonContent, EvidenceItem, RequestContent, TransactionContent } from '../api';
import { CopyButton } from './AddressCompare';
import { ether, EVIDENCE_ZH, FIELD_ZH, ROLE_ZH, zh } from './text';

function FullAddress({ address, label }: { address: string; label: string }): ReactElement {
  return (
    <span className="full-address">
      <code>{address}</code>
      <CopyButton text={address} label={label} />
    </span>
  );
}

export function AuthorizationCard({ c }: { c: AuthorizationContent }): ReactElement {
  return (
    <dl className="facts">
      <dt>授权编号</dt><dd>{c.reference}</dd>
      <dt>付款方</dt><dd>{c.payer.label}</dd>
      <dt>收款人</dt><dd><strong>{c.recipient.label}</strong><FullAddress address={c.recipient.address} label="授权收款地址" /></dd>
      <dt>金额</dt><dd>{ether(c.value)}</dd>
      <dt>链 ID</dt><dd>{c.chain_id}</dd>
      <dt>原文</dt><dd className="quote">{c.description}</dd>
    </dl>
  );
}

export function RequestCard({ c }: { c: RequestContent }): ReactElement {
  return (
    <>
      <dl className="facts">
        <dt>来源</dt><dd>{c.source}</dd>
        <dt>请求号</dt><dd>{c.request_id}</dd>
        <dt>付款给</dt><dd><strong className="mono">{c.pay_to.preview}</strong><FullAddress address={c.pay_to.address} label="请求收款地址" /></dd>
        <dt>金额</dt><dd>{ether(c.value)}</dd>
        <dt>链 ID</dt><dd>{c.chain_id}</dd>
        <dt>备注</dt><dd>{c.memo}</dd>
      </dl>
      <details className="raw"><summary>原始 API 消息（JSON）</summary><pre>{JSON.stringify(c.raw, null, 2)}</pre></details>
    </>
  );
}

export function TransactionCard({ c }: { c: TransactionContent }): ReactElement {
  return (
    <>
      <div className="wallet-popup" role="group" aria-label="钱包签名预览">
        <span className="wallet-title">钱包 · 请确认</span>
        <span className="wallet-line">{c.wallet_preview.replace('Send', '发送').replace('ether to', 'ETH 给')}</span>
      </div>
      <dl className="facts">
        <dt>from</dt><dd>{c.from.label} <code className="mono">{c.from.preview}</code></dd>
        <dt>to</dt><dd><FullAddress address={c.to.address} label="待签收款地址" /></dd>
        <dt>value</dt><dd>{ether(c.value)}</dd>
        <dt>chainId</dt><dd>{c.chain_id}</dd>
        <dt>gas</dt><dd>{c.gas_limit}</dd>
      </dl>
      <p className="note">这是根据请求生成的草稿：尚未签名，也没有发送。</p>
    </>
  );
}

export function ChainCard({ c }: { c: ChainContent }): ReactElement {
  return (
    <>
      <div className="table-wrap">
        <table className="ledger">
          <thead><tr><th>账户</th><th>身份</th><th>地址</th><th>余额</th><th>nonce</th><th>代码</th></tr></thead>
          <tbody>
            {c.accounts.map((a) => (
              <tr key={a.address} className={a.paid_by_request ? 'flagged' : undefined}>
                <td>{a.label}</td>
                <td>{zh(ROLE_ZH, a.role, a.role)}</td>
                <td><code title={a.address}>{a.preview}</code>{a.paid_by_request && <span className="flag">API 请求付款给它</span>}</td>
                <td>{ether(a.balance)}</td>
                <td>{a.nonce}</td>
                <td>{a.has_code ? '有' : '无'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="raw"><summary>完整地址</summary>{c.accounts.map((a) => <p key={a.address}>{a.label}: <code>{a.address}</code> <CopyButton text={a.address} label={`${a.label} 地址`} /></p>)}</details>
      <p className="note">本地链 {c.chain_id} · 区块 #{c.block_number}{c.client_version ? ` · ${c.client_version}` : ''}</p>
    </>
  );
}

export function ComparisonFields({ c }: { c: ComparisonContent }): ReactElement {
  return (
    <ul className="checks">
      {c.fields.map((f) => (
        <li key={f.field} className={f.passed ? 'ok' : 'bad'}>
          <span className="mark" aria-hidden="true">{f.passed ? '✓' : '✗'}</span>
          <strong>{zh(FIELD_ZH, f.field, f.field)}</strong> {f.passed ? '一致' : '不一致'}
          <details><summary>后端解释</summary><p>{f.explanation}</p><p>授权：<code>{f.authorized}</code><br />请求：<code>{f.requested}</code></p></details>
        </li>
      ))}
    </ul>
  );
}

export function EvidenceBody({ item }: { item: EvidenceItem }): ReactElement {
  switch (item.kind) {
    case 'authorization': return <AuthorizationCard c={item.content as AuthorizationContent} />;
    case 'request': return <RequestCard c={item.content as RequestContent} />;
    case 'transaction': return <TransactionCard c={item.content as TransactionContent} />;
    case 'chain': return <ChainCard c={item.content as ChainContent} />;
    case 'comparison': return <ComparisonFields c={item.content as ComparisonContent} />;
    default: return <pre>{JSON.stringify(item.content, null, 2)}</pre>;
  }
}

export function evidenceTitle(id: string, fallback: string): string {
  return zh(EVIDENCE_ZH, id, fallback);
}
