---
feature: web-hardening
status: delivered
updated: 2026-10-23
branch: main
commits: 未提交（本地变更）
---

# 查询站 Web 层加固：可验证、可分享、移动端可用、资源瘦身

## Report

**What was built** — 四组改动，全部围绕 `web/`（无构建步骤的静态站）与其验证链路：

1. **Web 测试重新可信**：`tools/_smoke_web.js` 的期望值改为从 `data/` 现算（补丁数、词条数、英雄卡数、年份数、分类 chip 集合），不再硬编码 343/904/18；`jump-bar` 的 chip 容器按 `#cat-chips` id 取用而非 `children[4]` 索引；`ci.yml` 新增 `web` job 运行该测试（此前 CI 只跑 pytest，唯一的前端回归测试从未执行、且在 main 上已是红的）。
2. **页面健壮性与可分享状态**：`<body data-page="…">` 统一启动 + `runPage()` 统一捕获（索引页/补丁页此前会 unhandled rejection 白屏）；筛选与搜索状态用 `replaceState` 写入 URL（`?cat=` / `?q=` / `?dim=`）；跳转条的年/月选项随当前可见补丁重建（筛选后不再出现"跳转到不存在的区块"）；空筛选结果有空状态 + "清空筛选"；列表上方显示"共 N 条补丁"；补丁页先构建语言切换器与官方链接再取档（一侧缺档时不再卡住）；每页设置 `document.title` / `description` / 内联 SVG favicon（消除 `/favicon.ico` 404）；英文视图切换 `<html lang="en">`；英雄时间线的补丁标题改为站内链接（与词条页一致）；新增「按英雄浏览」区块（55 位英雄，按角色分组，复用此前无任何前端消费者的 `heroes_index.json`）；词条搜索加 120ms 防抖、精确/前缀优先排序、命中高亮、卡片加英雄头像；移动端把 17 个分类 chip 收成单行横向滚动 + `--sticky-h` 动态锚点偏移（宽屏仍换行）。
3. **安全加固**：`esc()` 改为纯字符串映射并转义引号（原 DOM 往返实现只转义 `& < >`，却被用于 `title`/`alt`/`src` 属性）；`media()` 收紧为 https-only 并给外链图片加 `referrerpolicy`；移除全部内联 `onerror`，改为一处捕获级 error 监听；5 个页面加 CSP meta；`tools/serve.py` 的 `import os` 移回模块顶部。
4. **资源瘦身**：新增 `tools/optimize_assets.py`（离线、幂等）；英雄头像 256×256/127KB → 96×96 调色板 PNG（12.5MB → 0.5MB）；地图截图（实为 JPEG 字节的 `.png`）2560 宽 → 1024 宽 progressive JPEG（76.6MB → 15.9MB）；删除未被任何代码引用的 `web/assets/heroes/` 重复树（12.2MB，其中 `doctrine.png`/`hero-d205583e.png` 两个缺失头像先并入 `icons/heroes/`）；`download_icons.py` 现在同时维护 `web/assets/icons/index.json`（可用头像清单），前端据此跳过不存在的头像，`pages.yml` 只把站点真正读取的 `data/*.json` + `patches/` + `heroes/` 复制进产物。`web/` 总体积 105.4MB → 24MB，部署产物 121MB → 38MB。

**Verification** —
- `node tools/_smoke_web.js` → **ALL WEB ASSERTIONS OK**（并新增 12 条断言：URL 回写、空状态、英雄浏览 55 卡、卡片头像、英雄页补丁链接、raw_text 兜底转义/图标）
- `python -m pytest -q` → **300 passed**
- `npx -p playwright node tools/_layout_check.js` → **12/12 PASS**
- 一次性 Playwright 脚本（未提交，覆盖 5 个页面）：**0 CSP 违规、0 console error、0 4xx**；筛选点击 → `?cat=` 生效、跳转条年份 11→3、跳转目标存在；375px 吸顶条 89px、锚点偏移 101px ≥ 条高；词条搜索 `?q=` 生效、结果收窄、`<mark>` 高亮、「按英雄浏览」在搜索时隐藏；英雄页补丁链接；英文补丁页 `lang=en` 且标题含日期、无裂图。同一脚本对**按新 `pages.yml` 规则暂存的 `_site`** 复跑，结果一致。
- `python tools/optimize_assets.py` 连跑两遍 → 第二次 "0 rewritten"（字节收敛）；抽查 96px 头像与 1024 宽地图清晰度可接受。

**Journey log** —
① 地图 `.png` 里装的是 **JPEG 字节**（`download_icons.py` 的 `_ext_for` 一直如此，浏览器按内容嗅探）。第一版脚本把它们当 PNG 重编码：1024 宽真彩 PNG 反而 1.4MB/张（原图 278KB），地图总量 76.6MB → 更大，脚本的 budget 校验以非零退出兜住了。改为 JPEG 重编码（同一文件名/扩展名）后 15.9MB。
② 英雄头像原本 256×256/**127KB**（PNG 调色板已优化过，但分辨率过剩），96×96 + 128 色 → 5–6KB，视觉无损（显示尺寸 22–36px）。
③ `web/assets/heroes/` 是 `web/assets/icons/heroes/` 的 98 文件副本（多出的恰是 `doctrine`、`hero-d205583e` 两个头像），代码零引用 —— 与之前清理掉的 `web/maps/` 同类残留。
④ 词条卡头像一上线就产生 2 个 404（`doctrine`、`hero-d205583e` 无头像文件），单靠 `onerror` 隐藏只是遮丑：改为由 `download_icons.py` 产出 `icons/index.json` 清单，前端只请求存在的头像。
⑤ `_smoke_web.js` 的 DOM shim 只认识"注册表"里的 id，新代码用 `#cat-chips` 取节点时拿到了空壳；在 `appendChild` 时把带 id 的节点登记进注册表后，shim 与真实 DOM 行为一致（同时让 `syncChips` 首次真正作用到 chip 上）。
⑥ CSP 上线前必须先去掉内联 `onerror` 与内联 `<script>initXxx()</script>`，否则 `script-src 'self'` 会直接拦掉页面初始化。
⑦ 宽屏下 17 个 chip 单行横向滚动会把最后一个 chip 切一半 —— 用 `min-width: 1000px` 的媒体查询恢复换行，窄屏保持单行滚动。

## [S1] Problem

`web/` 是一个 1313 行 `app.js` + 5 个 HTML 的零构建静态站，功能已完整，但有四类缺陷：

1. **验证链路失效**：唯一的 Web 回归测试 `tools/_smoke_web.js` 把数据规模写死（343 补丁 / 904 词条 / 18 英雄卡），当前数据是 349 / 949 / 19 —— 在 main 上 `exit 1`；且没有任何 workflow 执行它（`ci.yml` 只跑 pytest）。
2. **健壮性/可分享性**：`initIndex`/`initPatch` 的 fetch 未捕获异常（白屏 + unhandled rejection）；筛选与搜索状态不进 URL（分享/后退失效）；`buildJumpBar` 只在初始化时按全量数据构建（筛选后跳转目标可能不存在）；空筛选结果无提示；补丁一侧缺档时语言切换器尚未构建（无法切换）；所有页面共用静态 `<title>`；英文视图 `<html lang>` 仍为中文；英雄时间线的补丁标题不可点；`heroes_index.json` 在前端零使用（英雄轨迹页几乎无入口）；移动端 17 个 chip 使吸顶条高达 150–220px，而 `scroll-margin-top` 写死 110px。
3. **加固缺口**：`esc()` 依赖 DOM 往返、不转义引号却用于属性值；`media()` 注释称 https-only 实则放行 `http:`；内联 `onerror` 与内联初始化脚本使 CSP 无法启用；`serve.py` 的 `os` 仅在 `__main__` 分支导入。
4. **资源体积**：`web/` 105.4MB —— 地图 73MB（2560×1440，显示约 470px）、英雄头像 11.9MB（256×256/127KB，显示 22–36px）、另有一棵未被引用的 12.2MB `web/assets/heroes/` 重复树；`pages.yml` 还把 `data/archive/` 等站点从不读取的文件打进产物。

## [S2] Design

### D1 前端（`web/app.js`、`web/style.css`、5 个 HTML）

- **启动**：HTML 去掉内联 `initXxx()`，改 `<body data-page="…">`；`app.js` 末尾 `PAGE_INIT` 表 + `runPage(fn).catch(mountLoadError)` 渲染失败原因与"重试"按钮。`installImageFallback()` 用一个捕获级 `error` 监听替代所有内联 `onerror`。
- **状态**：`syncURLState(values)` 用 `history.replaceState` 回写（shim 环境回退到 `location.search`）；`toggleCat`/`setFilter`/词条 `render()` 调用之。`initIndex`/`initEntries` 从 `?cat=`/`?q=`/`?dim=` 还原。
- **跳转条**：`buildJumpBar()` 只建壳，`fillJumpBar(years)`/`fillJumpMonths()` 在每次 `renderTimeBrowser` 按可见集合重填（保留用户已选年/月）。
- **补丁页**：`patchFileFor()` 用正则解析 `{site}-YYYY-MM-DD-N`（替代位置切分，非法 id 显式报错）；语言切换器/官方链接在取档前构建；缺档分支仍保留切换能力。
- **元信息/无障碍**：`setPageMeta(title, desc)`；`documentElement.lang` 随视图；chip `aria-pressed`、`aria-live` 计数、`sr-only` 搜索标签、`focus-visible` 描边、`prefers-reduced-motion`。
- **导航**：抽出 `buildPatchLinkMap()`（词条页与英雄页共用）；`initHero` 传入 `patchHref`；`initEntries` 新增 `buildHeroBrowse()`（按角色分组的 55 张英雄卡，复用 `.hero-grid`/`.hero-card`/`.role-title` 三条原本无引用的 CSS）。
- **搜索**：`entryHaystack()` 预计算、`searchRank()` 排序、`highlight()` 高亮、120ms 防抖（首帧仍同步）。
- **移动端**：`.jump-bar .chips` 单行横向滚动（≥1000px 恢复换行）；`trackStickyHeight()` 用 `ResizeObserver` 写 `--sticky-h`，`[id^="year-"] { scroll-margin-top: calc(var(--sticky-h,110px) + 12px) }`。

### D2 加固（`web/app.js`、5 个 HTML、`tools/serve.py`）

`esc()` 改为 `/[&<>"']/` 映射（属性安全、无 DOM 分配）；`media()` 仅 `https:` + `referrerpolicy="no-referrer"`；5 页加 `Content-Security-Policy` meta（`default-src 'self'; img-src 'self' https: data:; style-src 'self'; script-src 'self'; …`）；`serve.py` 的 `import os` 移到顶部。

### D3 资源（`tools/optimize_assets.py`、`tools/download_icons.py`、`web/assets/**`、`pages.yml`）

- `optimize_assets.py`：英雄头像 → 96×96/128 色 PNG；地图 → 1024 宽/quality 72 progressive JPEG（沿用同名 `.png` 约定）；按文件字节 budget 跳过已完成项（幂等）；超预算以非零退出。Pillow 作为可选依赖 `[project.optional-dependencies].assets`，仅离线使用。
- `download_icons.py`：新增 `write_icon_index()` 产出 `web/assets/icons/index.json`（存在的英雄头像清单）；`app.js` 的 `heroAvatar()` 据此跳过缺失头像。
- 删除 `web/assets/heroes/`（重复树），先把其中独有的 `doctrine.png`、`hero-d205583e.png` 并入 `icons/heroes/` 并优化。
- `pages.yml`：只复制 `web/*`、`data/*.json`、`data/patches`、`data/heroes`。

### D4 测试（`tools/_smoke_web.js`、`.github/workflows/ci.yml`）

`EXPECT` 由 `patches_index.json`/`entries_index.json`/`heroes_index.json` 现算；chip 断言改为集合比较（数据里出现的分类必须都有 chip —— 前后端标签契约）；新增断言：URL 回写、空状态、英雄浏览 55 卡、卡片头像、英雄页补丁链接、`raw_text` 兜底（图标注入 + 转义）；`ci.yml` 增 `web` job（`setup-node` + `node tools/_smoke_web.js`，无需浏览器）。

## [S3] Out of Scope

- 不改数据契约（`schema_version` 仍为 1）："最后抓取"改为"数据截至（最新补丁日期）"的**文案**修正，不给索引加 `generated_at`。
- 不引入构建链/框架（保持零构建、Pages 直出）；不把多页站改成单页应用。
- 不做暗/亮主题切换、不做搜索拼音/模糊匹配、不做站内全文检索。
- 不合并 `owpatch-tool` 侧同源 UI；不为 `entryKey`/分类标签增加更多 Python 对偶测试（`test_entries.py` 已有入口）。
- 地图不改成 WebP（保持既有 `.png` 文件名约定，避免动前端路径与下载脚本的扩展名逻辑）。

## Tasks

- [x] T1: `_smoke_web.js` 期望值改为数据推导 + shim 支持 id 解析 + `ci.yml` 增 web job — acceptance: 数据增删后测试仍绿；CI 可见 (covers: D4)
- [x] T2: 启动/错误兜底、URL 状态、跳转条重建、空状态与计数、补丁页先建壳、标题/描述/lang/a11y、英雄页链接、按英雄浏览、搜索排序高亮防抖、移动端吸顶条 — acceptance: smoke 新增断言全绿 + 真机 375px 抽查 (covers: D1)
- [x] T3: `esc()` 属性安全、`media()` https-only、捕获级图片兜底、CSP meta、`serve.py` 导入 — acceptance: 5 页 0 CSP 违规 / 0 console error (covers: D2)
- [x] T4: `optimize_assets.py` + 头像清单 + 删除重复树 + `pages.yml` 精简 — acceptance: 幂等；`web/` ≤ 25MB；暂存产物 5 页 0 4xx (covers: D3)
- [x] T5: 全量验证 — acceptance: smoke / pytest(300) / layout(12) / 真机脚本 全绿 (covers: D1-D4)
