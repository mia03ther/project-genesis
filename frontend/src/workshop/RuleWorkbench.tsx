import { useState } from "react";
import { blankRule, expression, ruleSource, seals, tryRule } from "./rules";
import type { Rule } from "./rules";

export function RuleWorkbench({
  onCraft,
  onEdit,
}: {
  onCraft: (source: string) => void;
  onEdit: () => void;
}) {
  const [rule, setRule] = useState<Rule>(blankRule);
  const [tested, setTested] = useState<ReturnType<typeof tryRule> | null>(null);
  const solved = tested?.every((v) => v.correct) ?? false;
  return (
    <section className="rule-workbench" aria-labelledby="forge-title">
      <div className="forge-intro">
        <span className="workshop-eyebrow">工坊试炼 / 01</span>
        <h2 id="forge-title">打造一枚验证印章</h2>
        <p>
          选好印记，让正常的付款通行，拦住被改过的请求。试错不花费任何资金。
        </p>
        <div className="forge-seals">
          {seals.map((s) => (
            <button
              key={s.id}
              aria-pressed={rule[s.id]}
              onClick={() => {
                setRule((old) => ({ ...old, [s.id]: !old[s.id] }));
                setTested(null);
                onEdit();
              }}
            >
              <span aria-hidden="true">{s.symbol}</span>
              <strong>{s.name}</strong>
              <small>{s.detail}</small>
            </button>
          ))}
        </div>
        <div className="forge-actions">
          <button
            className="btn primary"
            onClick={() => setTested(tryRule(rule))}
          >
            试炼 · 放入四张请求
          </button>
          <button
            className="btn"
            disabled={!solved}
            onClick={() => onCraft(ruleSource(rule))}
          >
            铸成练习代码
          </button>
        </div>
      </div>
      <div className="forge-trial">
        <div
          className={`forge-stamp${solved ? " complete" : ""}`}
          aria-hidden="true"
        >
          <span>{solved ? "✧" : "◇"}</span>
          <i>{seals.filter((s) => rule[s.id]).length} / 3</i>
        </div>
        <ul className="forge-samples" aria-label="四张请求的教学预览">
          {tryRule(rule).map((v, i) => (
            <li
              key={v.name}
              className={
                !tested
                  ? "waiting"
                  : tested[i]!.correct
                    ? "correct"
                    : "incorrect"
              }
            >
              <span aria-hidden="true">
                {!tested ? "·" : tested[i]!.correct ? "✓" : "×"}
              </span>
              <strong>{v.name}</strong>
              <small>
                {!tested ? "等待试炼" : tested[i]!.accepts ? "放行" : "拦截"}
              </small>
            </li>
          ))}
        </ul>
        <p className="forge-verdict" role="status">
          {tested
            ? solved
              ? "四张样本都处理正确。可以铸成代码，再去编译验证。"
              : `处理正确 ${tested.filter((v) => v.correct).length}/4 张。看看哪一道印记还没有装上。`
            : "装上印记，再按「试炼」看看会发生什么。"}
        </p>
      </div>
      <details className="forge-formula">
        <summary>看看印章对应的代码</summary>
        <code>return {expression(rule)};</code>
      </details>
      <p className="workshop-note forge-boundary">
        这里预览的是你拼装的三条规则。它不执行下方编辑的
        Solidity，也不改变链上委托成绩。
      </p>
    </section>
  );
}
