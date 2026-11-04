// Developer-only check of repository-generated code, never browser/user drafts.
// Requires Node 24 and Foundry with Solidity 0.8.28 already cached.
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawnSync } = require("node:child_process");
const { stripTypeScriptTypes } = require("node:module");
const root = path.resolve(__dirname, "..");
const project = path.join(root, "reports", "crafted-check");
const starter = fs.readFileSync(
  path.join(root, "contracts/authorization/exercise/PaymentIntent.sol"),
  "utf8",
);
let generator = stripTypeScriptTypes(
  fs.readFileSync(path.join(root, "frontend/src/workshop/rules.ts"), "utf8"),
  { mode: "transform" },
);
generator = generator
  .replace(/import\s*\{[^}]*\}\s*from\s*["'][^"']+["'];/g, "")
  .replace(/export\s+/g, "");
// Only the fixed, repository-owned generator is executed. The browser's draft
// and localStorage are never read. ruleSource does not depend on sample vectors.
const source = new Function(
  "starter",
  "vectors",
  generator + "\nreturn ruleSource({recipient:true,amount:true,chain:true});",
)(starter, []);
fs.mkdirSync(path.join(project, "src"), { recursive: true });
fs.mkdirSync(path.join(project, "test"), { recursive: true });
fs.writeFileSync(path.join(project, "src/PaymentIntent.sol"), source);
fs.writeFileSync(
  path.join(project, "foundry.toml"),
  '[profile.default]\nsolc_version = "0.8.28"\nevm_version = "cancun"\nsrc = "src"\ntest = "test"\n',
);
fs.writeFileSync(
  path.join(project, "test/Generated.t.sol"),
  `// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;
import {PaymentIntent} from "../src/PaymentIntent.sol";
contract GeneratedTest {
    PaymentIntent v = new PaymentIntent();
    function testApproved() public view { require(v.matches(address(uint160(0x0b0b)), 1.5 ether, 31337)); }
    function testWrongRecipient() public view { require(!v.matches(address(uint160(0x0f0b0b)), 1.5 ether, 31337)); }
    function testWrongAmount() public view { require(!v.matches(address(uint160(0x0b0b)), 1 ether, 31337)); }
    function testWrongChain() public view { require(!v.matches(address(uint160(0x0b0b)), 1.5 ether, 1)); }
}
`,
);
const option = process.argv.indexOf("--forge");
const forge = option < 0 ? "forge" : process.argv[option + 1];
if (!forge) throw new Error("--forge needs an executable path");
// cwd avoids Foundry's relative-root resolution differences on Windows.
const run = spawnSync(forge, ["test", "--offline", "-vv"], {
  cwd: project,
  encoding: "utf8",
  shell: false,
});
const report = {
  format: "genesis.workshop-code-check",
  version: 1,
  checked_at: new Date().toISOString(),
  compiler: "0.8.28",
  source_sha256: crypto.createHash("sha256").update(source).digest("hex"),
  status: run.status === 0 ? "passed" : "failed",
  exit_code: run.status,
  checks: [
    "testApproved",
    "testWrongRecipient",
    "testWrongAmount",
    "testWrongChain",
  ],
  stdout: run.stdout ?? "",
  stderr: run.error?.message ?? run.stderr ?? "",
};
fs.writeFileSync(
  path.join(project, "report.json"),
  JSON.stringify(report, null, 2) + "\n",
);
process.stdout.write(report.stdout);
if (report.stderr) process.stderr.write(report.stderr);
console.log("Report: " + path.join(project, "report.json"));
process.exitCode = run.status === 0 ? 0 : 1;
