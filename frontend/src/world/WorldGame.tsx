import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import type { Lab } from "../game/useLab";
import type {
  AuthorizationContent,
  EvidenceItem,
  RequestContent,
} from "../api";
import { useLab } from "../game/useLab";
import { EvidenceBody, evidenceTitle } from "../game/cards";
import { CHOICE_ZH, VARIANT_ZH } from "../game/text";
import { PixelPortrait } from "./art";
import { HEIGHT, places, WIDTH, World } from "./engine";
import type { PlaceId } from "./engine";
import { camera, renderWorld } from "./render";
import { Dialogue } from "./Dialogue";
import { saveExploration } from "./checkpoint";
import "./world.css";

type Panel = PlaceId | "menu" | null;
const speakers = {
  alice: "Alice",
  relay: "中继员",
  bob: "Bob",
  wallet: "Nomi",
  warehouse: "仓库看守",
  workshop: "工坊匠人",
  menu: "Nomi",
};
const movement = new Set([
  "w",
  "a",
  "s",
  "d",
  "arrowup",
  "arrowdown",
  "arrowleft",
  "arrowright",
  "shift",
]);
const words: Record<PlaceId, string> = {
  alice:
    "我是 Alice。Bob 帮我画了新作品，能帮我核对一下这笔付款吗？先收好我的原始授权。",
  relay:
    "这里是支付中继。请求已经到了，金额和收款地址都写在单子上。它说的，和 Alice 批准的是一回事吗？",
  bob: "欢迎来画室。名字可能相似，地址才是账户的身份。把两份文件放在一起看看吧。",
  wallet:
    "把你的判断装进付款终端。它会在本地链上分别试一次正常请求和地址被替换的请求，每次都从相同状态开始。",
  warehouse: "这里不是 Bob 的画室。查查链上账户，看看请求里的地址到底是谁。",
  workshop:
    "想亲手写一条验证规则？工坊里有一份可编辑的 Solidity 练习，和可选的 Remix 编辑器。",
};

export function WorldGame({
  onNavigate,
  initialWorld,
}: {
  onNavigate: (view: "workshop" | "space") => void;
  initialWorld?: World;
}) {
  const lab = useLab();
  const [world] = useState(() => initialWorld ?? new World());
  return <GameScene lab={lab} world={world} onNavigate={onNavigate} />;
}

export function GameScene({
  lab,
  world,
  onNavigate,
}: {
  lab: Lab;
  world: World;
  onNavigate: (view: "workshop" | "space") => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const [panel, setPanel] = useState<Panel>(null);
  const [near, setNear] = useState<PlaceId | null>(null);
  const [message, setMessage] = useState(
    "你就是 Nomi。按 WASD 走走看，也可以点击地面。",
  );
  const [selected, setSelected] = useState("");
  const [journal, setJournal] = useState(false);
  const [mapOpen, setMapOpen] = useState(false);
  const [saved, setSaved] = useState(true);
  const [position, setPosition] = useState({
    x: world.x,
    y: world.y,
    signals: 0,
    delivered: false,
  });
  const live = useRef({ lab, panel });
  live.current = { lab, panel };

  function close() {
    setPanel(null);
    world.keys.clear();
    world.target = null;
    canvas.current?.focus();
  }
  function interact(id?: PlaceId) {
    const place = places.find((p) => p.id === (id ?? world.nearby()?.id));
    if (!place) {
      setMessage("靠近角色或终端，再按 E。Alice 在左上方。");
      return;
    }
    world.keys.clear();
    world.target = null;
    setPanel(place.id);
    setJournal(false);
    const current = live.current.lab;
    if (
      current.session &&
      place.evidence &&
      (!current.evidence[place.evidence] || place.evidence === "chain-accounts")
    ) {
      const entry = current.session.evidence.find(
        (e) => e.id === place.evidence,
      );
      if (entry && !entry.locked) void current.inspect(place.evidence);
    }
  }
  const interaction = useRef(interact);
  interaction.current = interact;

  useEffect(() => {
    const save = () => {
      try {
        setSaved(saveExploration(world, window.localStorage));
      } catch {
        setSaved(false);
      }
    };
    const timer = window.setInterval(save, 2000);
    window.addEventListener("pagehide", save);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("pagehide", save);
      try {
        saveExploration(world, window.localStorage);
      } catch {
        /* Movement remains available without browser storage. */
      }
    };
  }, [world]);

  useEffect(() => {
    const motion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const node = canvas.current;
    const ctx = node?.getContext("2d");
    if (!node) return;
    let width = 1,
      height = 1,
      last = 0,
      sample = 0,
      frame = 0;
    const resize = () => {
      const rect = node.getBoundingClientRect();
      width = rect.width || 1000;
      height = rect.height || 700;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      node.width = Math.round(width * dpr);
      node.height = Math.round(height * dpr);
      ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);
    const tick = (time: number) => {
      const delta = last ? (time - last) / 1000 : 0;
      last = time;
      if (!live.current.panel && !document.hidden) world.update(delta);
      if (ctx)
        renderWorld(
          ctx,
          world,
          width,
          height,
          time / 1000,
          live.current.lab.result,
          motion?.matches,
        );
      if (time - sample > 100) {
        sample = time;
        setNear(world.nearby()?.id ?? null);
        setPosition({
          x: world.x,
          y: world.y,
          signals: world.signals.filter((s) => s.found).length,
          delivered: world.toyDelivered,
        });
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    const clear = () => {
      world.keys.clear();
      world.target = null;
    };
    const down = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      if (key === "escape") {
        setPanel((old) => (old ? null : "menu"));
        clear();
        node.focus();
        return;
      }
      const target = event.target as HTMLElement | null;
      if (
        live.current.panel ||
        target?.closest("input,textarea,select,button,a,[contenteditable]")
      )
        return;
      if (movement.has(key) || key === " " || key === "e")
        event.preventDefault();
      if (movement.has(key)) world.keys.add(key);
      if (!event.repeat && key === "m") setMapOpen((old) => !old);
      if (!event.repeat && key === "e") interaction.current();
      if (!event.repeat && key === " ") setMessage(world.space());
    };
    const up = (event: KeyboardEvent) =>
      world.keys.delete(event.key.toLowerCase());
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", clear);
    document.addEventListener("visibilitychange", clear);
    node.focus();
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", clear);
      document.removeEventListener("visibilitychange", clear);
      clear();
    };
  }, [world]);

  useEffect(() => {
    if (!panel) return;
    world.keys.clear();
    world.target = null;
    (
      dialog.current?.querySelector<HTMLElement>("[data-dialogue-next]") ??
      dialog.current?.querySelector<HTMLElement>("button")
    )?.focus();
  }, [panel, world]);
  useEffect(() => {
    // An accepted commission removes its button; a completed replay removes
    // the rule form. Keep focus inside the surviving dialogue after either.
    if (panel && !dialog.current?.contains(document.activeElement)) {
      (
        dialog.current?.querySelector<HTMLElement>("[data-dialogue-next]") ??
        dialog.current?.querySelector<HTMLElement>("button")
      )?.focus();
    }
  }, [panel, lab.busy, lab.result]);
  useEffect(() => {
    setSelected(lab.session?.choice?.id ?? "");
  }, [lab.session?.choice?.id, lab.session?.attempt]);
  useEffect(() => {
    if (position.signals)
      setMessage(
        position.signals === 3
          ? "三枚信号碎片收齐了！可以继续送包裹，或者去完成委托。"
          : `信号碎片 ${position.signals}/3。继续在岛上找找。`,
      );
  }, [position.signals]);
  useEffect(() => {
    if (position.delivered)
      setMessage(
        "练习包裹送到 Bob 门口了！探索挑战完成，链上委托仍需去终端验证。",
      );
  }, [position.delivered]);

  const has = (id: string) => Boolean(lab.evidence[id]);
  const ready = has("authorized-intent") && has("payment-request");
  const goal: PlaceId = lab.result?.passed
    ? "workshop"
    : !lab.session || !has("authorized-intent")
      ? "alice"
      : !has("payment-request")
        ? "relay"
        : "wallet";
  const goalText = lab.result
    ? lab.result.passed
      ? "委托完成！去工坊继续创造，或者留在岛上玩。"
      : "看看钱去了哪里。去付款终端回溯，再试一种规则。"
    : goal === "alice"
      ? "找 Alice 接委托 · 西北工作室"
      : goal === "relay"
        ? "去中继站取付款请求 · 东北方"
        : "去付款终端试试你的规则 · 南边广场";
  const place = places.find((p) => p.id === panel);
  const item = place?.evidence ? lab.evidence[place.evidence] : undefined;
  const entry = lab.session?.evidence.find((e) => e.id === place?.evidence);
  const point = places.find((p) => p.id === goal)!;
  const busy = Boolean(lab.busy);
  const narration =
    panel && panel !== "menu"
      ? panel === "alice" && lab.session
        ? [
            "授权书交给你了。",
            "去东面的中继站取请求吧。",
            "看清楚：我想付给的，是 Bob。",
          ]
        : panel === "bob" && position.delivered
          ? [
              "包裹收到了，谢谢你！",
              "我们再看看付款地址——名字像，可不代表是同一个人。",
            ]
          : (words[panel].match(/[^。！？]+[。！？]?/g) ?? [words[panel]])
      : [];

  function walk(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (panel || event.pointerType === "touch") return;
    const rect = event.currentTarget.getBoundingClientRect();
    const view = camera(world, rect.width, rect.height);
    world.target = {
      x: (event.clientX - rect.left) / view.scale + view.x,
      y: (event.clientY - rect.top) / view.scale + view.y,
    };
    event.currentTarget.focus();
  }
  function pad(
    event: ReactPointerEvent<HTMLButtonElement>,
    key: string,
    pressed: boolean,
  ) {
    event.preventDefault();
    if (pressed) {
      event.currentTarget.setPointerCapture?.(event.pointerId);
      world.keys.add(key);
    } else world.keys.delete(key);
  }

  return (
    <main className="world-game" aria-label="GENESIS 漫游岛">
      <canvas
        ref={canvas}
        tabIndex={0}
        aria-label="游戏场景。WASD 或方向键移动，Shift 跑动，E 互动，空格拿起或抛出包裹，Esc 菜单。"
        onPointerDown={walk}
      />
      <header className="world-hud">
        <a href="#" className="world-logo">
          genesis<span> / NOMI ISLAND</span>
        </a>
        <div className="world-network">ANVIL · 本地练习</div>
        <button
          aria-label="查看地图 M"
          aria-pressed={mapOpen}
          onClick={() => {
            setMapOpen((old) => !old);
            canvas.current?.focus();
          }}
        >
          地图 <kbd>M</kbd>
        </button>
        <button
          aria-label="打开游戏菜单"
          onClick={() => {
            world.keys.clear();
            setPanel("menu");
          }}
        >
          ☰
        </button>
      </header>
      <section className="world-objective" aria-label="当前目标">
        <span>委托 001 / 错付疑云</span>
        <p>{goalText}</p>
        <div>
          <i className={has("authorized-intent") ? "done" : ""}>1</i>接委托
          <b>—</b>
          <i className={has("payment-request") ? "done" : ""}>2</i>取请求
          <b>—</b>
          <i className={lab.result?.passed ? "done" : ""}>3</i>试规则
        </div>
      </section>
      <aside
        className="world-map"
        aria-label="小地图"
        hidden={!mapOpen || Boolean(panel)}
      >
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} aria-hidden="true">
          <rect
            x="35"
            y="35"
            width="1530"
            height="1030"
            rx="120"
            fill="#f0efe5"
          />
          {places.map((p) => (
            <g key={p.id}>
              <rect
                x={p.x - 65}
                y={p.y - 90}
                width="130"
                height="90"
                rx="15"
                fill={p.color}
              />
              <text
                x={p.x}
                y={p.y + 60}
                textAnchor="middle"
                fontSize="70"
                fill="#655776"
              >
                {p.id === "alice"
                  ? "A"
                  : p.id === "relay"
                    ? "R"
                    : p.id === "wallet"
                      ? "P"
                      : p.id === "bob"
                        ? "B"
                        : p.id === "workshop"
                          ? "⌘"
                          : "?"}
              </text>
            </g>
          ))}
          <circle
            cx={point.x}
            cy={point.y - 35}
            r="105"
            fill="none"
            stroke="#6e54ff"
            strokeWidth="15"
          />
          <circle
            cx={position.x}
            cy={position.y}
            r="42"
            fill="#6e54ff"
            stroke="white"
            strokeWidth="16"
          />
        </svg>
        <span>紫圈是目标 · 你是紫点</span>
      </aside>
      <div className="world-discoveries">
        ✦ {position.signals}/3 信号碎片
        {position.delivered && <span> · ✓ 包裹送达</span>}
        <small>探索小游戏 · 不计入链上成绩</small>
      </div>
      <div className="world-controls">
        <span>
          <kbd>W A S D</kbd> 移动
        </span>
        <span>
          <kbd>Shift</kbd> 跑
        </span>
        <span>
          <kbd>E</kbd> 互动
        </span>
        <span>
          <kbd>Space</kbd> 拿 / 抛 / 跳
        </span>
        <span>点击地面也能走</span>
      </div>
      {!panel && (
        <div className="world-bottom">
          <p role="status">{message}</p>
          <button
            className="world-interact"
            onClick={() => {
              interact();
              canvas.current?.focus();
            }}
          >
            {near
              ? `E · ${places.find((p) => p.id === near)?.name}`
              : "E · 附近互动"}
          </button>
        </div>
      )}
      {!panel && (
        <div className="world-touch" aria-label="触屏控制">
          <div className="direction-pad">
            {(
              [
                ["w", "↑"],
                ["a", "←"],
                ["s", "↓"],
                ["d", "→"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                className={`pad-${key}`}
                aria-label={`向${({ w: "上", a: "左", s: "下", d: "右" } as const)[key]}移动`}
                onPointerDown={(e) => pad(e, key, true)}
                onPointerUp={(e) => pad(e, key, false)}
                onPointerCancel={(e) => pad(e, key, false)}
                onLostPointerCapture={() => world.keys.delete(key)}
              >
                {label}
              </button>
            ))}
          </div>
          <button
            className="world-space"
            onClick={() => setMessage(world.space())}
          >
            拿 / 抛<br />
            跳跃
          </button>
        </div>
      )}
      {lab.error && (
        <div className="world-error" role="alert">
          <span>{lab.error.message}</span>
          <button disabled={busy} onClick={() => void lab.load()}>
            重新连接
          </button>
          <button onClick={lab.dismissError}>收起</button>
        </div>
      )}
      {panel && (
        <div className="world-dialog-shade">
          <div
            ref={dialog}
            className="world-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="world-dialog-title"
            onKeyDown={(e) => {
              if (e.key !== "Tab") return;
              const buttons = dialog.current?.querySelectorAll<HTMLElement>(
                "button:not(:disabled),a,input:not(:disabled),summary,textarea",
              );
              if (!buttons?.length) return;
              const first = buttons[0]!,
                last = buttons[buttons.length - 1]!;
              if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
              } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
              }
            }}
          >
            <header>
              <span>
                {panel === "menu" ? "PAUSED / 游戏暂停" : "NOMI ISLAND / 对话"}
              </span>
              <button aria-label="关闭对话，继续走动" onClick={close}>
                ✕
              </button>
            </header>
            <div className="world-speaker">
              <PixelPortrait kind={panel} />
              <span>{speakers[panel]}</span>
            </div>
            <h1 id="world-dialog-title">
              {panel === "menu" ? "歇一下，再出发。" : speakers[panel]}
              <small>{place?.name}</small>
            </h1>
            {panel === "menu" ? (
              <>
                <p>
                  WASD / 方向键移动，Shift 跑动，E
                  对话，空格拿起、抛出包裹或跳跃。把练习包裹送到 Bob
                  门口的圈里，路上还有 3 枚信号碎片。
                </p>
                <div className="world-menu-actions">
                  <button className="world-primary" onClick={close}>
                    继续游戏
                  </button>
                  <button onClick={() => onNavigate("workshop")}>
                    合约工坊
                  </button>
                  <button onClick={() => onNavigate("space")}>
                    伙伴空间 / 旧版任务面板
                  </button>
                  <button
                    onClick={() => {
                      world.x = 800;
                      world.y = 500;
                      world.target = null;
                      close();
                    }}
                  >
                    回到广场（保留任务进度）
                  </button>
                </div>
                <p className="world-note">
                  WASD 小岛是客户端玩法原型；实验成绩来自 Python + Anvil。未连接
                  Monad Testnet 或 DSH。触屏方向键可用，尚未实机验证 iPhone。
                </p>
                <p className="world-note">
                  {saved
                    ? "探索位置与收集物会保存在此浏览器。"
                    : "浏览器暂未保存探索记录，刷新可能丢失岛上进度。"}
                  链上委托进度由本地实验服务管理。
                </p>
              </>
            ) : (
              <>
                <Dialogue
                  key={`${panel}:${Boolean(lab.session)}:${position.delivered}`}
                  lines={narration}
                />
                {!lab.session && panel !== "workshop" ? (
                  <>
                    {panel !== "alice" && (
                      <p>
                        先去 Alice
                        的工作室接受委托，再开始调查。小岛随时可以自由探索。
                      </p>
                    )}
                    {panel === "alice" && (
                      <button
                        className="world-primary"
                        disabled={!lab.mission || busy}
                        onClick={() => void lab.accept()}
                      >
                        {busy ? "正在准备本地实验…" : "好，我接下了！"}
                      </button>
                    )}
                  </>
                ) : null}
                {item &&
                  (panel === "wallet" ? (
                    <details className="world-evidence">
                      <summary>查看待签交易草稿（尚未发送）</summary>
                      <EvidenceBody item={item} />
                    </details>
                  ) : (
                    <EvidenceSlip item={item} />
                  ))}
                {lab.session && place?.evidence && !item && (
                  <div className="world-read">
                    <p>
                      {entry?.locked
                        ? "先拿到 Alice 的授权和中继站的请求，再来对照。"
                        : busy
                          ? "正在读取真实实验数据…"
                          : "文件还没打开。"}
                    </p>
                    <button
                      disabled={busy || entry?.locked}
                      onClick={() => void lab.inspect(place.evidence)}
                    >
                      读取{evidenceTitle(place.evidence, "文件")}
                    </button>
                  </div>
                )}
                {panel === "wallet" && lab.session && !lab.result && (
                  <>
                    <p>
                      {ready
                        ? "选一条规则，直接启动实验。你可以放心试错。"
                        : "先找 Alice 接委托，再去中继站读请求。"}
                    </p>
                    <fieldset className="world-rules" disabled={busy || !ready}>
                      <legend>你想如何验证付款？</legend>
                      {lab.mission?.choices.map((c) => (
                        <label
                          key={c.id}
                          className={selected === c.id ? "selected" : ""}
                        >
                          <input
                            type="radio"
                            name="world-rule"
                            value={c.id}
                            checked={selected === c.id}
                            onChange={() => setSelected(c.id)}
                          />
                          <span>
                            <strong>{CHOICE_ZH[c.id]?.label ?? c.label}</strong>
                            <small>{CHOICE_ZH[c.id]?.detail ?? c.detail}</small>
                          </span>
                        </label>
                      ))}
                    </fieldset>
                    <button
                      className="world-primary"
                      disabled={!selected || busy || !ready}
                      onClick={() => void lab.experiment(selected)}
                    >
                      {lab.busy === "replay"
                        ? "本地链正在试跑两份请求…"
                        : "启动终端 · 试跑两份请求"}
                    </button>
                  </>
                )}
                {panel === "wallet" && lab.result && (
                  <section className="world-result">
                    <h2>
                      {lab.result.passed
                        ? "✓ 委托完成！"
                        : "这次的钱，走对了吗？"}
                    </h2>
                    <p>
                      {lab.result.passed
                        ? "正常付款通过，异常请求被拦下。"
                        : "实验发现了问题。对照实际收款人和余额，再试一条规则。"}
                    </p>
                    {lab.result.variants.map((v) => (
                      <article key={v.id}>
                        <strong>
                          {VARIANT_ZH[v.id] ?? v.title} · {v.score}/
                          {v.max_score}
                        </strong>
                        <p>
                          {v.transaction
                            ? `收据状态 ${v.transaction.status} · 收款人 ${v.transaction.to.label ?? v.transaction.to.address} · ${v.transaction.value.ether}`
                            : "没有发送交易，未产生交易收据"}
                        </p>
                        <details>
                          <summary>查看余额与裁判证据</summary>
                          {v.transaction && (
                            <code>交易 {v.transaction.hash}</code>
                          )}
                          {v.balances.map((b) => (
                            <p key={b.label}>
                              {b.label}: {b.before.ether} → {b.after.ether}
                            </p>
                          ))}
                          {v.criteria.map((c) => (
                            <p key={c.id}>
                              {c.passed ? "✓" : "✗"} {c.check}: {c.explanation}
                            </p>
                          ))}
                        </details>
                      </article>
                    ))}
                    <div className="world-menu-actions">
                      <button
                        className="world-primary"
                        disabled={busy}
                        onClick={() => void lab.reset()}
                      >
                        回溯，再试一次
                      </button>
                      <button disabled={busy} onClick={() => void lab.report()}>
                        下载实验报告
                      </button>
                      <button onClick={() => onNavigate("workshop")}>
                        去工坊写规则 ↗
                      </button>
                    </div>
                  </section>
                )}
                {panel === "workshop" && (
                  <button
                    className="world-primary"
                    onClick={() => onNavigate("workshop")}
                  >
                    进入合约工坊 ↗
                  </button>
                )}
                {lab.session && (
                  <>
                    <button
                      className="world-journal-toggle"
                      aria-expanded={journal}
                      onClick={() => setJournal(!journal)}
                    >
                      随身证据本 · {Object.keys(lab.evidence).length} 份{" "}
                      {journal ? "−" : "+"}
                    </button>
                    {journal && (
                      <div className="world-journal">
                        {Object.values(lab.evidence).map((e) => (
                          <details key={e.id}>
                            <summary>{evidenceTitle(e.id, e.title)}</summary>
                            <EvidenceBody item={e} />
                          </details>
                        ))}
                      </div>
                    )}
                  </>
                )}
                <button className="world-leave" onClick={close}>
                  继续走走 <kbd>Esc</kbd>
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </main>
  );
}

function EvidenceSlip({ item }: { item: EvidenceItem }) {
  const [open, setOpen] = useState(false);
  if (item.kind === "authorization" || item.kind === "request") {
    const c = item.content as AuthorizationContent | RequestContent;
    const address = "recipient" in c ? c.recipient.address : c.pay_to.address;
    return (
      <div className="world-paper">
        <div>
          <span>
            {item.kind === "authorization" ? "收到原始授权" : "收到付款请求"}
          </span>
          <strong>
            {c.value.ether.replace(" ether", " 测试 ETH")} · 链 {c.chain_id}
          </strong>
        </div>
        <code>{address}</code>
        <details onToggle={(e) => setOpen(e.currentTarget.open)}>
          <summary>展开完整文件</summary>
          {open && <EvidenceBody item={item} />}
        </details>
      </div>
    );
  }
  return (
    <details
      className="world-evidence"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>{evidenceTitle(item.id, item.title)}</summary>
      {open && <EvidenceBody item={item} />}
    </details>
  );
}
