import starter from '../../../contracts/authorization/exercise/PaymentIntent.sol?raw';
import reference from '../../../contracts/authorization/src/PaymentIntent.sol?raw';

export { starter, reference };
export const REMIX_ORIGIN = 'https://app.remix.live';
export const DRAFT_KEY = 'genesis.payment-intent.draft.v1';
export const MAX_SOURCE_BYTES = 24000;

/** UTF-8, not btoa(source): learners may write Chinese comments. Fragment stays out of HTTP requests. */
export function remixUrl(source: string, embedded = false): string {
  const bytes = new TextEncoder().encode(source);
  if (bytes.length > MAX_SOURCE_BYTES) throw new Error('练习代码请控制在 24 KB 内，再送入 Remix。');
  const encoded = btoa(Array.from(bytes, b => String.fromCharCode(b)).join(''));
  const params = new URLSearchParams({ code: encoded, theme: 'Dark', language: 'Solidity',
    version: 'soljson-v0.8.28+commit.7893614a.js', activate: 'solidity,udapp' });
  if (embedded) params.set('embed', 'true');
  return `${REMIX_ORIGIN}/?#${params.toString()}`;
}

export const vectors = [
  { name: 'Bob 的合法付款', address: '0x0000000000000000000000000000000000000b0b', amount: '1500000000000000000', chain: 31337, expected: 'true' },
  { name: '相似地址', address: '0x00000000000000000000000000000000000f0b0b', amount: '1500000000000000000', chain: 31337, expected: 'false' },
  { name: '金额不符', address: '0x0000000000000000000000000000000000000b0b', amount: '1000000000000000000', chain: 31337, expected: 'false' },
  { name: '链不符', address: '0x0000000000000000000000000000000000000b0b', amount: '1500000000000000000', chain: 1, expected: 'false' },
] as const;
