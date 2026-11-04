import { starter, vectors } from "./lesson";

export const seals = [
  {
    id: "recipient",
    name: "收款人印记",
    symbol: "◇",
    detail: "逐位核对完整地址",
    expression: "recipient == APPROVED_RECIPIENT",
  },
  {
    id: "amount",
    name: "金额印记",
    symbol: "≋",
    detail: "核对付款数额",
    expression: "amount == APPROVED_VALUE",
  },
  {
    id: "chain",
    name: "网络印记",
    symbol: "⌘",
    detail: "核对链 ID",
    expression: "chainId == APPROVED_CHAIN_ID",
  },
] as const;
export type Seal = (typeof seals)[number]["id"];
export type Rule = Record<Seal, boolean>;
export const blankRule = (): Rule => ({
  recipient: false,
  amount: false,
  chain: false,
});
export function expression(rule: Rule): string {
  return (
    seals
      .filter((s) => rule[s.id])
      .map((s) => s.expression)
      .join(" && ") || "true"
  );
}
/** A four-sample teaching preview; never executes or grades edited Solidity. */
export function tryRule(rule: Rule) {
  const approved = vectors[0];
  return vectors.map((sample) => {
    const accepts =
      (!rule.recipient || sample.address.toLowerCase() === approved.address) &&
      (!rule.amount || BigInt(sample.amount) === BigInt(approved.amount)) &&
      (!rule.chain || sample.chain === approved.chain);
    return {
      ...sample,
      accepts,
      correct: accepts === (sample.expected === "true"),
    };
  });
}
export function ruleSource(rule: Rule): string {
  return starter
    .replace(
      "// This starter is intentionally incomplete; it is NOT a safe validator.",
      "// Generated from the GENESIS teaching workbench. Test before use.",
    )
    .replace(
      "// TODO: also compare recipient with APPROVED_RECIPIENT.",
      "// Compare the fields selected at the teaching workbench.",
    )
    .replace(/return [^;]+;/, `return ${expression(rule)};`);
}
