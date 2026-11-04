import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import type {
  AuthorizationContent,
  EvidenceItem,
  RequestContent,
} from "../api";
import { App as LegacyGame } from "../App";
import { EvidenceBody } from "../game/cards";
import { CHOICE_ZH, HINT_ZH, VARIANT_ZH } from "../game/text";
import { useLab } from "../game/useLab";
import type { Lab } from "../game/useLab";
import { Workshop } from "../workshop/Workshop";
import { WorldGame } from "../world/WorldGame";
import { World } from "../world/engine";
import mascot from "../../../genesis/pet/assets/companion.png";
import identity from "../../../genesis/pet/assets/identity.json";
import "./product.css";

type View = "home" | "space" | "mission" | "workshop" | "town";
function currentView(): View {
  const hash = window.location.hash.slice(1);
  return hash === "space" ||
    hash === "mission" ||
    hash === "workshop" ||
    hash === "town"
    ? hash
    : "home";
}

export function ProductApp() {
  const [view, setView] = useState<View>(currentView);
  const [world] = useState(() => new World());
  useEffect(() => {
    const update = () => setView(currentView());
    window.addEventListener("hashchange", update);
    window.addEventListener("popstate", update);
    return () => {
      window.removeEventListener("hashchange", update);
      window.removeEventListener("popstate", update);
    };
  }, []);
  function navigate(next: View) {
    window.history.pushState(
      null,
      "",
      next === "home" ? window.location.pathname : `#${next}`,
    );
    setView(next);
    window.scrollTo?.(0, 0);
  }
  if (view === "town")
    return (
      <>
        <div className="archive-toolbar">
          <button onClick={() => navigate("home")}>← 返回 Nomi 空间</button>
          <span>历史像素原型 · 保留用于回归与对照</span>
        </div>
        <LegacyGame />
      </>
    );
  if (view === "home")
    return <WorldGame onNavigate={navigate} initialWorld={world} />;
  if (view === "workshop")
    return (
      <div className="product">
        <Workshop onClose={() => navigate("home")} />
      </div>
    );
  return <CompanionSpace view={view} navigate={navigate} />;
}

function CompanionSpace({
  view,
  navigate,
}: {
  view: "space" | "mission";
  navigate: (view: View) => void;
}) {
  const lab = useLab();
  const [reaction, setReaction] = useState("");
  const [selected, setSelected] = useState("");
  useEffect(() => {
    if (!reaction) return;
    const timer = window.setTimeout(() => setReaction(""), 4500);
    return () => window.clearTimeout(timer);
  }, [reaction]);
  useEffect(() => {
    setSelected(lab.session?.choice?.id ?? "");
  }, [lab.session?.choice?.id, lab.session?.attempt]);
  const speech =
    reaction ||
    (lab.error
      ? "连接有点问题。我们先在这里等一会。"
      : lab.busy === "replay"
        ? "正在做真实实验。结果出来前，我先不下结论。"
        : lab.result
          ? lab.result.passed
            ? "这次守住了。Bob 收到了付款，可疑请求被拦下。"
            : "发现一个漏洞。回溯一下，我们还能再试。"
          : "先陪你待一会。想冒险的时候，我们就拆开那封委托。");
  const count = lab.session?.evidence.filter((e) => e.inspected).length ?? 0;
  const brand = {
    "--purple": identity.colors.primary,
    "--purple-light": identity.colors.lavender,
    "--black": identity.colors.ink,
    "--off-white": identity.colors.paper,
  } as CSSProperties;
  return (
    <div className="product" style={brand}>
      <aside className="product-sidebar" aria-label="GENESIS 导航">
        <a
          className="product-wordmark"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("home");
          }}
        >
          <span className="genesis-mark">g</span> genesis
          <span className="wordmark-dot">.</span>
        </a>
        <div className="product-nav">
          <span className="nav-caption">YOUR COMPANION SPACE</span>
          {(
            [
              ["home", "◉", "回到游戏"],
              ["space", "♡", "伙伴空间"],
              ["mission", "↗", "安全委托"],
              ["workshop", "⌘", "合约工坊"],
            ] as const
          ).map(([id, icon, name]) => (
            <button
              key={id}
              aria-current={view === id ? "page" : undefined}
              onClick={() => navigate(id)}
            >
              <span aria-hidden="true">{icon}</span>
              {name}
              {id === "mission" && <small>01</small>}
            </button>
          ))}
        </div>
        <div className="sidebar-companion">
          <img src={mascot} alt="Nomi，GENESIS 的原创紫色伙伴" />
          <div>
            <strong>Nomi</strong>
            <span>你的链上学习搭子</span>
          </div>
          <i aria-label="本机伙伴" />
        </div>
        <p className="sidebar-foot">
          独立运行，无需模型密钥。
          <br />
          DSH 连接仍在规划中。
        </p>
      </aside>
      <div className="product-content">
        <header className="product-topbar">
          <span>
            {view === "space"
              ? "一点陪伴，一点新发现。"
              : "委托 001 / 错付疑云"}
          </span>
          <span className="environment-pill">
            <i />
            本地 Anvil 实验
          </span>
        </header>
        {lab.error && (
          <div className="product-error" role="alert">
            <p>{lab.error.message}</p>
            <button
              disabled={Boolean(lab.busy)}
              onClick={() => void lab.load()}
            >
              重新连接
            </button>
            <button onClick={lab.dismissError}>收起</button>
          </div>
        )}
        {view === "space" ? (
          <>
            <section className="companion-hero">
              <div className="hero-copy">
                <span className="product-eyebrow">
                  MEET YOUR LITTLE GUARDIAN
                </span>
                <h1>
                  有个小伙伴，
                  <br />
                  陪你看懂链上世界。
                </h1>
                <p>
                  认识 Nomi。平时是桌面上的一点陪伴，
                  <br className="desktop-break" />
                  遇到可疑委托，就一起查清楚。
                </p>
                <div className="hero-actions">
                  <button
                    className="product-primary"
                    disabled={!lab.loaded || Boolean(lab.busy)}
                    onClick={() => navigate("mission")}
                  >
                    和 Nomi 接个委托 <span>↗</span>
                  </button>
                  <button
                    className="product-secondary"
                    onClick={() => setReaction("嗯，收到了。再摸一下也可以。")}
                  >
                    摸摸 Nomi
                  </button>
                </div>
                <div className="hero-proof">
                  <span>不需要钱包</span>
                  <span>可以放心试错</span>
                  <span>结果来自真实本地链</span>
                </div>
              </div>
              <div className={`companion-stage${reaction ? " delighted" : ""}`}>
                <div className="stage-orbit orbit-one" />
                <div className="stage-orbit orbit-two" />
                <span className="stage-star star-one">✦</span>
                <span className="stage-star star-two">+</span>
                <div className="companion-speech" role="status">
                  {speech}
                </div>
                <button
                  className="mascot-touch"
                  aria-label="摸摸 Nomi 角色"
                  onClick={() =>
                    setReaction("我在。重要的签名，我们一起慢慢看。")
                  }
                >
                  <img src={mascot} alt="" />
                </button>
                <div className="companion-pedestal" />
                <div className="companion-name">
                  NOMI <span>YOUR GENESIS COMPANION</span>
                </div>
                <button
                  className="feed-button"
                  onClick={() =>
                    setReaction("小点心收到！喂食不会改变你的实验成绩。")
                  }
                >
                  ＋ 喂个小点心
                </button>
              </div>
            </section>
            <section className="home-bottom">
              <div className="mission-invitation">
                <div>
                  <span className="product-eyebrow">
                    一封新委托 / 约 5–10 分钟
                  </span>
                  <h2>“金额对了，收款人呢？”</h2>
                  <p>
                    Alice 批准了给 Bob 的付款。但一条看似正常的请求，让 Nomi
                    有点在意。
                  </p>
                </div>
                <button
                  className="round-go"
                  aria-label="打开错付疑云委托"
                  onClick={() => navigate("mission")}
                >
                  ↗
                </button>
              </div>
              <div className="learning-note">
                <span>PLAY → UNDERSTAND → BUILD</span>
                <h3>玩懂了，再亲手写出来。</h3>
                <p>把刚学到的验证规则，带进 Solidity 和 Remix。</p>
                <button onClick={() => navigate("workshop")}>
                  走进合约工坊 ↗
                </button>
              </div>
            </section>
          </>
        ) : (
          <section className="mission-space" aria-labelledby="mission-title">
            <div className="mission-heading">
              <div>
                <span className="product-eyebrow">
                  NOMI’S FIRST REQUEST / 001
                </span>
                <h1 id="mission-title">错付疑云</h1>
                <p>你的目标：让正确的付款通过，让被替换的请求停下来。</p>
              </div>
              <div className="mini-companion">
                <img src={mascot} alt="" />
                <span>{speech}</span>
              </div>
            </div>
            {!lab.session ? (
              <div className="mission-envelope">
                <span className="envelope-symbol" aria-hidden="true">
                  ↗
                </span>
                <h2>Alice 的付款委托</h2>
                <p>
                  她要支付 1.5 测试 ETH 给插画师
                  Bob。你可以先看看授权，再决定如何处理付款请求。
                </p>
                <button
                  className="product-primary"
                  disabled={!lab.mission || Boolean(lab.busy)}
                  onClick={() => void lab.start()}
                >
                  {lab.busy === "start" ? "正在准备实验…" : "拆开委托"}
                </button>
              </div>
            ) : (
              <>
                <div className="mission-strip">
                  <span>第 {lab.session.attempt} 次实验</span>
                  <span>
                    已收集 {count}/{lab.session.evidence.length} 份证据
                  </span>
                  <span>
                    {lab.busy === "replay"
                      ? "正在执行"
                      : lab.result
                        ? "裁判结果已返回"
                        : "尚未发送交易"}
                  </span>
                </div>
                <div className="document-pair">
                  {["authorized-intent", "payment-request"].map((id) => (
                    <Document key={id} id={id} lab={lab} />
                  ))}
                </div>
                <div className="evidence-tools">
                  {lab.session.evidence
                    .filter(
                      (e) =>
                        !["authorized-intent", "payment-request"].includes(
                          e.id,
                        ),
                    )
                    .map((e) => (
                      <button
                        key={e.id}
                        disabled={Boolean(lab.busy) || e.locked}
                        onClick={() => void lab.inspect(e.id)}
                      >
                        {e.inspected ? "✓ " : "+ "}
                        {(
                          {
                            "field-comparison": "逐字段核对",
                            "chain-accounts": "查询账户档案",
                            "transaction-draft": "预览待签交易",
                          } as Record<string, string>
                        )[e.id] ?? e.title}
                      </button>
                    ))}
                  <button
                    disabled={Boolean(lab.busy) || !lab.session.allowed.hint}
                    onClick={() => void lab.hint()}
                  >
                    给我一点提示
                  </button>
                </div>
                {lab.lastHint && (
                  <p className="nomi-hint" role="status">
                    Nomi 的提示：{HINT_ZH[lab.lastHint] ?? lab.lastHint}
                  </p>
                )}
                {Object.values(lab.evidence)
                  .filter(
                    (e) =>
                      !["authorized-intent", "payment-request"].includes(e.id),
                  )
                  .map((e) => (
                    <details className="product-evidence-detail" key={e.id}>
                      <summary>{e.title}</summary>
                      <EvidenceBody item={e} />
                    </details>
                  ))}
                {!lab.result ? (
                  <section className="rule-bench">
                    <div>
                      <span className="product-eyebrow">
                        BUILD YOUR CHECKPOINT
                      </span>
                      <h2>给钱包装上一条规则。</h2>
                      <p>
                        你可以选择不同的做法，再让本地链验证结果。阅读两份文件后即可装配。
                      </p>
                    </div>
                    <fieldset
                      disabled={
                        Boolean(lab.busy) || !lab.session.allowed.choose
                      }
                    >
                      <legend>验证策略</legend>
                      <div className="rule-options">
                        {lab.mission?.choices.map((c) => (
                          <label
                            key={c.id}
                            className={selected === c.id ? "selected" : ""}
                          >
                            <input
                              type="radio"
                              name="rule"
                              value={c.id}
                              checked={selected === c.id}
                              onChange={() => setSelected(c.id)}
                            />
                            <strong>{CHOICE_ZH[c.id]?.label ?? c.label}</strong>
                            <span>{CHOICE_ZH[c.id]?.detail ?? c.detail}</span>
                          </label>
                        ))}
                      </div>
                    </fieldset>
                    <div className="rule-actions">
                      <button
                        className="product-secondary"
                        disabled={!selected || Boolean(lab.busy)}
                        onClick={() => void lab.choose(selected)}
                      >
                        装配这条规则
                      </button>
                      <button
                        className="product-primary"
                        disabled={
                          Boolean(lab.busy) ||
                          !lab.session.allowed.replay ||
                          selected !== lab.session.choice?.id
                        }
                        onClick={() => void lab.replay()}
                      >
                        {lab.busy === "replay"
                          ? "正在运行真实实验…"
                          : "运行两份请求 ↗"}
                      </button>
                    </div>
                  </section>
                ) : (
                  <Outcome lab={lab} navigate={navigate} />
                )}
                <details className="product-journal">
                  <summary>实验记录与技术证据</summary>
                  {lab.session.timeline.map((t) => (
                    <p key={t.seq}>
                      <strong>{t.title}</strong>
                      <br />
                      {t.detail}
                    </p>
                  ))}
                </details>
              </>
            )}
          </section>
        )}
        <footer className="product-footer">
          <span>GENESIS · 陪伴式 Web3 安全学习原型</span>
          <span>筹备 Monad Blitz · 当前链为本地 Anvil，未接入 Monad</span>
          <button onClick={() => navigate("town")}>查看历史像素原型</button>
        </footer>
      </div>
    </div>
  );
}

function Document({ id, lab }: { id: string; lab: Lab }) {
  const item = lab.evidence[id];
  const isIntent = id === "authorized-intent";
  const facts = item?.content as
    | AuthorizationContent
    | RequestContent
    | undefined;
  const address = facts
    ? "recipient" in facts
      ? facts.recipient.address
      : facts.pay_to.address
    : null;
  return (
    <article
      className={`product-document ${isIntent ? "original" : "incoming"}`}
    >
      <div className="document-header">
        <span>
          {isIntent ? "01 / ALICE’S APPROVAL" : "02 / INCOMING REQUEST"}
        </span>
        <span>{isIntent ? "原始授权" : "待核对输入"}</span>
      </div>
      <h2>{isIntent ? "Alice 真正批准了什么？" : "API 实际要求付给谁？"}</h2>
      {item && facts ? (
        <>
          <div className="document-amount">
            {facts.value.ether.replace(/\s*ether$/, "")} <small>测试 ETH</small>
          </div>
          <span className="address-caption">完整收款地址</span>
          <code className="document-address">{address}</code>
          <p>
            网络 ID {facts.chain_id} ·{" "}
            {isIntent ? "来自原始委托" : "来自模拟支付 API"}
          </p>
          <details>
            <summary>查看完整文件</summary>
            <EvidenceBody item={item as EvidenceItem} />
          </details>
        </>
      ) : (
        <>
          <div className="sealed-document" aria-hidden="true">
            {isIntent ? "↗" : "?"}
          </div>
          <p>
            {isIntent
              ? "查看付款人最初记录的意图。"
              : "请求的金额看似正确，地址呢？"}
          </p>
          <button
            className="product-secondary"
            disabled={Boolean(lab.busy)}
            onClick={() => void lab.inspect(id)}
          >
            {isIntent ? "查看 Alice 的授权" : "读取 API 请求"}
          </button>
        </>
      )}
    </article>
  );
}

function Outcome({
  lab,
  navigate,
}: {
  lab: Lab;
  navigate: (view: View) => void;
}) {
  const result = lab.result!;
  return (
    <section
      className={`product-outcome ${result.passed ? "passed" : "failed"}`}
      aria-labelledby="outcome-title"
    >
      <span className="product-eyebrow">VERIFIED BY THE LOCAL ENGINE</span>
      <h2 id="outcome-title">
        {result.passed ? "这次，意图守住了。" : "结果不对？这就是实验的意义。"}
      </h2>
      <p>{CHOICE_ZH[result.choice.id]?.feedback ?? result.choice.feedback}</p>
      <div className="outcome-paths">
        {result.variants.map((v) => (
          <article key={v.id}>
            <h3>{VARIANT_ZH[v.id] ?? v.title}</h3>
            <div className="transfer-path">
              <span>Alice</span>
              <span aria-hidden="true">{v.transaction ? "→" : "⊣"}</span>
              <strong>
                {v.transaction
                  ? (v.transaction.to.label ?? v.transaction.to.address)
                  : "停在签名前"}
              </strong>
            </div>
            <p>
              {v.transaction
                ? v.transaction.status === 1
                  ? `${v.transaction.value.ether} 测试 ETH · 已提交且收据成功`
                  : "已提交，但收据失败"
                : "没有发送交易，未产生交易收据"}
            </p>
            <span className="outcome-score">
              {v.status === "passed" ? "验证通过" : "验证未通过"} · {v.score}/
              {v.max_score}
            </span>
            <details>
              <summary>余额变化与收据</summary>
              {v.balances.map((b) => (
                <p key={b.label}>
                  {b.label}: {b.before.ether} → {b.after.ether} ETH
                </p>
              ))}
              {v.transaction && <code>{v.transaction.hash}</code>}
              <p>快照恢复验证：{v.reset_verified ? "通过" : "未通过"}</p>
            </details>
          </article>
        ))}
      </div>
      <div className="rule-actions">
        <button
          className="product-secondary"
          disabled={Boolean(lab.busy)}
          onClick={() => void lab.reset()}
        >
          回溯，再试一种规则
        </button>
        <button
          className="product-secondary"
          disabled={Boolean(lab.busy)}
          onClick={() => void lab.report()}
        >
          导出真实实验报告
        </button>
        {result.passed && (
          <button
            className="product-primary"
            onClick={() => navigate("workshop")}
          >
            把规则写成合约 ↗
          </button>
        )}
      </div>
    </section>
  );
}
