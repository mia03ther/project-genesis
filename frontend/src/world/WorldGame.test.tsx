import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { forgetLabVersion } from "../api";
import { FakeLab } from "../test/fakeBackend";
import { ProductApp } from "../product/ProductApp";
import { World } from "./engine";
import { WorldGame } from "./WorldGame";

let backend: FakeLab;
beforeEach(() => {
  backend = new FakeLab();
  localStorage.clear();
  forgetLabVersion();
  window.history.replaceState(null, "", "/");
  vi.stubGlobal("fetch", vi.fn(backend.fetch));
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  vi.stubGlobal("scrollTo", vi.fn());
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
const field = () => screen.getByLabelText(/^游戏场景/);
function visit(world: World, x: number, y: number) {
  world.x = x;
  world.y = y;
  field().focus();
  fireEvent.keyDown(field(), { key: "e" });
}

describe("Playable island", () => {
  it("is the front door, accepts real movement keys and clears them on blur", async () => {
    render(<ProductApp />);
    expect(
      screen.getByRole("main", { name: "GENESIS 漫游岛" }),
    ).toBeInTheDocument();
    await waitFor(() => expect(backend.count("GET /api/session")).toBe(1));
    fireEvent.keyDown(field(), { key: " " });
    expect(screen.getByRole("status")).toHaveTextContent("拿到");
    expect(backend.count("POST")).toBe(0);
    expect(screen.getByLabelText("小地图")).not.toBeVisible();
    fireEvent.keyDown(field(), { key: "m" });
    expect(screen.getByLabelText("小地图")).toBeVisible();
    fireEvent.keyDown(field(), { key: "m" });
    expect(screen.getByLabelText("小地图")).not.toBeVisible();
    fireEvent.keyDown(field(), { key: "Escape" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "继续游戏" }));
    expect(field()).toHaveFocus();
  });
  it("stops movement during dialogue, supports keyboard release and touch controls", async () => {
    const world = new World();
    render(<WorldGame initialWorld={world} onNavigate={vi.fn()} />);
    fireEvent.keyDown(field(), { key: "d" });
    world.update(0.05);
    expect(world.x).toBe(811);
    fireEvent.keyUp(window, { key: "d" });
    expect(world.keys.size).toBe(0);
    fireEvent.keyDown(field(), { key: "w" });
    fireEvent.blur(window);
    expect(world.keys.size).toBe(0);
    visit(world, 340, 350);
    expect(world.keys.size).toBe(0);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "d" });
    expect(world.keys.size).toBe(0);
    fireEvent.keyDown(window, { key: "Escape" });
    const right = screen.getByRole("button", { name: "向右移动" });
    fireEvent.pointerDown(right, { pointerId: 1 });
    expect(world.keys.has("d")).toBe(true);
    fireEvent.pointerCancel(right, { pointerId: 1 });
    expect(world.keys.size).toBe(0);
  });
  it("plays failure, rewind and success through nearby interactions and real API-shaped results", async () => {
    const user = userEvent.setup();
    const world = new World();
    world.x = 340;
    world.y = 350;
    render(<WorldGame initialWorld={world} onNavigate={vi.fn()} />);
    await waitFor(() => expect(backend.count("GET /api/session")).toBe(1));
    visit(world, 340, 350);
    await user.click(screen.getByRole("button", { name: "好，我接下了！" }));
    expect(
      await screen.findByText("0x0000000000000000000000000000000000000b0b"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("INV-0042", { exact: true }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByText("展开完整文件"));
    expect(
      await screen.findByText("INV-0042", { exact: true }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /关闭对话/ }));
    visit(world, 1220, 350);
    expect(
      await screen.findByText("0x00000000000000000000000000000000000f0b0b"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /关闭对话/ }));
    visit(world, 800, 790);
    const weak = await screen.findByRole("radio", { name: /照单全付/ });
    await waitFor(() => expect(weak).toBeEnabled());
    await user.click(weak);
    await user.click(screen.getByRole("button", { name: /启动终端/ }));
    expect(
      await screen.findByRole("heading", { name: "这次的钱，走对了吗？" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/收款人 unknown/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "回溯，再试一次" }));
    const safe = await screen.findByRole("radio", {
      name: /逐字段核对原始授权/,
    });
    await user.click(safe);
    await user.click(screen.getByRole("button", { name: /启动终端/ }));
    expect(
      await screen.findByRole("heading", { name: "✓ 委托完成！" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("没有发送交易，未产生交易收据"),
    ).toBeInTheDocument();
    expect(backend.count("POST /api/session/replay")).toBe(2);
  }, 15000);
  it("does not run replay after a rejected choice or invent a successful result", async () => {
    const user = userEvent.setup();
    const world = new World();
    render(<WorldGame initialWorld={world} onNavigate={vi.fn()} />);
    await waitFor(() => expect(backend.count("GET /api/session")).toBe(1));
    visit(world, 340, 350);
    await user.click(screen.getByRole("button", { name: "好，我接下了！" }));
    await screen.findByText("0x0000000000000000000000000000000000000b0b");
    await user.click(screen.getByRole("button", { name: /关闭对话/ }));
    visit(world, 1220, 350);
    await screen.findByText("0x00000000000000000000000000000000000f0b0b");
    await user.click(screen.getByRole("button", { name: /关闭对话/ }));
    visit(world, 800, 790);
    const safe = await screen.findByRole("radio", {
      name: /逐字段核对原始授权/,
    });
    await waitFor(() => expect(safe).toBeEnabled());
    await user.click(safe);
    backend.once("POST /api/session/choice", {
      status: 409,
      body: { error: { code: "stale-state", message: "stale" } },
    });
    await user.click(screen.getByRole("button", { name: /启动终端/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("已同步");
    expect(backend.count("POST /api/session/replay")).toBe(0);
    expect(
      screen.queryByRole("heading", { name: "✓ 委托完成！" }),
    ).not.toBeInTheDocument();
  });
});
