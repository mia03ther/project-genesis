# Project GENESIS — 一页 pitch / One-page pitch

**一句话：文明三分钟兴衰——押注幸存者；每个纪元都以一个任何人都能重算的哈希收尾。不是 GameFi——没有代币，没有投机。**
*One line: civilisations rise and fall in 3 minutes — bet on the survivor;
every epoch ends in a hash anyone can recompute. Not GameFi — no token, no
speculation.*

## 一局怎么玩 | The 60-second loop

一个纪元是 4 个文明并排跑——Aurora、Boreas、Cinder、Dune——各是一个真实
的 60 天小世界，5 个居民。纪元开跑之前，你用游戏币押一个文明——你觉得
谁活得最好，谁就是「幸存者」。赢家按生存分：`存活人数 × 1,000,000 +
财富（分）+ 总健康 × 100`，人口第一；平局按纪元摘要的哈希裁定。结算按
注金比例分池子，庄家抽水 0；没人押中赢家则全额退款。一条命令，不用私钥，
不用联网：`python main.py epoch --bet you:2:100`。默认纪元
（`epoch:42:60:4:5:0:10`）Cinder 以 5,144,627 分获胜，纪元摘要
`b25c8fb3e94f746b…`，任何人重跑都必须得到同一个摘要。
*One epoch is four civilisations racing in parallel — Aurora, Boreas,
Cinder, Dune — each a real 60-day mini-world with 5 residents. Before it
runs, you bet play-money points on who survives best — the survivor. The
winner is the highest survival score: `alive × 1,000,000 + wealth_cents +
total_health × 100`, population first; ties are broken by the epoch
digest's hash. Settlement is parimutuel with house fee 0; if nobody backed
the winner, every stake is refunded in full. One command, no key, no
network: `python main.py epoch --bet you:2:100`. The default epoch
(`epoch:42:60:4:5:0:10`) is won by Cinder with 5,144,627 points, epoch
digest `b25c8fb3e94f746b…` — anyone re-running it must get the same digest.*

## 问题 | The problem

学 Web3 是碎片化的：教程、文档、测试网各说各话；新手的第一笔交易既吓人
又不可撤销；黑客松演示大多是假的——录好的界面、写死的数字，评委无法验证。
*Learning Web3 is fragmented: tutorials, docs and testnets don't connect; a
beginner's first transaction is scary and irreversible; most hackathon demos
are fake — recorded screens and hard-coded numbers no judge can verify.*

## GENESIS 是什么 | What it is

一个**确定性文明模拟 + 下注循环 + 分级链上学习场景**。一个纪元里 4 个文
明各跑 60 天，每一步都被记录、每一条不变量都被检查，整个纪元哈希成一个
摘要。**它是可以玩的**：押一个文明，看四个世界兴衰，结算当场发生；换种
子（43 号纪元 Boreas 赢）、关市场（下单数 2，四个文明全饿死，平局由摘要
哈希裁定，Dune 赢），赢家当场跟着变——因果看得见。学习者按版本化场景一步
步走：先在本地练，再上真实测试网，每一步都有确定性评分器打分。
*A deterministic civilization simulation plus a betting loop plus graded
on-chain learning scenarios — and it is playable. In one epoch, four
civilisations each run 60 days; every step is logged, every invariant
checked, and the whole epoch hashes to one digest. Bet on a civilisation,
watch four worlds rise and fall, settle on the spot; change the seed (seed
43 → Boreas wins) or shut the market (2 orders a day → all starve, the
digest-hash tiebreak picks Dune) and the winner changes in front of you —
cause and effect you can see. Learners progress through versioned scenarios:
practice locally first, then go to the real testnet, graded deterministically
at each step.*

## 为什么是 Monad | Why Monad

快、便宜、公开、永久。链上不存世界，只存一个摘要锚点——世界永远在链下可
重跑，链只负责证明「这个世界存在过」。纪元结算完马上开下一局，结算必须
快 finalized 才跟得上循环——Monad 的快区块和并行执行给的就是这个快终结。
一笔真实转账只花 0.002415 MON 手续费。
*Fast, cheap, public, permanent. The chain stores no world, only one digest
anchor — the world stays reproducible off-chain; the chain only proves "this
world existed". Each epoch settles and the next starts right away, so
settlement has to finalise fast — Monad's fast blocks and parallel execution
give the loop that pace. One real transfer cost 0.002415 MON in fees.*

## 实时证据 | Live proof （全部可验证，nothing staged）

- **确定性：** 默认纪元 `epoch:42:60:4:5:0:10`，摘要 `b25c8fb3e94f746bf4d29fd7118ecd0fb72b23b8386eda76b35830e00cfab9fc`，任何机器重跑都一样；Cinder 5,144,627 分获胜（Aurora 5,143,163、Boreas 5,144,121、Dune 5,143,061）。浏览器移植版逐位一致（`node frontend/verify_epochs.mjs`：3/3 黄金纪元，赢家和赔付一模一样）。
- **下注循环：** 游戏币默认（演示积分 · 不是真钱），不用钱包、不用私钥；庄家抽水 0，没人押中赢家则全额退款。真实测试网模式是另外的、可选的、明确标注的，只用测试 MON——`python main.py epoch --real-testnet` 只打印链上事实，不下注、不领奖。
- **世界锚定：** 种子 42、100 天的世界，状态摘要 `8ed4e8d7dd86fafc`（完整：`8ed4e8d7dd86fafce0ec09064a239b599d0eb596f4588d69b249cbbd1ad201c6`），任何机器重跑都一样；3,867 笔交易，3,890 单位，12,350.97 积分，健康度 100.0，基尼系数 0.057 → 0.308。
- **真实交易：** Monad 测试网第一笔转账，场景 `first-monad-transfer`，判定 **13/13 通过**。交易哈希 `0x4b66b46fba5301e60452ae5d38c5e58e4f636302b7f80425777ef1a4355eae11`，区块 **78228932**，1.5 MON，手续费 0.002415 MON（21,000 gas @ 115 Gwei），发送方 5 → 3.497585 MON，接收方 0 → 1.5 MON。查证：https://testnet.monadexplorer.com/tx/0x4b66b46fba5301e60452ae5d38c5e58e4f636302b7f80425777ef1a4355eae11
- **测试：** 614 个测试全部通过；`GenesisLedger` 合约已用 Foundry 1.9.0 编译通过。
- **锚定（已完成）：** `GenesisLedger` 合约已部署在 Monad 测试网，地址 `0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1`（部署交易 `0xfc042b3927ea880c6517c1c6f20e458ef8b366cc6f1a8ca0dc0f9220e7170c00`，手续费 0.04775 MON）。世界摘要 `8ed4e8d7dd86fafc` 已写入链上，锚定交易 `0xd035cdda274104d6958300f0022562a3cebde1e3f370d49fe2061bcad5fc433f`（第 100 天、20 人、3,867 笔交易）。任何人可用 `cast call 0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1 "getDigest(uint256)(bytes32)" 100 --rpc-url https://testnet-rpc.monad.xyz` 取回，或用只读命令 `python main.py monad verify --tx 0x4b66b46fba5301e60452ae5d38c5e58e4f636302b7f80425777ef1a4355eae11` 验证交易，并与本地重跑结果比对。查证：https://testnet.monadexplorer.com/tx/0xd035cdda274104d6958300f0022562a3cebde1e3f370d49fe2061bcad5fc433f

## 团队与诉求 | Team & ask

Project GENESIS，Monad Blitz（广州，一日黑客松）参赛作品。演示 60 秒：下注
→ 看纪元跑完 → 结算 → 链上验摘要。仓库：github.com/mia03ther/project-genesis。
诉求：请评委验证我们的证据——跑一次纪元、押一次文明、查一次交易哈希。
*Project GENESIS, built for Monad Blitz (Guangzhou, one-day hackathon). A
60-second demo: bet → watch the epoch → settle → verify the digest on-chain.
Repo: github.com/mia03ther/project-genesis. Our ask: verify our evidence — run
the epoch once, bet on a civilisation once, check the transaction hash once.*

---
*Monad Testnet: chain 10143 · RPC https://testnet-rpc.monad.xyz · Faucet https://faucet.monad.xyz · 演示脚本：docs/DEMO_SCRIPT.md · 循环设计：docs/EPOCH_BETTING.md · 链上事实：frontend/chain.json*
