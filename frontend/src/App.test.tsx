import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { forgetLabVersion } from './api';
import { FakeLab } from './test/fakeBackend';
import stateReplayedFailed from './test/fixtures/state_replayed_failed.json';

let backend: FakeLab;

beforeEach(() => {
  backend = new FakeLab();
  forgetLabVersion();
  vi.stubGlobal('fetch', vi.fn(backend.fetch));
  // Reduced motion: the walker and parcels jump straight to their backend-driven end state.
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('reduce'), media: query, addEventListener() {}, removeEventListener() {} }));
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const user = () => userEvent.setup();

/** The scene hotspot for a place (not the dialogue's "go to" buttons). */
function place(name: string): HTMLElement {
  const found = screen.getAllByRole('button').find((b) => b.classList.contains('hotspot') && b.getAttribute('aria-label')?.startsWith(name));
  if (!found) throw new Error(`no hotspot ${name}`);
  return found;
}
const panel = () => within(screen.getByRole('complementary', { name: '对话与调查' }));

async function startCase(u: ReturnType<typeof user>) {
  render(<App />);
  await u.click(await screen.findByRole('button', { name: '开始调查' }));
  // A new case walks the detective to Alice's studio.
  return panel().findByRole('button', { name: '查看原始授权' });
}

async function collectEvidence(u: ReturnType<typeof user>) {
  await u.click(await startCase(u));
  await panel().findByText(/唯一亲手批准/);
  await u.click(place('支付中继站'));
  await u.click(await panel().findByRole('button', { name: '读取 API 消息' }));
  await u.click(place('Bob 的画室'));
  await u.click(await panel().findByRole('button', { name: '摊开两份完整地址' }));
  await u.click(await panel().findByRole('button', { name: '全部展开' }));
  await panel().findByText('那不是我的地址。缩写一模一样，可只要差一位，就是别人的账户。');
  await u.click(place('链上档案馆'));
  await u.click(await panel().findByRole('button', { name: '查询链上档案' }));
  await u.click(place('钱包终端'));
  await u.click(await panel().findByRole('button', { name: '预览待签交易' }));
  await panel().findByRole('group', { name: '选择验证规则' });
}

async function runStrategy(u: ReturnType<typeof user>, label: string) {
  await u.click(panel().getByRole('radio', { name: new RegExp(label) }));
  await u.click(panel().getByRole('button', { name: '锁定这条规则' }));
  await panel().findByRole('button', { name: '规则已锁定' });
  await u.click(panel().getByRole('button', { name: '在本地链上运行两笔请求' }));
}

describe('The Wrong Recipient game', () => {
  it('shows the town and a loading card, then the title card from the backend mission', async () => {
    let release!: () => void;
    backend.once('GET /api/mission', { status: 200, body: (await import('./test/fixtures/mission.json')).default, hold: new Promise((r) => { release = r; }) });
    render(<App />);
    expect(screen.getByRole('img', { name: /像素街区/ })).toBeInTheDocument();
    expect(screen.getByText('正在连接本地实验服务…')).toBeInTheDocument();
    expect(place('钱包终端')).toBeDisabled();
    await act(async () => release());
    expect(await screen.findByRole('button', { name: '开始调查' })).toBeEnabled();
    expect(screen.getByText('The Wrong Recipient')).toBeInTheDocument();
  });

  it('reveals evidence step by step, with Bob locked until both documents are found', async () => {
    const u = user();
    await u.click(await startCase(u));
    await panel().findByText(/唯一亲手批准/);
    expect(screen.getByLabelText('调查进度 1/5')).toBeInTheDocument();
    expect(place('Alice 的设计工作室')).toHaveAccessibleName('Alice 的设计工作室（已调查）');

    await u.click(place('Bob 的画室'));
    expect(await panel().findByText(/要比对，手上得有两份东西/)).toBeInTheDocument();
    expect(panel().queryByRole('button', { name: '摊开两份完整地址' })).not.toBeInTheDocument();

    await u.click(place('支付中继站'));
    await u.click(await panel().findByRole('button', { name: '读取 API 消息' }));
    await u.click(place('Bob 的画室'));
    await u.click(await panel().findByRole('button', { name: '摊开两份完整地址' }));

    // Step through the address four digits at a time; the difference comes from the backend.
    const next = await panel().findByRole('button', { name: '开始逐段核对' });
    await u.click(next);
    expect(panel().getByText('第 1 段一致（4/40 位）。')).toBeInTheDocument();
    for (let i = 0; i < 7; i += 1) await u.click(panel().getByRole('button', { name: '下一段 →' }));
    expect(panel().queryByText(/出现不同/)).not.toBeInTheDocument();
    await u.click(panel().getByRole('button', { name: '下一段 →' }));
    expect(panel().getByText(/第 9 段出现不同：第 36 位不一样/)).toBeInTheDocument();
    expect(panel().getAllByRole('button', { name: /^复制/ })).toHaveLength(2);
    expect(await panel().findByText(/那不是我的地址/)).toBeInTheDocument();
    expect(screen.getByLabelText('调查进度 3/5')).toBeInTheDocument();
    expect(backend.count('POST /api/session/evidence/')).toBe(3);
  });

  it('runs a failing strategy on the backend, shows funds reaching the unknown address, then resets and succeeds', { timeout: 30000 }, async () => {
    const u = user();
    await collectEvidence(u);
    // The strategy list is the mission's own five ids.
    expect(panel().getAllByRole('radio')).toHaveLength(5);

    await runStrategy(u, '照单全付');
    expect(backend.calls.find((c) => c.path === '/api/session/choice')?.body).toEqual({ choice: 'trust-api' });
    expect(await panel().findByRole('heading', { name: '验证没有守住' })).toBeInTheDocument();
    expect(panel().getAllByText(/交易已上链/)).toHaveLength(2);
    expect(panel().getAllByRole('strong').some((el) => el.textContent === 'unknown')).toBe(true);
    expect(screen.getByText(/实验没有守住意图/)).toBeInTheDocument();

    await u.click(panel().getByRole('button', { name: '回溯：恢复快照后重试' }));
    await panel().findByRole('group', { name: '选择验证规则' });
    expect(backend.count('POST /api/session/reset')).toBe(1);

    await runStrategy(u, '逐字段核对原始授权');
    expect(backend.calls.filter((c) => c.path === '/api/session/choice').at(-1)?.body).toEqual({ choice: 'exact-intent-match' });
    expect(await panel().findByRole('heading', { name: '意图守住了' })).toBeInTheDocument();
    expect(panel().getByText(/没有发送任何交易/)).toBeInTheDocument();
    expect(panel().getAllByText(/交易已上链/)).toHaveLength(1);

    await u.click(screen.getByRole('button', { name: '📒 证据册' }));
    const book = within(screen.getByRole('dialog', { name: '证据册' }));
    await u.click(book.getByRole('tab', { name: '尝试记录' }));
    expect(book.getByText(/第 1 次 · 照单全付 · 未通过/)).toBeInTheDocument();
    expect(book.getByText(/第 2 次 · 逐字段核对原始授权 · 通过/)).toBeInTheDocument();
    await u.click(book.getByRole('tab', { name: '技术详情' }));
    expect(book.getByRole('heading', { name: '后端时间线' })).toBeInTheDocument();
    await u.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('sends one request per action even when tapped twice, with version and idempotency headers', async () => {
    const u = user();
    const button = await startCase(u);
    let release!: () => void;
    backend.once('POST /api/session/evidence/authorized-intent', { status: 200, body: (await import('./test/fixtures/evidence.json')).default['authorized-intent'], hold: new Promise((r) => { release = r; }) });
    await u.click(button);
    expect(panel().getByRole('button', { name: '正在向本地实验服务请求…' })).toBeDisabled();
    await u.click(panel().getByRole('button', { name: '正在向本地实验服务请求…' }));
    await act(async () => release());
    await panel().findByText(/唯一亲手批准/);
    const inspects = backend.calls.filter((c) => c.path === '/api/session/evidence/authorized-intent');
    expect(inspects).toHaveLength(1);
    expect(inspects[0]?.headers['idempotency-key']).toBeTruthy();
    expect(inspects[0]?.headers['x-lab-version']).toBe('epoch:1');
  });

  it('retries a lost response with the same key, and reloads the session after an idempotent replay', async () => {
    const u = user();
    const button = await startCase(u);
    backend.once('POST /api/session/evidence/', { status: 0, network: true });
    await u.click(button);
    await panel().findByText(/唯一亲手批准/);
    const inspects = backend.calls.filter((c) => c.path.startsWith('/api/session/evidence/'));
    expect(inspects).toHaveLength(2);
    expect(inspects[0]?.headers['idempotency-key']).toBe(inspects[1]?.headers['idempotency-key']);

    // A replayed (cached) response must not overwrite newer state: the client GETs the session.
    const evidence = (await import('./test/fixtures/evidence.json')).default;
    backend.once('POST /api/session/evidence/payment-request', { status: 200, body: evidence['payment-request'], headers: { 'Idempotency-Replayed': 'true', 'X-Lab-Version': 'epoch:0' } });
    backend.session!.evidence.find((e: { id: string }) => e.id === 'payment-request').inspected = true;
    const before = backend.count('GET /api/session');
    await u.click(place('支付中继站'));
    await u.click(await panel().findByRole('button', { name: '读取 API 消息' }));
    await panel().findByText(/那不归中继管/);
    expect(backend.count('GET /api/session') - before).toBeGreaterThanOrEqual(2);
    // The stale cached version was not adopted for the next action.
    await u.click(place('Bob 的画室'));
    await u.click(await panel().findByRole('button', { name: '摊开两份完整地址' }));
    const compare = backend.calls.find((c) => c.path.endsWith('field-comparison'));
    expect(compare?.headers['x-lab-version']).not.toBe('epoch:0');
  });

  it('refreshes from the backend after a stale-state conflict', async () => {
    const u = user();
    const button = await startCase(u);
    backend.once('POST /api/session/evidence/', { status: 409, body: { error: { code: 'stale-state', message: 'Session changed.' } } });
    // Something else moved the session on: the refresh must show the backend's state.
    backend.session!.evidence.find((e: { id: string }) => e.id === 'authorized-intent').inspected = true;
    await u.click(button);
    expect(await screen.findByRole('alert')).toHaveTextContent('实验状态已在别处更新');
    await waitFor(() => expect(screen.getByLabelText('调查进度 1/5')).toBeInTheDocument());
  });

  it('explains a network failure and recovers when the service is back', async () => {
    const u = user();
    backend.once('GET /api/mission', { status: 0, network: true });
    render(<App />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('无法连接本地实验服务');
    expect(alert).toHaveTextContent('python.exe -m genesis.lab');
    await u.click(within(alert).getByRole('button', { name: '重新连接' }));
    expect(await screen.findByRole('button', { name: '开始调查' })).toBeEnabled();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('reports an unavailable local chain without showing a result', { timeout: 30000 }, async () => {
    const u = user();
    await collectEvidence(u);
    await u.click(panel().getByRole('radio', { name: /逐字段核对原始授权/ }));
    await u.click(panel().getByRole('button', { name: '锁定这条规则' }));
    await panel().findByRole('button', { name: '规则已锁定' });
    backend.once('POST /api/session/replay', { status: 503, body: { error: { code: 'chain-unavailable', message: 'Anvil is not running.' } } });
    await u.click(panel().getByRole('button', { name: '在本地链上运行两笔请求' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('本地链没有就绪：Anvil is not running.');
    expect(screen.queryByRole('heading', { name: /意图守住了|验证没有守住/ })).not.toBeInTheDocument();
  });

  it('resumes an existing backend session with its result', async () => {
    backend.session = JSON.parse(JSON.stringify(stateReplayedFailed));
    render(<App />);
    expect(await screen.findByRole('heading', { name: '验证没有守住' })).toBeInTheDocument();
    expect(screen.getByLabelText('调查进度 5/5')).toBeInTheDocument();
    // Re-opening already-inspected evidence for the cards.
    expect(backend.count('POST /api/session/evidence/')).toBe(5);
  });

  it('shows the hint in Chinese from the backend hint text', async () => {
    const u = user();
    await startCase(u);
    await u.click(screen.getByRole('button', { name: /提示 0\/4/ }));
    expect(await screen.findByRole('status')).toHaveTextContent('侦探笔记 · 提示 1/4');
    expect(screen.getByRole('button', { name: /提示 1\/4/ })).toBeInTheDocument();
  });

  it('restarting from the evidence book opens a fresh case back at the studio', { timeout: 20000 }, async () => {
    const u = user();
    await u.click(await startCase(u));
    await panel().findByText(/唯一亲手批准/);
    await u.click(place('支付中继站'));
    await panel().findByRole('button', { name: '读取 API 消息' });
    await u.click(screen.getByRole('button', { name: '📒 证据册' }));
    const book = within(screen.getByRole('dialog', { name: '证据册' }));
    await u.click(book.getByRole('tab', { name: '技术详情' }));
    await u.click(book.getByRole('button', { name: '重新开始整个调查' }));
    await u.click(book.getByRole('button', { name: '确认：清空证据，重新开始' }));
    expect(await panel().findByRole('button', { name: '查看原始授权' })).toBeEnabled();
    expect(screen.getByLabelText('调查进度 0/5')).toBeInTheDocument();
    expect(backend.calls.filter((c) => c.method === 'POST' && c.path === '/api/session')).toHaveLength(2);
  });
});

