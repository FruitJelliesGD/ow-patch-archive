---
feature: icon-path-and-doctrine-mapping
status: delivered
updated: 2026-10-23
branch: main
commits: 未提交（本地变更）
---

# 图标写入目录修复 + 血律/Doctrine 名称映射

## Report

**What was built** — 三处修复，回答"为什么 patch.html 上 Doctrine（血律）的技能没有图标"：

1. **图标目录错位（根因）**：三个监控工作流调用 `download_icons.py` 时传了 `--out web/assets`，
   而该工具把头像/技能图标写进 `out_dir/heroes`、`out_dir/abilities`，站点读取的却是
   `assets/icons/{heroes,abilities}`。于是迁移提交（`8a738c4`）之后新下载的图标全部落到
   `web/assets/{heroes,abilities}`，页面 404 后被错误监听器隐藏 —— 表现为"没有图标"。
   修复：三个工作流改为 `--out web/assets/icons`（地图仍经 `out_dir.parent` 落到 `web/assets/maps`），
   新增 `test_workflows_download_icons_into_the_site_tree` 契约测试防止回归；工作流下载后追加
   `optimize_assets.py` 步骤，使新英雄头像按显示尺寸（96px）落盘。
2. **把错位的历史图标搬回正确目录**：按 `data/patches/**` 的 633 条图标引用逐一核对，
   从 `web/assets/abilities/**` 迁移 18 个站点仍引用但 `icons/` 缺失的文件（含 Doctrine 的
   `eternal-scepter`/`invigorating-drones`/`shrouded-momentum`/`deliverance`、Sombra 的
   `cyberspace`/`hotfix`/`conspirator`、D.Mon 的 `power-barrier` 等），删除整个 539 文件的
   重复树（`web/` 24MB → 20MB），重建 `web/assets/icons/index.json` 清单。复核：633 条引用
   全部存在，0 缺失。
3. **血律与 Doctrine 是同一个英雄**：EN 站 2026-10-06/10-13 的新英雄 "Doctrine" 与 CN 站
   2026-10-07 的「血律」没有映射，CN 侧被自动 slug 成 `hero-d205583e`，能力也是哈希 slug
   （`hero-6db24cbe` 等）。`data/names.json` 补入 `Doctrine → 血律`（support）以及
   `Invigorating Drones → 焕生无人机`、`Shrouded Momentum → 迅影疾行`、`Deliverance → 救赎恩典`，
   重新生成后两个英雄合并为一个（20 条记录 / 11 条合并后更改）、能力落到英文 slug 并对齐图标。
4. **补丁页名称跟随内容语言**：此前 `heroBlock` 一律 `name_cn || name_en`，导致英文补丁页显示
   中文英雄名（例如 lang=en 页上显示「黑影」）。新增 `patchLang`/`patchName`/`patchRoleLabel`，
   英文页显示 Doctrine / Sombra / Tank，中文页显示 血律 / 黑影 / 重装（TOC 同步）。

**Verification** —
- `python -m pytest -q` → **307 passed**（+2：血律→doctrine 与三个能力名解析；工作流 `--out` 契约）
- `node tools/_smoke_web.js` → **ALL WEB ASSERTIONS OK**（期望值全部数据推导，英雄 55→54、词条 949→943 自动跟随）
- 真实浏览器（本地 serve）：
  - `patch.html?id=en-2026-10-13-1&lang=en` → 英雄 **Doctrine**，`eternal-scepter`/`invigorating-drones` 图标 `naturalWidth > 0`
  - `patch.html?id=p-2026-10-06-1&lang=en` → Doctrine + Transfusion/Invigorating Drones/Shrouded Momentum/Deliverance 四个技能图标全部加载
  - `patch.html?id=p-2026-10-06-1&lang=cn` → **血律** + 活力传输/焕生无人机/迅影疾行/救赎恩典 四个图标全部加载
  - 全程 0 个 4xx
- `tools/rebuild.py` 幂等（连跑两遍无差异）；`optimize_assets.py` 复跑 0 rewritten；`web/` 20MB

**Journey log** —
① 页面"没有图标"的直接原因是 404 被隐藏，但 404 的根源不在前端：图标的**写入目录**和**读取目录**
  分叉了。先按 `data/` 的图标引用做全量对账（633 条），才能区分"没下载"、"下错地方"和"引用路径错"。
② 血律问题暴露出名称映射缺口：`slugify("血律")` 必然产出哈希 slug，只有把 CN 名补进 `names.json`
  才能让两站合并；能力名同理，否则同一技能会以哈希 slug 各建一条历史。
③ 补丁页一直是"中文名优先"，英文页显示中文名属于长期存在但没人报的 i18n 缺陷；顺手按 `lang`
  切换名称，也避免合并后英文页显示「血律」。

## [S1] Problem

`https://…/patch.html?id=en-2026-10-13-1&lang=en` 上 Doctrine（中文名「血律」）的头像正常、技能没有图标：

- 页面请求 `assets/icons/abilities/doctrine/eternal-scepter.png` 等 → 404 → 被捕获级 error 监听器
  `display:none`，表现为"无图标"；
- 文件其实存在，只是被 CI 写进了 `web/assets/abilities/doctrine/…`（老目录），站点从不读取；
- 同一个英雄在 EN/CN 两站是两条记录（`doctrine` 与 `hero-d205583e`），CN 侧能力名为哈希 slug；
- 英文补丁页显示中文英雄名。

## [S2] Design

- **工作流**：`--out web/assets` → `--out web/assets/icons`（monitor / monitor-fast / backfill）；
  下载后追加 `pip install pillow --quiet || true && python tools/optimize_assets.py || true`。
- **资产迁移**：一次性脚本按 `data/patches/**` 的图标引用，把 `icons/` 缺失而老目录存在的文件复制过去，
  再 `git rm -r web/assets/abilities`；删除孤儿 `icons/heroes/hero-d205583e.png`；`write_icon_index()` 重建清单。
- **名称映射**（`data/names.json`）：`Doctrine`/`血律` + 3 个能力名，`tools/rebuild.py` 重富化。
- **前端**（`web/app.js`）：`patchLang` 由 `initPatch` 的 `active` 决定，`patchName()` 选择该侧名称，
  `patchRoleLabel()` 选择角色文案，用于英雄块、能力、威能、Stadium 物品与 TOC。
- **测试**：`test_names.py` 覆盖血律/能力映射；`test_download_icons.py` 覆盖工作流 `--out` 契约。

## [S3] Out of Scope

- 让工作流下载地图截图（`--include-maps`）：新地图差异图仍不会自动补，属于另一件事。
- 清理 `web/assets/icons/abilities` 里已无引用的孤儿图标（6 个，不影响请求）。
- 补丁正文（description/dev/general）不做中英选择：它们本来就是单语内容。

## Tasks

- [x] T1: 工作流 `--out` 修复 + 契约测试 + 下载后优化步骤 —— acceptance: 测试通过；图标落到 `assets/icons`
- [x] T2: 迁移 18 个图标、删除重复树、重建清单 —— acceptance: 633 条引用 0 缺失；`web/` ≤ 20MB
- [x] T3: `names.json` 补充映射并重建 —— acceptance: 血律→doctrine、能力 slug 对齐、英雄数 55→54
- [x] T4: 补丁页名称随 `lang` 切换 —— acceptance: EN 页 Doctrine / CN 页 血律；0 个 4xx
- [x] T5: 全量验证（pytest 307 / smoke / 浏览器 4 页 / rebuild 幂等）+ README/本 spec
