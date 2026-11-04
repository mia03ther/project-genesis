import { useEffect, useRef, useState } from "react";
import {
  DRAFT_KEY,
  MAX_SOURCE_BYTES,
  reference,
  remixUrl,
  starter,
  vectors,
} from "./lesson";
import { PixelPortrait } from "../world/art";
import { RuleWorkbench } from "./RuleWorkbench";
import "./workshop.css";

export function Workshop({ onClose }: { onClose: () => void }) {
  const [source, setSource] = useState(() => {
    try {
      return localStorage.getItem(DRAFT_KEY) ?? starter;
    } catch {
      return starter;
    }
  });
  const [frame, setFrame] = useState("");
  const [message, setMessage] = useState("");
  const [confirmReset, setConfirmReset] = useState(false);
  const [referenceShown, setReferenceShown] = useState(false);
  const [pendingCraft, setPendingCraft] = useState<string | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const previousFocus = useRef(document.activeElement);
  const frameSource = useRef("");
  useEffect(() => {
    heading.current?.focus();
    return () => {
      if (previousFocus.current instanceof HTMLElement)
        previousFocus.current.focus();
    };
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem(DRAFT_KEY, source);
    } catch {
      setMessage("浏览器未能保存草稿，请下载备份。");
    }
  }, [source]);

  const tooLarge = new TextEncoder().encode(source).length > MAX_SOURCE_BYTES;
  const external = tooLarge ? undefined : remixUrl(source);
  function embed() {
    if (tooLarge) return;
    frameSource.current = source;
    setFrame(remixUrl(source, true));
    setMessage(
      "已请求打开官方 Remix。若编辑器空白或无法使用，请使用新窗口入口。",
    );
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(source);
      setMessage("代码已复制。");
    } catch {
      setMessage("复制不可用，请选中代码手动复制，或下载 .sol 文件。");
    }
  }
  function download() {
    const url = URL.createObjectURL(
      new Blob([source], { type: "text/plain;charset=utf-8" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "PaymentIntent.sol";
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setMessage("已请求下载 PaymentIntent.sol。");
  }
  function craft(next: string) {
    if (source !== starter && source !== next) {
      setPendingCraft(next);
      return;
    }
    setSource(next);
    setPendingCraft(null);
    setConfirmReset(false);
    setMessage(
      "印章已写入本机草稿。代码还没有编译，可以继续编辑或送入 Remix。",
    );
    document.getElementById("solidity-source")?.focus();
  }
  return (
    <main className="workshop" aria-labelledby="workshop-title">
      <header className="workshop-head">
        <div className="workshop-guide">
          <div className="workshop-portrait">
            <PixelPortrait kind="workshop" />
          </div>
          <div>
            <p className="kicker">NOMI ISLAND / 合约工坊</p>
            <h1 id="workshop-title" tabIndex={-1} ref={heading}>
              把你的判断写成合约
            </h1>
            <p>“先试着打造印章。看清它拦住了什么，再把规则刻进代码。”</p>
          </div>
        </div>
        <button className="btn" onClick={onClose}>
          返回小岛
        </button>
      </header>
      <RuleWorkbench onCraft={craft} onEdit={() => setPendingCraft(null)} />
      {pendingCraft && (
        <section className="workshop-draft-confirm" aria-label="替换草稿确认">
          <p>
            已有你编辑过的草稿。生成的练习代码将替换它；需要的话请先下载备份。
          </p>
          <button
            className="btn"
            onClick={() => {
              setSource(pendingCraft);
              setPendingCraft(null);
              setConfirmReset(false);
              setMessage("已将印章写入草稿，尚未编译。");
              document.getElementById("solidity-source")?.focus();
            }}
          >
            确认替换当前草稿
          </button>
          <button className="btn ghost" onClick={() => setPendingCraft(null)}>
            保留原草稿
          </button>
        </section>
      )}
      <div className="workshop-grid">
        <section className="workshop-lesson" aria-label="练习说明">
          <h2>修好缺失的收款人检查</h2>
          <p>
            初始代码只核对金额和链，故意漏了收款人。补全 <code>matches</code>
            ，使四组请求只有第一组返回 <code>true</code>。
          </p>
          <details className="workshop-howto">
            <summary>怎样在 Remix 里编译和验证？</summary>
            <ol>
              <li>修改右侧源码，再送入 Remix。中文注释也可以。</li>
              <li>
                在 Solidity Compiler 中选择 <strong>0.8.28</strong> 并编译。
              </li>
              <li>
                在 Deploy & Run 中选择 <strong>Remix VM</strong>，部署后展开{" "}
                <code>matches</code>。
              </li>
              <li>依次输入下方测试参数，检查实际返回值。</li>
            </ol>
          </details>
          <p className="workshop-note">
            这是不转账、不保管资金的教学函数。chainId
            是待核对的输入；它不能证明实际网络，也没有实现付款人身份验证。
          </p>
          <div className="workshop-vectors">
            {vectors.map((v) => (
              <details key={v.name}>
                <summary>
                  {v.name} · 期望 {v.expected}
                </summary>
                <code>
                  {v.address}, {v.amount}, {v.chain}
                </code>
                <p>期望值来自课程，不是对你当前代码的测试结果。</p>
              </details>
            ))}
          </div>
          <details onToggle={(e) => setReferenceShown(e.currentTarget.open)}>
            <summary>查看参考答案（先自己试一试）</summary>
            {referenceShown && <pre>{reference}</pre>}
          </details>
          <p className="workshop-note">
            GENESIS 不会读取跨站 Remix
            内的源码和测试结果。你的练习尚未自动评分；游戏成绩也不会因此改变。
          </p>
        </section>
        <section className="workshop-editor" aria-label="Solidity 草稿">
          <label htmlFor="solidity-source">PaymentIntent.sol · 本机草稿</label>
          <textarea
            id="solidity-source"
            spellCheck={false}
            value={source}
            onChange={(e) => {
              setSource(e.target.value);
              setConfirmReset(false);
              setPendingCraft(null);
            }}
          />
          <div className="row">
            <button className="btn" onClick={() => void copy()}>
              复制代码
            </button>
            <button className="btn" onClick={download}>
              下载 .sol
            </button>
            <button
              className="btn ghost"
              onClick={() => {
                if (!confirmReset) {
                  setConfirmReset(true);
                  return;
                }
                setSource(starter);
                setConfirmReset(false);
                setPendingCraft(null);
                setMessage("已恢复初始练习代码。");
              }}
            >
              {confirmReset ? "确认覆盖本机草稿" : "恢复初始代码"}
            </button>
          </div>
          {tooLarge && (
            <p role="alert">
              源码超过 24 KB，请缩短后再送入 Remix；下载和复制仍可用。
            </p>
          )}
        </section>
      </div>
      <section className="workshop-remix" aria-label="Remix 编辑器">
        <h2>在 Remix 里编写和运行</h2>
        <p>
          点击后才会连接第三方官方服务
          app.remix.live，并把当前源码带入编辑器。只在 Remix VM
          练习，无需连接钱包。
        </p>
        <p className="workshop-mobile">
          手机可以阅读、编辑与导出草稿。Remix
          官方不支持手机和平板；完整编译练习请在桌面浏览器继续。
        </p>
        <div className="row">
          <button
            className="btn primary workshop-embed-button"
            disabled={tooLarge}
            onClick={embed}
          >
            {frame ? "用当前草稿重新打开 Remix" : "启动内置 Remix"}
          </button>
          {external && (
            <a
              className="btn"
              href={external}
              target="_blank"
              rel="noopener noreferrer"
            >
              在新窗口打开 Remix ↗
            </a>
          )}
          {frame && (
            <button
              className="btn"
              onClick={() => {
                setFrame("");
                setMessage("已关闭 Remix。内置编辑器中的修改请先另行保存。");
              }}
            >
              关闭 Remix
            </button>
          )}
        </div>
        <p role="status" aria-live="polite">
          {message}
        </p>
        {frame && (
          <>
            <p className="workshop-note">
              Remix 内的改动不会同步回上方草稿。重新打开会载入上方源码；请先在
              Remix 中保存或导出。
              {source !== frameSource.current &&
                " 上方草稿已修改，尚未送入当前 Remix。"}
            </p>
            <iframe
              title="官方 Remix Solidity 编辑器"
              src={frame}
              referrerPolicy="no-referrer"
              sandbox="allow-scripts allow-same-origin allow-downloads allow-forms"
            />
          </>
        )}
      </section>
    </main>
  );
}
