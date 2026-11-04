import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Workshop } from './Workshop';
import { DRAFT_KEY, MAX_SOURCE_BYTES, remixUrl, starter } from './lesson';

afterEach(() => { cleanup(); localStorage.clear(); });

describe('Solidity workshop', () => {
  it('does not contact Remix until requested, and keeps lesson and source available offline', () => {
    const close = vi.fn();
    render(<Workshop onClose={close} />);
    expect(screen.queryByTitle('官方 Remix Solidity 编辑器')).not.toBeInTheDocument();
    expect(screen.getByLabelText('PaymentIntent.sol · 本机草稿')).toHaveValue(starter);
    fireEvent.click(screen.getByRole('button', { name: '返回伙伴空间' }));
    expect(close).toHaveBeenCalledOnce();
  });
  it('exports edited UTF-8 code in the official fragment and persists the draft', () => {
    render(<Workshop onClose={() => {}} />);
    const code = '// 中文练习\ncontract Example {}';
    fireEvent.change(screen.getByLabelText('PaymentIntent.sol · 本机草稿'), { target: { value: code } });
    expect(localStorage.getItem(DRAFT_KEY)).toBe(code);
    fireEvent.click(screen.getByRole('button', { name: '启动内置 Remix' }));
    expect(screen.getByTitle('官方 Remix Solidity 编辑器')).toHaveAttribute('src', remixUrl(code, true));
    const parsed = new URL(remixUrl(code));
    const bytes = Uint8Array.from(atob(new URLSearchParams(parsed.hash.slice(1)).get('code')!), c => c.charCodeAt(0));
    expect(new TextDecoder().decode(bytes)).toBe(code);
    expect(parsed.origin).toBe('https://app.remix.live');
  });
  it('requires a second click to overwrite a learner draft', () => {
    localStorage.setItem(DRAFT_KEY, 'my edits');
    render(<Workshop onClose={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '恢复初始代码' }));
    expect(screen.getByLabelText('PaymentIntent.sol · 本机草稿')).toHaveValue('my edits');
    fireEvent.click(screen.getByRole('button', { name: '确认覆盖本机草稿' }));
    expect(screen.getByLabelText('PaymentIntent.sol · 本机草稿')).toHaveValue(starter);
  });
  it('limits encoded source size without claiming to compile or grade it', () => {
    expect(() => remixUrl('a'.repeat(MAX_SOURCE_BYTES + 1))).toThrow('24 KB');
    render(<Workshop onClose={() => {}} />);
    expect(screen.getByText(/你的练习尚未自动评分/)).toBeInTheDocument();
  });
});
