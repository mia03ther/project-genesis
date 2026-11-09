# 60 秒评委演示脚本 — Project GENESIS × Monad Blitz（动手版）

> 这不是演讲，是现场玩一局。演示者全程动手操作，评委看的是因果，不是幻灯片。
>
> 定位（开场第一句就说清楚）：**civilisations rise and fall in 3 minutes —
> bet on the survivor; every epoch ends in a hash anyone can recompute.**
> 文明三分钟兴衰——押注幸存者；每个纪元都以一个任何人都能重算的哈希收尾。
> **不是 GameFi —— 没有代币，没有投机。**注是游戏币（演示积分 · 不是真钱），
> 默认不用钱包、不用私钥、不用联网；真实测试网模式是另外的、可选的、明确
> 标注的，只用测试 MON。
>
> 一局是什么：一个纪元是 4 个文明并排跑——Aurora、Boreas、Cinder、Dune——
> 各是一个真实的 60 天小世界，5 个居民，种子分别是 42000、42001、42002、
> 42003。赢家按生存分：`alive × 1,000,000 + wealth_cents + total_health × 100`，
> 人口第一，财富和健康其次；平局按纪元摘要的哈希裁定。默认纪元
> （`epoch:42:60:4:5:0:10`）四个文明全活 5 人，Cinder 以 5,144,627 分获胜
> （Aurora 5,143,163、Boreas 5,144,121、Dune 5,143,061）。结算按注金比例分
> 池子，庄家抽水 0；没人押中赢家则全额退款。
>
> 演示前检查：终端已 `cd` 到项目根目录、`.venv` 就绪；浏览器已打开三个
> 标签页（① 前端游乐场 `frontend/index.html` ② 转账交易链接
> ③ 锚定交易链接）；备用：终端里能 `cat reports/first-monad-transfer.json`。
>
> 全程只用已验证的数字（见上文，全部由引擎实测；614 个测试、真实交易哈希
> 见下）。不要临场编数字。
> 如果评委给了 3 分钟：60 秒主脚本跑完后，用剩下的时间加演——换种子（43
> 号纪元 Boreas 赢）、关市场（下单数 2，四个文明全饿死，平局由摘要哈希裁
> 定，Dune 赢），见下文「3 分钟加演」。

## 0:00–0:10 — 开场钩子：一句话，一个注

**展示什么（Show）：** 终端已打开，停在项目根目录。不要先放演示视频，
不要先讲架构。先说一句话，再打一条命令——命令里就带上了注：

```bash
python main.py epoch --bet you:2:100
```

**台词（Say）：**

> 「一句话：文明三分钟兴衰——押注幸存者；每个纪元都以一个任何人都能重算
> 的哈希收尾。这条命令就是一局：四个文明，Aurora、Boreas、Cinder、Dune，
> 各跑 60 天。我押 Cinder 100 游戏币——不用钱包，不用私钥。下面一秒钟，
> 四个世界一起跑完。」
>
> *EN: "One sentence: civilisations rise and fall in 3 minutes — bet on the
> survivor; every epoch ends in a hash anyone can recompute. This one command
> is a round: four civilisations — Aurora, Boreas, Cinder, Dune — each running
> 60 days. I'm putting 100 play credits on Cinder — no wallet, no key. In
> about a second, all four worlds will have run."*

**如果失败（Fallback）：** 终端出问题 → 直接打开浏览器前端游乐场，里面跑
的是同一套引擎的移植版（`node frontend/verify_epochs.mjs`：3/3 黄金纪元，
赢家和赔付逐位一致），口头说「我押 Cinder」，照着屏幕上的四个文明和分数读。

## 0:10–0:35 — 纪元开跑：四个世界，一个赢家

**展示什么（Show）：** 命令一秒跑完，JSON 打在屏幕上。不要切走，逐项读：
四个文明各 5 人全活、健康 500；财富 Cinder 94,627 最高，Boreas 94,121，
Aurora 93,163，Dune 93,061；生存分 Cinder 5,144,627 第一。说：「Cinder 赢
了，我押对了——赢 506 分，赢在财富。」再指结算部分：池子 100（只有我一
注），赢家池 100，赔付 100——「一注独赢，拿回自己的 100。」

**台词（Say）：**

> 「这不是录好的动画，每一个数字都是现在算出来的。Cinder 赢了，我押对了——
> 但重点不是我押对了，是这个结果任何人都能重算：四个文明的种子、参数、
> 赢家规则全写在输出里，换一台机器跑，摘要必须一模一样。」
>
> *EN: "Nothing here is pre-recorded — every number was just computed. Cinder
> won, so my bet won. But the point isn't that I won. It's that anyone can
> recompute this: all four seeds, parameters and the winner rule are in the
> output — run it on another machine and the digest must be identical."*

**如果失败（Fallback）：** 想让结算更热闹 → 再跑一条带两个注的：
`python main.py epoch --bet alice:2:100 --bet bob:0:100`——池子 200，
Cinder 赢，Alice 拿 200，Bob 拿 0。赔付永远加起来等于池子。

## 0:35–0:55 — 结算 + 证明：摘要上链

**展示什么（Show）：** 指着 JSON 里的纪元摘要
`b25c8fb3e94f746bf4d29fd7118ecd0fb72b23b8386eda76b35830e00cfab9fc`，说一句
「这个摘要，换一个数字就变」。然后切到浏览器标签页 ③（锚定交易）：
https://testnet.monadexplorer.com/tx/0xd035cdda274104d6958300f0022562a3cebde1e3f370d49fe2061bcad5fc433f
——读：合约 `0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1`，方法
`recordWorldDigest`，世界摘要 `8ed4e8d7dd86fafc`、第 100 天、20 人、
3,867 笔交易。然后回到终端，现场跑一条只读命令（不用私钥，不花钱）：

```bash
cast call 0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1 "getDigest(uint256)(bytes32)" 100 --rpc-url https://testnet-rpc.monad.xyz
```

返回 `0x8ed4e8d7dd86fafce0ec09064a239b599d0eb596f4588d69b249cbbd1ad201c6`——
和本地跑出来的种子 42、100 天世界摘要**一模一样**。说：「链上那个，就是
本地这个。纪元的摘要能重算，世界的摘要能上链——同一个证明逻辑。」

**台词（Say）：**

> 「结算完了，游戏币当场分完。但这个游戏真正可信的地方不在这里——在链上。
> 种子 42 的世界摘要已经写进 Monad 的合约里，任何人现在都能从链上把它读
> 回来，和自己本地跑出来的摘要比对，差一个数字都不行。」
>
> *EN: "Settled — the play-money points are paid out on the spot. But what
> makes this game trustworthy isn't here — it's on-chain: the seed-42 world's
> digest is already written into a contract on Monad. Anyone can read it back
> right now and compare it with their own local run. One digit off and it
> fails."*

**如果失败（Fallback）：** 浏览器页面加载慢 / 现场断网 → 立刻切回终端，
跑 `python main.py monad verify --tx
0x4b66b46fba5301e60452ae5d38c5e58e4f636302b7f80425777ef1a4355eae11`（只读
命令，会自己重试），口头读出交易哈希和 1.5 MON；或者跑
`python main.py epoch --real-testnet`，直接打出全部已验证的链上事实——
这个命令不跑纪元、不下注、不领奖。不要等页面转圈超过 5 秒。断网也不怕：
下注、跑纪元、结算全程离线，只有锚定这一步需要链，而那两笔交易的证据
已经在链上了。

## 0:55–1:00 — 收尾：一句话 + 请评委验证

**展示什么（Show）：** 回到终端，停住，看着评委。

**台词（Say）：**

> 「总结一句话：文明三分钟兴衰——押注幸存者；每个纪元都以一个任何人都能
> 重算的哈希收尾。世界是确定的，赌注是游戏币，证明是公开的。谢谢，请
> 提问——最好现场提一个种子，我当场跑给你看。」
>
> *EN: "One line to close: civilisations rise and fall in 3 minutes — bet on
> the survivor; every epoch ends in a hash anyone can recompute. The world is
> deterministic, the bet is play money, and the proof is public. Thank you —
> and if you have a question, give me a seed and I'll run it right now."*

---

## 3 分钟加演（如果时间允许）

60 秒主脚本跑完后，加演两条命令，证明「换个输入，世界就变，因果是真的」：

1. **换种子：** `python main.py epoch --seed 43 --bet you:1:100`——赢家变成
   **Boreas**（5,146,761 分），纪元摘要变成 `6561439a3eb4eb79…`。说：
   「换一个种子，赢家就换一个；换回来，赢家就回来。」
   *EN: "Change the seed, the winner changes; change it back, the winner
   comes back."*
2. **关市场：** `python main.py epoch --max-orders 2`——四个文明全饿死
   （0 人、分数全 0），赢家由摘要哈希的平局裁定规则决定：**Dune**。说：
   「市场一关，四个文明一起饿死——连平局怎么裁，规则都写死了，不用庄家
   说了算。」
   *EN: "Shut the market and all four civilisations starve together — and
   even how the tie is broken is written in the rule, not decided by the
   house."*

加演时顺带打开标签页 ②（转账交易）讲一句真实转账，见下文 Q3。

## 评委最可能问的 5 个问题（一句话答案）

1. **「这是 GameFi / 赌博吗？」**
   → 不是。没有代币、没有真钱、没有赚钱机制；注是游戏币（演示积分 ·
   不是真钱），默认不用钱包不用私钥；真实测试网模式是另外的、可选的、
   明确标注的，只用测试 MON，而且那个命令（`epoch --real-testnet`）根本
   不下注、不领奖。
   *EN: No — no token, no real money, no earning. Bets are play-money points
   (demo points, not real money) by default, no wallet or key needed; the
   real-testnet mode is separate, optional and clearly labelled, test MON
   only — and that command doesn't place a bet or claim a payout at all.*

2. **「结果能作弊吗？庄家能改吗？」**
   → 不能。赢家规则是公开的算式（人口第一，`alive × 1,000,000 +
   wealth_cents + total_health × 100`），纪元摘要覆盖每个文明的种子、世
   界摘要和分数输入，改一个数字摘要就变；平局按摘要哈希裁定，不用再跑一遍。
   *EN: No. The winner rule is a public formula (population first: alive ×
   1,000,000 + wealth_cents + total_health × 100); the epoch digest covers
   every civilisation's seed, world digest and score inputs — change one
   number and it changes; ties are settled by the digest hash.*

3. **「这笔交易真的是你们做的吗？怎么证明？」**
   → 浏览器链接就是证据：转账交易哈希 `0x4b66b46f…ae11`、区块 78228932、
   1.5 MON、手续费 0.002415 MON，发送方余额 5 → 3.497585，全部公开可查；
   锚定交易 `0xd035cdda…fc433f`、合约 `0x0D903C…ABA1` 同理；钱包在转账、
   部署、锚定之后还剩 3.4323 MON。
   *EN: The explorer links are the evidence — transfer `0x4b66b46f…ae11`,
   block 78228932, 1.5 MON, fee 0.002415 MON, sender 5 → 3.497585; anchor
   `0xd035cdda…fc433f`, contract `0x0D903C…ABA1` — all public; the wallet
   holds 3.4323 MON after transfer, deploy and anchor.*

4. **「为什么非得是 Monad？别的链不行吗？」**
   → 纪元结算完马上开下一局，结算必须快 finalized 才跟得上循环——Monad
   的快区块和并行执行给的就是这个快终结；而且锚定只是一次便宜的写入，
   世界本身一直在链下可重跑。
   *EN: Each epoch settles and the next starts right away, so settlement has
   to finalise fast — Monad's fast blocks and parallel execution give the
   loop that pace, and the anchor is one cheap write while the world stays
   reproducible off-chain.*

5. **「前端里那个世界是真的在算，还是写死的？」**
   → 真的在算：浏览器里跑的是同一套引擎的移植版，纪元 API（`runEpoch`、
   `deriveWinner`、`settleEpoch`）和 Python 逐位一致——`node
   frontend/verify_epochs.mjs` 3/3 黄金纪元通过，赢家和赔付一模一样；而且
   `python main.py play` / `python main.py epoch` 用同样的参数在终端跑，
   摘要必须一模一样——两个实现互相验证。
   *EN: It really computes: the browser runs a port of the same engine — the
   epoch API (`runEpoch`, `deriveWinner`, `settleEpoch`) matches Python
   bit-for-bit: `node frontend/verify_epochs.mjs` passes 3/3 golden epochs
   with identical winners and payouts; and `python main.py play` /
   `python main.py epoch` with the same parameters must print the same
   digest. Two implementations check each other.*

---

## 演示者检查清单（上台前 10 分钟）

- [ ] `python main.py epoch --bet you:2:100` 本地能跑，赢家 Cinder（5,144,627 分），纪元摘要 `b25c8fb3e94f746b…`
- [ ] `node frontend/verify_epochs.mjs` 3/3 通过；`python -m pytest` 通过（614 个测试）
- [ ] 加演试过：`--seed 43` → Boreas 赢；`--max-orders 2` → 四个文明全死，平局裁定 Dune 赢
- [ ] 游乐场里试过：种子 42 → 摘要 `8ed4e8d7dd86fafc`；税率 10% → 基尼系数 0.054；下单数 2 → 世界死亡；都恢复默认
- [ ] 浏览器标签页 ①：前端游乐场已打开 ②：转账交易链接已打开 ③：锚定交易链接已打开（不要现场输入哈希）
- [ ] 终端里 `cast call 0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1 "getDigest(uint256)(bytes32)" 100 --rpc-url https://testnet-rpc.monad.xyz` 能返回 `0x8ed4e8d7dd86fafc…`
- [ ] 备用：`reports/first-monad-transfer.json` 能在终端 `cat` 出来；`python main.py epoch --real-testnet` 能打出链上事实
- [ ] 记住一句话：文明三分钟兴衰——押注幸存者；每个纪元都以一个任何人都能重算的哈希收尾；记住定位：不是 GameFi，没有代币，没有投机
