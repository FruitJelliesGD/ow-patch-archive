---
feature: spa-navigation
status: delivered
updated: 2026-10-23
branch: main
commits: 未提交（本地变更）
---

# 查询站 SPA 导航：站内切换不刷新标签页

## Report

**What was built** — `web/` 从“每个链接都整页刷新”的多页站升级为 **History API + 视图壳热切换** 的 SPA 导航，同时保留 5 个 HTML 作为可直链、可刷新的渐进增强入口：

1. **路由与壳切换**：点击站内链接时 `pushState` 目标 `*.html?参数`，`fetch` 目标页 HTML（会话内缓存）、用 `DOMParser` 取出 `header/main/footer` 替换当前文档，再调用目标页原有 `init*()` 渲染。URL 仍是物理 `.html`，不需要服务端 rewrite / hash 路由。
2. **状态与历史**：URL、`document.title`、description、`<html lang>`、`body[data-page]`、`body class` 随视图同步；浏览器前进/后退直接重新渲染视图；滚动位置写入 `history.state`（`history.scrollRestoration = "manual"`），返回时恢复；补丁页中/英切换保留当前滚动位置。
3. **健壮性**：导航令牌 `navSeq` 丢弃过期导航；`waitForIdle()` 等待上一个视图初始化完成后再换壳，避免旧异步初始化写入新 DOM；`popstate` 在导航进行中也会启动真正的重渲染（不能把未更新的 `currentRouteKey` 误判为同页滚动）；换壳前统一执行 `onPageLeave` 清理（搜索防抖 timer、`ResizeObserver`、`IntersectionObserver`）。
4. **性能**：`fetchJSON` 增加会话级缓存（`entries_index.json` 0.42 MB、`patches_index.json` 0.2 MB 不再每次切换重下）；HTML 壳同样按页缓存。
5. **降级**：只有 http(s) + `fetch` + `DOMParser` + History API 都可用时才安装路由；否则完全维持原多页跳转。壳加载/解析失败时回退整页 `location.assign`（popstate 失败则 `reload`）。

**Verification** —
- `node tools/_smoke_web.js` → **ALL WEB ASSERTIONS OK**（新增 SPA 纯函数断言：路径→页面映射、站内/跨源/hash/非页面文件判定、仅语言切换判定、被取代视图不得回写 URL；原有渲染/检索/分页断言不变）。
- `python -m pytest -q` → **307 passed**（本特性无 Python 改动）。
- `npx --yes -p playwright@1.61.0 node tools/_spa_check.js` → **ALL SPA ASSERTIONS OK**：
  - 首页→词条检索、词条检索→词条详情→返回、检索→英雄轨迹→返回、首页→补丁详情→语言切换→返回，全程 `window.__spaMarker` 存活、`load` 事件 0 次；
  - URL / 标题 / topnav active / `html lang` 正确；
  - 浏览器 `back()` / `forward()` 重新渲染且不刷新；返回词条列表时滚动位置 600 → 600；延迟 `data/heroes/ana.json`
    400ms 让 `history.back()` 落在 `initEntry` 未完成时，仍能正确回到词条列表（覆盖 pending-init 竞态）；
  - 补丁页 TOC `#sec-0` 锚点保持原生滚动、不触发重渲染；补丁页返回首页后 `<html lang>` 复位为 `zh-CN`；
  - 语言切换 600 → 600；新增深链 `entry.html?...` 正常直接渲染；
  - console error / pageerror / CSP 违规 **0**。
- `npx --yes -p playwright@1.61.0 node tools/_layout_check.js` → **12/12 PASS**（补丁页布局无回归）。

**Journey log** —
① 最初只根据 `currentRouteKey` 判断 popstate 是否同页。实测发现：点击卡片后 `applyShell` 已把 `body[data-page]` 换成 `entry`，但 `currentRouteKey` 要等 `initEntry` 结束才更新；此时立即 `history.back()` 会把“回到上一页”误判为同页滚动，导致地址栏回到 `entries.html` 而内容仍停在词条详情。修复：`navPending` 期间一律走真正的 pop 重渲染，并让新导航的令牌使在途 push 的后续写入失效。
② Playwright 的 `locator.click()` 会先把目标滚入视口，直接用于“语言切换保留滚动位置”会把 600px 位置变成按钮附近的 0；该断言改为页面内 `element.click()`，避免测试工具改变被测状态。
③ 滚动恢复需要在 `requestAnimationFrame` 中执行并带 `navSeq` 守卫，否则连续点击时旧导航的恢复滚动会作用到新视图。

## [S1] Problem

`web/` 的 5 个页面（index/entries/entry/hero/patch）各自是完整 HTML，站内所有链接都是普通 `<a href="*.html?...">`：

- 每次在「按时间浏览」与「词条检索」之间切换、点开补丁/词条/英雄详情、返回列表或切换中英文，都会整页刷新：重新下载 CSS/JS/索引 JSON、重建页面、丢失滚动位置与瞬时的筛选上下文。
- 用户明确要求 SPA 模式：切换显示时刷新标签页不可接受。
- 站点仍需保持零构建、GitHub Pages 直出、可直链/可刷新/可收藏，且不能放宽现有 CSP。
- 本特性解除了 `web-hardening.md` 中「不把多页站改成单页应用」的历史限制，但保留其“零构建、多入口、渐进增强”的约束。

## [S2] Design

### D1 路由与视图壳（`web/app.js`）

- `PAGE_FILE` 映射五个页面；`pageFromPathname()` 把 `/`、`index.html`、`entries.html` 等映射为路由键，未知路径不拦截。
- `spaTarget(href, base, origin)` 只接受同源五个 `.html`；跨源、`#hash`、`mailto:`、JSON 等返回 null。
- `loadShell(page)`：取 HTML → `DOMParser` → 提取 title/description/lang/body class/header/main/footer，按页缓存；失败不缓存。
- `applyShell(shell)`：替换三块壳并同步 `document.title`、description、`html lang`、`body.className`、`body.dataset.page`。
- 点击代理：左键、无修饰键、非 `_blank`/`download`；同页 hash 放行原生；同页无 hash 只阻止刷新并回顶部；其余 `preventDefault` 后 `runNavigation(page, {historyMode:"push"})`。

### D2 导航串行化、历史与滚动

- `activeRender` 保存当前视图初始化 Promise，`waitForIdle()` 循环等待其稳定；新导航先等旧视图完成再换壳，避免旧 `init*` 把数据写进新壳。
- `navSeq` 作为导航令牌：壳加载/初始化完成后若已过期则丢弃；`popstate` 触发的重渲染同样参与令牌竞争。
- `runNavigation` 在 `push` 前用 `saveScrollState()` 记录当前页 `scrollY`，再 `pushState({spa:true, scrollY})`；`pop` 从 `history.state.scrollY` 恢复。滚动事件用 150ms 防抖把实时位置合入当前历史项；安装路由时设 `history.scrollRestoration = "manual"`。
- `popstate` 判断：仅当 `!navPending && pathname+search === currentRouteKey` 时才视为同页（hash/滚动恢复）；否则重新渲染目标视图。
- `syncURLState` 在 `body[data-page]` 与 URL 页面不一致时跳过写入：被 back/forward 取代的 entries 初始化不得把 `?q=` 写到新页面。
- 滚动恢复在 `requestAnimationFrame` 中执行，并再次检查 `navSeq`，防止旧导航覆盖新视图。

### D3 生命周期、状态与性能

- `onPageLeave(fn)` / `cleanupPage()`：换壳前清理旧页面的防抖 timer、`ResizeObserver`、`IntersectionObserver`。
- `initIndex` 每次进入重置 `filter.selected`、`allPatches`、`jumpState`；`initEntries` 重置 `entryDocs`/`entryFiltered`，再从 URL 还原 `q/dim`。
- `fetchJSON` 增加 `Map` 缓存（失败删除），避免 SPA 切换重复下载索引。
- 焦点：换壳后给 `main` 设 `tabindex=-1` 并 `focus({preventScroll:true})`，屏幕阅读器可感知视图变化；`main:focus { outline: none; }` 避免整页焦点框。
- 降级：`installSpaRouter()` 检查 `window`/`http(s)`/History API/`fetch`/`DOMParser`；不满足则完全不安装，保留原多页站。

### D4 测试与文档

- `tools/_smoke_web.js`：新增纯函数路由断言；DOM shim 无 `window` 时路由器不安装，原初始化测试不受影响。
- `tools/_spa_check.js`：真实 Chromium 回归（Playwright），覆盖无刷新、URL/标题、搜索状态返回、语言切换、滚动恢复、前进/后退、深链、console/CSP。
- `README.md` + 本 spec 记录行为与命令。

## [S3] Out of Scope

- 不合并成单一 HTML 入口；不引入 hash 路由、服务端 rewrite、前端框架或构建链。
- 不改数据契约（`schema_version` 仍为 1）、不改 Python 抓取/解析/配对、不改 `pages.yml`/`ci.yml`。
- 不把 Playwright 浏览器回归加进 CI（与既有 `_layout_check.js` 一样手动运行）；不新增运行时依赖。
- 不做视觉改版、不做页面间转场动画、不做视口内组件级局部刷新。
- 异常深链缺少必需参数时仍走既有 `location.href` 整页兜底（正常站内链接不会产生这种 URL）。

## Tasks

- [x] T1: `web/app.js` 路由/壳缓存/点击代理/popstate/降级 — acceptance: 站内五页切换无文档 load (covers: D1)
- [x] T2: 导航串行化、令牌、滚动/历史、焦点 — acceptance: 前进后退、滚动恢复、语言切换保持位置 (covers: D2)
- [x] T3: 清理注册表、页面状态重置、JSON 缓存 — acceptance: 旧 timer/observer 不跨页触发；重复进入状态正确 (covers: D3)
- [x] T4: smoke 路由断言 + `tools/_spa_check.js` — acceptance: 两个测试全绿，0 console/CSP 错误 (covers: D4)
- [x] T5: README/spec — acceptance: 文档说明行为、降级与运行命令 (covers: D4)
- [x] T6: 全量验证 — acceptance: `_smoke_web.js` / `pytest` / `_spa_check.js` / `_layout_check.js` 全绿
