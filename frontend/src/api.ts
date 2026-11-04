// Typed client for the Security Lab API (genesis/lab/api.py). The backend is the only
// authority on stage, permissions, balances, validation and grading; this module only
// carries requests and responses.

export interface Amount { wei: string; ether: string }
export interface AccountRef { label: string; address: string; preview: string; role: string }
export interface AccountRow extends AccountRef { balance: Amount; nonce: number }
export interface AddressRef { address: string; preview: string; label?: string | null }

export interface Choice { id: string; label: string; detail: string }
export interface Mission {
  id: string;
  title: string;
  tagline: string;
  estimated_minutes: number;
  briefing: string[];
  objectives: string[];
  trust_boundary: { title: string; summary: string; disclaimer: string; steps: { actor: string; trust: string; note: string }[] };
  choices: Choice[];
  hints_total: number;
  scenario: { id: string; version: string; title: string; manifest_digest: string; variants: { id: string; title: string }[] };
}

export type EvidenceKind = 'authorization' | 'request' | 'transaction' | 'chain' | 'comparison';
export interface Evidence { id: string; title: string; kind: EvidenceKind; summary: string; requires: string[]; locked: boolean; inspected: boolean }
export interface TimelineEvent { seq: number; attempt: number; kind: string; title: string; detail: string }

export interface Criterion {
  id: string; check: string; description: string; required: boolean; points: number; awarded: number;
  passed: boolean; expected: string; actual: string; explanation: string;
}
export interface TransactionView {
  hash: string; block_number: number; from: AccountRef; to: AddressRef; value: Amount;
  gas_used: number; effective_gas_price_wei: string; fee: Amount; status: number;
}
export interface BalanceChange { label: string; address: string; before: Amount; after: Amount; change: Amount }
export interface VariantResult {
  id: string; title: string; description: string; expect: 'accept' | 'reject';
  request: { request_id: string; pay_to: AddressRef; value: Amount; chain_id: number };
  decision: { accepted: boolean; summary: string; checks: { field: string; passed: boolean; detail: string }[] };
  status: 'passed' | 'failed'; score: number; max_score: number;
  transaction: TransactionView | null; balances: BalanceChange[]; criteria: Criterion[];
  normalized_digest: string; reset_verified: boolean;
}
export interface Result {
  passed: boolean; attempt: number; summary: string;
  choice: { id: string; label: string; detail: string; feedback: string };
  variants: VariantResult[];
}
export interface Session {
  stage: 'investigating' | 'diagnosed' | 'replayed';
  attempt: number;
  evidence: Evidence[];
  hints: { revealed: string[]; total: number };
  choice: null | { id: string; label: string };
  accounts: AccountRow[];
  chain: { chain_id: number; block_number: number; client_version?: string };
  timeline: TimelineEvent[];
  result: Result | null;
  history: { attempt: number; choice: string; label: string; passed: boolean }[];
  allowed: { inspect: boolean; hint: boolean; choose: boolean; replay: boolean; reset: boolean };
}

export interface AuthorizationContent { reference: string; description: string; payer: AccountRef; recipient: AccountRef; value: Amount; chain_id: number }
export interface RequestContent { source: string; request_id: string; pay_to: AddressRef; value: Amount; chain_id: number; memo: string; raw: Record<string, unknown> }
export interface TransactionContent { from: AccountRef; to: AddressRef; value: Amount; chain_id: number; gas_limit: number; wallet_preview: string; note: string }
export interface ChainContent { chain_id: number; block_number: number; client_version?: string; accounts: (AccountRow & { has_code: boolean; paid_by_request: boolean })[] }
export interface ComparisonField { field: string; passed: boolean; authorized: string; requested: string; explanation: string; differing_positions: number[] }
export interface ComparisonContent { fields: ComparisonField[]; all_match: boolean }
export interface EvidenceItem<C = unknown> { id: string; title: string; kind: EvidenceKind; summary: string; content: C }
export interface Hint { index: number; total: number; text: string }

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

// The last state version the backend reported (X-Lab-Version). Sent back on every
// action so the backend can refuse actions based on a stale view of the experiment.
let knownVersion: string | null = null;
export function labVersion(): string | null { return knownVersion; }
export function forgetLabVersion(): void { knownVersion = null; }

function newKey(): string {
  const c = globalThis.crypto as Crypto | undefined;
  return c?.randomUUID ? c.randomUUID() : `k-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/** Low-level call: GET without a body, POST with one. Kept for compatibility. */
export async function api<T>(path: string, body?: unknown, options: { idempotencyKey?: string; replayed?: { value: boolean } } = {}): Promise<T> {
  const post = body !== undefined;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (post && path.startsWith('session')) {
    if (knownVersion) headers['X-Lab-Version'] = knownVersion;
    headers['Idempotency-Key'] = options.idempotencyKey ?? newKey();
  }
  const response = await fetch('/api/' + path, {
    method: post ? 'POST' : 'GET',
    headers,
    ...(post ? { body: JSON.stringify(body) } : {}),
  });
  // A replayed idempotent response is the original one, possibly with an old version:
  // never adopt its version (the caller refreshes the session instead).
  const replayed = response.headers?.get?.('Idempotency-Replayed') === 'true';
  if (options.replayed) options.replayed.value = replayed;
  const version = response.headers?.get?.('X-Lab-Version');
  if (version && !replayed) knownVersion = version;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = data?.error;
    const message = typeof error === 'string' ? error : error?.message;
    throw new ApiError(
      response.status,
      typeof error === 'object' && error?.code ? error.code : `http-${response.status}`,
      message ?? `Local service unavailable (${response.status}). Restart the backend and retry.`,
    );
  }
  return data as T;
}

/**
 * One intended action: a single Idempotency-Key for its whole life. If the response is
 * lost to a network failure, the identical request is sent again with the same key, so
 * the backend returns the original outcome instead of executing twice
 * (docs/BACKEND_FRONTEND_HANDOFF.md). HTTP errors are never retried.
 */
export async function action<T>(path: string, body: unknown = {}, returnsSession = false, attempts = 3): Promise<T> {
  const idempotencyKey = newKey();
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const replayed = { value: false };
      const data = await api<T>(path, body, { idempotencyKey, replayed });
      if (!replayed.value) return data;
      // The backend returned the cached original. Fetch the current state and version
      // before anything else may happen, and never let the cached body overwrite it.
      const current = await api<Session>('session');
      return returnsSession ? (current as T) : data;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      lastError = error;
    }
  }
  throw new ApiError(0, 'network', `无法连接本地实验服务（${String(lastError)}）。请确认后端已启动后重试。`);
}

export const lab = {
  mission: () => api<Mission>('mission'),
  session: () => api<Session>('session'),
  start: () => action<Session>('session', {}, true),
  // These return evidence, a hint or a result (still valid when replayed); the caller
  // always reloads the session afterwards.
  inspect: <C = unknown>(id: string) => action<EvidenceItem<C>>(`session/evidence/${encodeURIComponent(id)}`),
  hint: () => action<Hint>('session/hints'),
  choose: (choice: string) => action<Session>('session/choice', { choice }, true),
  replay: () => action<Result>('session/replay'),
  reset: () => action<Session>('session/reset', {}, true),
  report: () => api<unknown>('session/report'),
};
