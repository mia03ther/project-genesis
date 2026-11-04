// A small stateful stand-in for the FastAPI lab, built from responses captured from the
// real session logic (src/test/fixtures). It only follows the rules the UI relies on.
import mission from './fixtures/mission.json';
import evidence from './fixtures/evidence.json';
import hint from './fixtures/hint.json';
import stateStart from './fixtures/state_start.json';
import replayFailed from './fixtures/replay_failed.json';
import replayPassed from './fixtures/replay_passed.json';
import report from './fixtures/report.json';

type Json = Record<string, any>;
export interface Call { method: string; path: string; body: Json | null; headers: Record<string, string> }
interface Canned { status: number; body?: unknown; headers?: Record<string, string>; network?: boolean; hold?: Promise<void> }

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

export class FakeLab {
  session: Json | null = null;
  version = 0;
  calls: Call[] = [];
  private overrides: { match: string; response: Canned }[] = [];

  /** Make the next request whose "METHOD /path" starts with `match` answer with `response`. */
  once(match: string, response: Canned): void { this.overrides.push({ match, response }); }

  count(match: string): number { return this.calls.filter((c) => `${c.method} ${c.path}`.startsWith(match)).length; }

  fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const method = (init?.method ?? 'GET').toUpperCase();
    const path = String(input).replace(/^https?:\/\/[^/]+/, '');
    const body = init?.body ? JSON.parse(String(init.body)) as Json : null;
    const headers = Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>).map(([k, v]) => [k.toLowerCase(), v]));
    this.calls.push({ method, path, body, headers });
    const index = this.overrides.findIndex((o) => `${method} ${path}`.startsWith(o.match));
    if (index >= 0) {
      const response = this.overrides.splice(index, 1)[0]!.response;
      if (response.hold) await response.hold;
      if (response.network) throw new TypeError('Failed to fetch');
      return reply(response.status, response.body, response.headers);
    }
    return this.handle(method, path, body);
  };

  private handle(method: string, path: string, body: Json | null): Response {
    const ok = (data: unknown, mutation = true) => {
      if (mutation) this.version += 1;
      return reply(200, data, { 'X-Lab-Version': `epoch:${this.version}` });
    };
    if (method === 'GET' && path === '/api/mission') return reply(200, mission);
    if (path === '/api/session' && method === 'POST') { this.session = clone(stateStart); return ok(this.session); }
    if (!this.session) return reply(404, { error: { code: 'no-session', message: 'Start a session first.' } });
    const s = this.session;
    const has = (id: string) => s.evidence.find((e: Json) => e.id === id)?.inspected;
    for (const e of s.evidence) e.locked = e.requires.some((r: string) => !has(r));
    if (method === 'GET' && path === '/api/session') return ok(s, false);
    if (method === 'GET' && path === '/api/session/report') return ok(report, false);
    const inspect = path.match(/^\/api\/session\/evidence\/(.+)$/);
    if (inspect) {
      const id = decodeURIComponent(inspect[1] ?? '');
      const row = s.evidence.find((e: Json) => e.id === id);
      if (!row) return reply(404, { error: { code: 'unknown-evidence', message: id } });
      if (row.locked) return reply(409, { error: { code: 'evidence-locked', message: 'Inspect its requirements first.' } });
      row.inspected = true;
      for (const e of s.evidence) e.locked = e.requires.some((r: string) => !has(r));
      return ok((evidence as Json)[id]);
    }
    if (path === '/api/session/hints') {
      s.hints.revealed.push(hint.text);
      return ok(hint);
    }
    if (path === '/api/session/choice') {
      if (!has('authorized-intent') || !has('payment-request')) return reply(409, { error: { code: 'investigate-first', message: 'Inspect the authorization and the request first.' } });
      const choice = mission.choices.find((c) => c.id === body?.choice);
      if (!choice) return reply(422, { error: { code: 'unknown-choice', message: String(body?.choice) } });
      s.choice = { id: choice.id, label: choice.label };
      s.stage = 'diagnosed';
      s.allowed = { ...s.allowed, replay: true };
      return ok(s);
    }
    if (path === '/api/session/replay') {
      if (!s.choice) return reply(409, { error: { code: 'choose-first', message: 'Choose a strategy first.' } });
      const result = clone(s.choice.id === 'exact-intent-match' ? replayPassed : replayFailed) as Json;
      result.attempt = s.attempt;
      s.result = result;
      s.stage = 'replayed';
      s.allowed = { ...s.allowed, choose: false, replay: false };
      s.history.push({ attempt: s.attempt, choice: s.choice.id, label: s.choice.label, passed: result.passed });
      return ok(result);
    }
    if (path === '/api/session/reset') {
      s.stage = 'investigating';
      s.attempt += 1;
      s.choice = null;
      s.result = null;
      s.allowed = { ...s.allowed, choose: true, replay: false };
      return ok(s);
    }
    return reply(404, { error: { code: 'not-found', message: path } });
  }
}

export function reply(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
}
