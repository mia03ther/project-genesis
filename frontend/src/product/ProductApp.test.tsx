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
import { ProductApp } from "./ProductApp";
import { EXPLORATION_KEY } from "../world/checkpoint";

let backend: FakeLab;
beforeEach(() => {
  backend = new FakeLab();
  localStorage.clear();
  forgetLabVersion();
  window.history.replaceState(null, "", "/#space");
  vi.stubGlobal("fetch", vi.fn(backend.fetch));
  vi.stubGlobal("scrollTo", vi.fn());
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("Unified GENESIS companion product", () => {
  it("returns from the workshop at the saved island location", async () => {
    const canvasContext = vi
      .spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockReturnValue(null);
    try {
      localStorage.setItem(
        EXPLORATION_KEY,
        JSON.stringify({ version: 1, x: 340, y: 350 }),
      );
      window.history.replaceState(null, "", "#workshop");
      render(<ProductApp />);
      await userEvent
        .setup()
        .click(screen.getByRole("button", { name: "返回小岛" }));
      await waitFor(() => expect(backend.count("GET /api/session")).toBe(1));
      fireEvent.keyDown(screen.getByLabelText(/^游戏场景/), { key: "e" });
      expect(screen.getByRole("dialog", { name: /Alice/ })).toBeInTheDocument();
      expect(window.location.hash).toBe("");
    } finally {
      canvasContext.mockRestore();
    }
  });
  it("keeps petting separate from grades and opens the same product mission", async () => {
    const user = userEvent.setup();
    render(<ProductApp />);
    await user.click(await screen.findByRole("button", { name: "摸摸 Nomi" }));
    expect(screen.getByRole("status")).toHaveTextContent("再摸一下也可以");
    expect(backend.count("POST")).toBe(0);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /和 Nomi 接个委托/ }),
      ).toBeEnabled(),
    );
    await user.click(screen.getByRole("button", { name: /和 Nomi 接个委托/ }));
    expect(
      screen.getByRole("heading", { name: "错付疑云" }),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe("#mission");
  });

  it("plays a backend failure, resets, and then verifies a passing strategy", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "#mission");
    render(<ProductApp />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "拆开委托" })).toBeEnabled(),
    );
    await user.click(screen.getByRole("button", { name: "拆开委托" }));
    await user.click(
      await screen.findByRole("button", { name: "查看 Alice 的授权" }),
    );
    await user.click(
      await screen.findByRole("button", { name: "读取 API 请求" }),
    );
    expect(
      (await screen.findAllByText("0x00000000000000000000000000000000000f0b0b"))
        .length,
    ).toBeGreaterThan(0);
    await user.click(screen.getByRole("radio", { name: /照单全付/ }));
    await user.click(screen.getByRole("button", { name: "装配这条规则" }));
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /运行两份请求/ }),
      ).toBeEnabled(),
    );
    await user.click(screen.getByRole("button", { name: /运行两份请求/ }));
    expect(
      await screen.findByRole("heading", {
        name: "结果不对？这就是实验的意义。",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("unknown", { exact: true })).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "回溯，再试一种规则" }),
    );
    await user.click(
      await screen.findByRole("radio", { name: /逐字段核对原始授权/ }),
    );
    await user.click(screen.getByRole("button", { name: "装配这条规则" }));
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /运行两份请求/ }),
      ).toBeEnabled(),
    );
    await user.click(screen.getByRole("button", { name: /运行两份请求/ }));
    expect(
      await screen.findByRole("heading", { name: "这次，意图守住了。" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("没有发送交易，未产生交易收据"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /把规则写成合约/ }));
    expect(
      screen.getByRole("heading", { name: "把你的判断写成合约" }),
    ).toBeInTheDocument();
    expect(backend.count("POST /api/session/replay")).toBe(2);
  }, 20000);

  it("can recover from an unavailable backend without presenting a false result", async () => {
    backend.once("GET /api/mission", {
      status: 503,
      body: {
        error: { code: "chain-unavailable", message: "Anvil unavailable" },
      },
    });
    render(<ProductApp />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Anvil unavailable",
    );
    expect(
      screen.queryByRole("heading", { name: "这次，意图守住了。" }),
    ).not.toBeInTheDocument();
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "重新连接" }));
    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
    );
  });
});
