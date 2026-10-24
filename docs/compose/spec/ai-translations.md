---
feature: ai-translations
status: delivered
updated: 2026-10-23
---

# AI翻译目录与站点入口

## Report

**What was built** — 在归档仓库新增与官方数据完全隔离的 `data/ai_translations/`，覆盖所有缺少官方中文的补丁（288 篇，含公告/PTR/愚人节等特殊模式）。站点补丁页在官方「英文站/中文站」之外增加「AI翻译」标签（`?lang=ai`），页头显示机器翻译声明；时间浏览列表对应条目显示「AI翻译」徽章。译文以结构化 JSON 存储，直接复用现有补丁详情渲染器（章节卡片、英雄头像、技能图标、开发者注、嵌套列表、目录侧栏）。批量补齐由 `tools/ai_translate.py` 完成（见 `ai-translate-tool.md`）。

数据层：`data/ai_translations/index.json` 以 `source_patch_id` 关联官方 `patches_index`；补丁 JSON 使用 `site: "ai"`、`id: "ai-<date>-<seq>"`、`source_patch_id`、`translation.source_hash`，`text_en` 全部置空、`text_cn` 为中文，数字提取字段/`slug`/`name_en`/`role`/`icon` 与源逐字段一致。官方 `patches_index`、`entries_index`、`heroes`、`pairing`、`manifest` 均不感知 AI 数据。

前端：`web/app.js` 新增 `loadAiIndex` / `aiFor` / `aiBadge`，`initPatch` 支持 `lang=ai` 并在无译文时回退官方语言；`web/patch.html` 增加 `#patch-ai-note`；`web/style.css` 增加紫色 AI 徽章/标签样式；`pages.yml` 把 `data/ai_translations` 一并部署到 `_site/data/`。

**Verification** —
- `pytest -q` → **323 passed**（新增工具/译文契约测试）
- `node tools/_smoke_web.js` → ALL WEB ASSERTIONS OK（新增 `aiLangButtons=2`、`aiTitle`、`aiBodyChinese`、`aiNoticeVisible`、`aiSiteBadge`、`indexAiBadge`）
- 本地 `tools/serve.py` + HTTP 检查：AI 页面与 4 个 JSON 均 200；官方 `patches_index.json` 未变
- `git status`：仅新增 `data/ai_translations/`、`tests/test_ai_translations.py`、本 spec；修改 `web/app.js`、`web/patch.html`、`web/index.html`、`web/style.css`、`tools/_smoke_web.js`、`pages.yml`、`README.md`

## [S1] Problem

英文站归档从 2016-05 开始，但官方中文站 2016 年没有对应页面，`patch_pairs.json` 中 2016 条目全部未配对。读者在补丁详情页只能看英文；直接把机器译文塞进 `data/patches/cn` 会污染官方数据、配对、英雄时间线与词条检索，也无法区分「官方中文」和「AI翻译」。

## [S2] Design

### D1 数据目录与契约

```text
data/ai_translations/
├── README.md
├── index.json
└── zh/2016/<date>-1.json
```

`index.json`（`schema_version: 1`）字段：`source_patch_id`、`ai_patch_id`、`date`、`title`、`file`、`status`。补丁 JSON 镜像 `data/patches` schema，额外带 `source_patch_id` 与 `translation`（skill/engine/generated_at/status/source_hash/kept_english）。

### D2 翻译约束

- 只翻译 `title`、section `title/description/dev`、hero `dev_note/general`、ability `name_cn`、change `text_cn`、block `title/body/dev`、map 展示字段；`text_en` 置 `null`。
- 保留全部数字、百分比、版本号、列表符号/缩进/空行、`**加粗**`；单位译 秒/米/发/秒。
- 标题日期取源 JSON `date`（归档日期），不取英文标题日期（09-02 英文标题写 September 1）。
- 开发者注不加「开发者注：」前缀（站点用 `dev-note` 样式）。
- 术语以 v7.6 为准；未收录专名保留英文并登记 `kept_english`；不写 `[待补充]`/译注。
- 2016 补充决策：`Skill Rating`→竞技等级、`Sudden Death`→绝杀局、`Time Bank`→时间池、`Top 500`→500强、`Golden Weapons`→黄金武器、`Loot Box`→补给箱、`Play of the Game`→全场最佳、`BattleTag`→战网昵称、`Shield Generator`→护盾发生器、`Photon Shield`→光子护盾、`Winter Wonderland`→雪国仙境、段位→青铜/白银/黄金/白金/钻石/大师/宗师；`Boop` 保留英文。
- 源文笔误（`Botsare`、`wasn"t`、`ProjectedBarrier`）保留 `name_en`/`slug`，展示文本按语义翻译。

### D3 站点接入

- `lang=ai` 作为第三种补丁视图；URL 仍用官方源 `id`（`patch.html?id=en-2016-06-14-1&lang=ai`），避免与 `p-…` 合并 id 冲突。
- 语言按钮仅在存在 AI 条目时追加；`AI翻译` 徽章 + 页头 `#patch-ai-note` 声明。
- 列表页只加被动徽章，不新增筛选维度、不改变 `indexPatches` 计数、不新增列表行。
- `loadAiIndex` 失败时静默降级，官方页面行为不变。

### D4 官方隔离

`src/ow2_patch/pipeline.py` 的 `regenerate_all` 只遍历 `patches/en`、`patches/cn`；AI 数据在 `data/ai_translations`，不进入 `patches_index`、`entries_index`、`heroes`、`ability_map`、`patch_pairs`、`manifest`、`changelog`。`test_ai_translations.py` 断言官方索引与英雄时间线无 `ai-` 记录。

## 任务与验收

- [x] 288 篇 AI JSON + `index.json` + 目录 README
- [x] 站点 `lang=ai` 标签、徽章、免责声明
- [x] 列表页 AI 徽章
- [x] `pytest` 契约测试与 smoke 回归
- [x] `pages.yml` 部署 AI 目录
- [x] README / spec 文档
- [x] 本地 serve + HTTP 检查
- [ ] 人工复核 288 篇译文质量（当前 `status: draft`）
- [ ] 扩展到 2016 其余 17 篇（本次不做）

## Journey log

① 2016 老补丁的标题日期与归档日期不一致（09-02 标题 September 1、05-27 标题 May 26 等），标题统一取归档 `date`，否则列表/详情日期会打架。
② 09-02 的「竞技比赛」block 有 46 行嵌套列表（2/4 空格缩进、连续空行），逐行翻译并保持结构；校验用 `- ` 行数与缩进宽度，而不是字符长度。
③ 源文有 `Botsare`、`wasn"t`、`ProjectedBarrier` 等笔误/粘连；`name_en`/`slug` 不能改（图标和数据键依赖），只按语义译展示文本。
④ 术语表把 `Dragonstrike` 收作「竜」、`Opportunist` 收作「相时而动」，与直觉译法不同；遵循表值，不在此特例改表。
⑤ `.5`/`.25` 在源文里省略前导零，译文写成 `0.5`/`0.25`；契约测试对数字 token 做前导零归一化，避免误报。
⑥ AI 数据不能放进 `data/patches/ai`：虽然 `regenerate_all` 只遍历 en/cn，但 `data/patches/*` 的语义是官方抓取数据；独立目录 + `pages.yml` 显式拷贝更清晰。
