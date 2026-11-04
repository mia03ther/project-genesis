import { describe, expect, it } from "vitest";
import { starter } from "./lesson";
import { blankRule, expression, ruleSource, tryRule } from "./rules";

describe("Four-sample workbench, separate from Solidity compilation", () => {
  it("shows the missing-address failure and succeeds only with all three checks", () => {
    const weak = tryRule({ recipient: false, amount: true, chain: true });
    expect(weak.map((s) => s.correct)).toEqual([true, false, true, true]);
    expect(weak[1]?.accepts).toBe(true);
    for (let mask = 0; mask < 8; mask++) {
      const outcome = tryRule({
        recipient: !!(mask & 1),
        amount: !!(mask & 2),
        chain: !!(mask & 4),
      });
      expect(outcome.every((v) => v.correct)).toBe(mask === 7);
    }
  });
  it("generates the selected condition without editing the starter or executing source", () => {
    expect(expression(blankRule())).toBe("true");
    const complete = ruleSource({ recipient: true, amount: true, chain: true });
    expect(complete).toContain(
      "return recipient == APPROVED_RECIPIENT && amount == APPROVED_VALUE && chainId == APPROVED_CHAIN_ID;",
    );
    expect(complete).toContain("pragma solidity 0.8.28;");
    expect(complete).not.toContain("TODO");
    expect(starter).toContain("// TODO: also compare recipient");
  });
});
