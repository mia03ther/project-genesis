// Chinese presentation of backend content. Lookups are keyed by the backend's own ids,
// check names or exact English text, and always fall back to the backend's wording.
// Nothing here decides anything: which strategy is safe is known only from graded results.

export function zh<K extends string>(table: Partial<Record<K, string>>, key: string, fallback: string): string {
  return (table as Record<string, string | undefined>)[key] ?? fallback;
}

export const EVIDENCE_ZH: Record<string, string> = {
  'authorized-intent': '原始授权',
  'payment-request': 'API 付款请求',
  'transaction-draft': '待签交易',
  'chain-accounts': '链上档案',
  'field-comparison': '完整地址核对',
};

export const CHOICE_ZH: Record<string, { label: string; detail: string; feedback: string }> = {
  'trust-api': {
    label: '照单全付',
    detail: '支付 API 是 Alice 自己的服务商，请求内容就是权威。',
    feedback: '不安全。API 的返回是不可信输入：谁控制或攻破了 API，谁就决定钱流向哪里。这个策略把 1.5 ether 付给了 Alice 从未批准的地址，而已上链的转账无法撤回。',
  },
  'preview-match': {
    label: '预览一致就批准',
    detail: '比对钱包显示的缩略地址和金额。',
    feedback: '不安全。Bob 的地址和未知地址缩略后都是 0x0000...0b0b，预览检查通过了，钱却去了错误的账户。缩略地址帮助阅读，不能用来验证。',
  },
  'amount-and-network': {
    label: '核对金额和网络',
    detail: '金额和链 ID 与发票一致就付款。',
    feedback: '不安全。金额和链都对，这正是请求看起来可信的原因；但收款人从未被核对，付款去了未授权的地址。',
  },
  'exact-intent-match': {
    label: '逐字段核对原始授权',
    detail: '收款人、金额、链 ID 都与 Alice 的授权完全相同才付款，任何不一致都拒绝。',
    feedback: '安全。匹配的请求付给了 Bob，不匹配的请求在签名前就被拒绝，所有余额分毫未动。做决定的是授权，而不是 API。',
  },
  'refuse-all': {
    label: '一律拒绝 API 请求',
    detail: '从不支付 API 发来的请求，改用其他方式结算。',
    feedback: '安全，但没有完成任务：Bob 的正确请求也被拒了，发票仍未支付。好的验证要拦住坏请求，同时放行好请求。',
  },
};

export const HINT_ZH: Record<string, string> = {
  'Start with what Alice approved, then read the request. Is every field the same, or only most of them?':
    '先看 Alice 批准了什么，再读请求。每个字段都一样，还是只有大部分一样？',
  'Wallet previews shorten addresses to the first and last few characters. Two different addresses can share both. Compare all 40 hex digits.':
    '钱包预览只显示地址开头和结尾几位，两个不同的地址可能首尾完全相同。请比对全部 40 位十六进制。',
  'Open the chain evidence. Which account does the request\'s address belong to, and did Alice ever authorize it?':
    '去链上档案馆看看：请求里的地址属于哪个账户？Alice 授权过它吗？',
  'A safe validator checks every authorized field exactly (recipient, amount and chain) and refuses on any mismatch before signing. It must still pay the request that does match.':
    '安全的验证会在签名前精确核对每个授权字段（收款人、金额、链），任何不一致都拒绝；同时仍要支付完全匹配的请求。',
};

export const VARIANT_ZH: Record<string, string> = {
  'authorized-request': '合法请求：收款人与授权一致',
  'wrong-recipient': '异常请求：收款人被换成另一个地址',
};

export const CHECK_ZH: Record<string, string> = {
  decision: '付款决定正确',
  authorized_transfer: '只执行授权内的转账',
  receipt_status: '交易成功上链',
  recipient: '付给 Bob 的完整地址',
  value: '金额分毫不差',
  final_balance: '收款后余额正确',
  sender_pays_value_and_fee: '付款方支付金额与手续费',
  nonce_increment: '只签了一笔交易',
  balances_unchanged: '拒付后余额未动',
  sender: '付款方正确',
  gas_used: 'gas 用量正确',
};

export const ROLE_ZH: Record<string, string> = {
  payer: '付款方',
  'authorized recipient': '授权收款人',
  'not in the authorization': '不在授权内',
};

export const FIELD_ZH: Record<string, string> = { recipient: '收款人', value: '金额', chain_id: '链 ID' };

export function ether(amount: { ether: string }): string {
  return amount.ether.replace(' ether', ' ETH');
}
