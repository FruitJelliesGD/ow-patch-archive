---
feature: pairing-signature
status: delivered
updated: 2026-08-22
branch: feat/pairing-signature
commits: f872bc0..78296bd
---

# 配对算法结构签名修复（迭代十二）

## Report

**What was built** — 修复 EN/CN 配对算法"同日优先"权重导致的系统性错配，并防复发：配对候选边的权重增加**结构签名校验**——当选择基于同日/同标题日（`min(anchor_diff,title_diff)==0`）时，要求两侧签名一致（section 类型序列 + 按序 hero slug，patch JSON 已富化无需 resolver；尾部空 generic 节归一化、至少留 1 节），不一致的候选加 `SIG_PENALTY=100M`（> 最大日期权重 ~20M，**不拒绝边、最大基数不变**）；差日配对信任原日期权重（CN 侧可能整体缺 hero 节——Season 15 CN 页实证——严格签名只验证同日选择）。

修复实证（vs f872bc0 恰 **10 处** en 侧配对变化、55 对不变、CN 多重集字节一致）：**2026-08-19/20**（cn-8.20 改配 en-8.19 Client Update，en-8.20 Hotfix 独立 unpaired，等 CN 8.21 发布后自动正确配对）；**2025-07-09**（en-07-03↔cn-07-09，en-07-09 Juno 热修 unpaired——尾部空 generic 归一化修复）；**2025-04-22↔04-23**、**2025-05-14↔05-16**（Season 15 平衡热修）+ 5 月中旬连锁（en-05-16→cn-05-21 SF6、en-05-22→cn-05-23 bugfix）；**2025-02 恢复基线**（en-02-18↔cn-02-19 Season 15，en-02-20 热修 unpaired——全空节折叠回归经"仅同日验证"规则修复）。

**Verification** — `pytest -q` → 191 passed（+5：同日异内容/差 1 天同内容单测、最大基数兜底单测、尾部空 generic 归一化单测、真实数据不变量——6 目标配对 + Feb 基线断言）；`node tools/_smoke_web.js` → ALL WEB ASSERTIONS OK（重基线 indexPatches 343、entryCards 919）；rebuild 字节收敛；layout 12/12；配对 diff 复核恰 10 处且 fresh pairing 与提交数据字节一致。三轮独立审查：首轮 critical = 07-09 未修（尾部空节致严格签名不等）→ 归一化修复；复审 critical = Feb 回归（全空节折叠 `""==""` 误配，en-02-20 抢 cn-02-19）→ 改为仅同日选择验证（Feb 属"CN 缺 hero 节"，真配对有 hero，纯签名无法兼得 8.19/8.20 与 Feb 两场景）；第三轮 **0 critical**（6 目标全对、Feb 字节级恢复、残留风险低——同日正确配对本就日期权重胜出，惩罚只压制错误同日内容）。

**Journey log** — ① 配对错配根因 = 权重同日优先无内容信号，**系统性**（8.19/8.20 + 3 处 2025 均实证）；patch JSON 已富化 slug 可直接做结构签名。② 严格签名等式的两个陷阱：**尾部空 generic 节**（en-07-03 7 节 vs cn-07-09 6 节，解析 stub 差异）与**全空节折叠**（`while parts[-1]=="generic_update:"` 把全 generic 补丁折叠成 `""` 致 `""==""` 误配）——归一化必须"至少留 1 节"且只验证同日选择。③ **CN 缺 hero 节场景**（Season 15 CN 页无 hero_update，真配对 EN 有 hero）证明签名只能验证"同日偏好"，差日信任日期权重——纯签名无法同时正确 8.19/8.20 与 Feb 两场景，`min(anchor,title)==0` 门控是平衡点。④ GitHub Actions run 日志 API 需管理员权限（403），匿名只能查 runs/issues 列表；通知根因 = SMTP 静默失败 + GitHub 平台提醒设置（Issue 创建本身正常）。
## Report

## [S1] Problem

EN/CN 补丁配对发生**系统性错配**：配对权重"同日优先"（`min(anchor_diff,title_diff)*1000` 主导，无任何内容信号）在 EN 连续发补丁时，把滞后一天的 CN 补丁错配给同日的另一个补丁。实证：

- **2026-08-19/20**（线上 f872bc0）：`p-2026-08-20-1` = en-2026-08-20-1（Hotfix，Mizuki）+ cn-2026-08-20-1（实为 EN 8.19 Client Update 的翻译）；真配对 `en-2026-08-19-1` 被拆为 unpaired。
- **2025-05-16**：en-2025-05-16（SF6 内容补丁）配了 cn-2025-05-16（平衡热修）；真配对 en-2025-05-14（同英雄集）unpaired。
- **2025-04-23**：en-2025-04-23（bug 热修）配了 cn-2025-04-23（Season-16 启动）；真配对 en-2025-04-22 unpaired。
- **2025-07-09**：en-2025-07-09（Juno 热修）配了 cn-2025-07-09（7 英雄）；真配对 en-2025-07-03 unpaired。

另一问题（只告知、不改代码）：Issue 创建与数据流水线正常（#4/#5/#6 由 bot 创建、changelog 持续追加），失效在 SMTP 邮件静默失败与 GitHub 平台提醒设置。

## [S2] Design

### D1 结构签名权重（src/ow2_patch/pairing.py）

- `_patch_signature(patch_data) -> str`：`"|".join(f"{s.type}:{','.join(h.slug for h in s.heroes)}" for s in sections)`（按文档顺序；空英雄 section 记 `type:`）。patch JSON 在 pairing 前已富化（hero.slug 双语一致），签名无需 resolver。
- `pair_patches(en, cn, data_dir=None)`：提供 data_dir 时读全部 patch JSON 构建 `patch_id → signature` 缓存（397 文件一次读取）；候选边权重：`sig_ok = sig(en) == sig(cn)`；`weight = (0 if sig_ok else SIG_PENALTY) + 现有项`。`SIG_PENALTY = 100_000_000`（> 现有最大权重 ~20M）。
- 不变式：最大基数（匹配总数）不变（惩罚仅作候选偏好、不拒绝边）；既有正确配对（签名一致）不受影响；签名不一致的历史配对在无更好替代时仍保留。

### D2 数据修复

- 改 pairing 后 `tools/rebuild.py` 全量重建（pairing → patches_index → heroes → entries 全链路）。
- 配对 diff 校验：新旧 patch_pairs 对比，预期仅 8.19/8.20 + 3 处 2025 错配变化，其余 51 对不变。
- 推送 origin/main（monitor 后续运行用新算法保持一致）。

### D3 通知根因（不改代码）

- 邮件：SMTP best-effort 静默失败——自查仓库 Settings→Secrets（SMTP_HOST/PORT/USER/PASS/TO），QQ/163 授权码过期需更新；未配置则 run.py 打印 "SMTP_HOST not set; skipping email"。
- GitHub 提醒：repo Watch 状态、通知设置、邮箱验证。
- 验证路径：产生 f872bc0 的 Actions run（monitor-fast run#256，2026-08-21T19:03:46Z）→ "Run pipeline" 步骤日志看 `email sent to …` / `SMTP_HOST not set` / `WARN: email failed`。

## [S3] Out of Scope

- 通知代码改动（用户选择"忽略"，仅告知根因）。
- 签名容忍度（严格相等；解析差异致签名不一致的真配对靠最大基数兜底保留）。
- 配对稳定性优化（保留既有配对除非内容确认替换——签名权重已覆盖主要错配）。

## Tasks

- [x] T1: 特性文档 — acceptance: 本文档含设计与任务（covers: 全部）
- [x] T2: pairing `_patch_signature` + 签名权重 — acceptance: 构造场景（同日异内容/差 1 天同内容）签名选对；最大基数不变（covers: D1）
- [x] T3: 单测（签名单测 + 真实数据不变量：55 对配对、8.19/8.20 正确、2025 三错配修复）— acceptance: pytest 全过（covers: D1；depends: T2）
- [x] T4: rebuild 重建 + 配对 diff 校验 — acceptance: 新旧 patch_pairs 仅 8 处差异（8.19/8.20 + 3 处 2025 + 5 月中旬连锁）；p-2026-08-19-1=en-8.19+cn-8.20、en-2026-08-20-1 unpaired（covers: D2；depends: T3）
- [x] T5: 全量验证（pytest/smoke 重基线/rebuild 收敛）— acceptance: 全绿（covers: 全部；depends: T4）
- [x] T6: 独立 review + 规格定稿 — acceptance: review 无 critical、status: delivered（covers: 全部；depends: T5）
