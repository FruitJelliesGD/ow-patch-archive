/* Shared helpers for the OW patch archive site (time browser + hero query). */
"use strict";

const ROLE_LABEL = { tank: "重装", damage: "输出", support: "支援" };
const KIND_LABEL = { ability: "技能改动", perk: "威能改动", general: "其他改动" };
const ITEM_KIND_LABEL = { weapon: "武器", ability: "技能", survival: "生存", power: "异能" };
const DIM_LABEL = { weapon: "武器", ability: "技能", perk: "威能", hero_attr: "英雄属性", hero: "英雄", other: "其他" };
const ATTR_LABEL = {
  health: "生命值", ultimate_cost: "终极技能消耗", move_speed: "移动速度",
  base_stat: "基础属性", other: "其他",
};
const SITE_LABEL = { en: "英文站", cn: "中文站" };
// mirror of src/ow2_patch/modes.py MODE_LABELS
const MODE_LABEL = {
  standard: "常规", quick_play_hacked: "快速比赛：黑客入侵", april_fools: "愚人节",
  experiment_6v6: "实验模式", hero_trial: "英雄试玩", ptr: "PTR 测试服",
  announcement: "公告", community_created: "社区创造模式",
};
const STATUS_LABEL = {
  added: "新增", removed: "移除", reworked: "重做", moved: "变更", changed: "调整",
};
// mirror of src/ow2_patch/categories.py CATEGORY_LABELS / CATEGORY_ORDER,
// plus the frontend-only hero_changes key (structural signal, not a content
// category: buildCategoryChips appends it separately, filterMatches matches it
// via mode + has_hero_changes)
const CATEGORY_LABEL = {
  quick_play_hacked: "快速比赛：黑客入侵", april_fools: "愚人节",
  experiment_6v6: "实验模式", hero_trial: "英雄试玩", ptr: "PTR 测试服",
  community_created: "社区创造模式",
  event: "活动", season: "新赛季", new_hero: "新英雄", new_map: "新地图",
  stadium: "角斗领域", arcade: "街机", workshop: "自定义工坊", owl: "联赛",
  crossover: "联动",
  hero_changes: "英雄改动",
};
const CATEGORY_ORDER = [
  "quick_play_hacked", "april_fools", "experiment_6v6", "hero_trial", "ptr",
  "community_created", "event", "season", "new_hero", "new_map",
  "stadium", "arcade", "workshop", "owl", "crossover",
];
const MONTH_LABEL = ["", "1月", "2月", "3月", "4月", "5月", "6月",
  "7月", "8月", "9月", "10月", "11月", "12月"];

async function fetchJSON(path) {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`failed to load ${path}: ${resp.status}`);
  return resp.json();
}

// String-based escaper: no DOM round-trip (this runs a few thousand times per
// page) and attribute-safe — quotes are escaped too, so `esc()` output can sit
// inside title="…" / alt="…" / src="…" without breaking out of the attribute.
const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

function esc(text) {
  return String(text == null ? "" : text).replace(/[&<>"']/g, (ch) => ESCAPES[ch]);
}

function fmtNum(v) {
  return typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(2)) : v;
}

// UTC ISO timestamp -> "YYYY-MM-DD HH:mm UTC±H" in the viewer's local timezone
function fmtLocalTs(ts) {
  const d = new Date(ts);
  if (isNaN(d) || !/T/.test(String(ts))) return ts || "";
  const pad = (n) => String(n).padStart(2, "0");
  const off = -d.getTimezoneOffset(); // minutes east of UTC (+480 for UTC+8)
  const zone = `UTC${off >= 0 ? "+" : "-"}${Math.floor(Math.abs(off) / 60)}`
    + (off % 60 ? ":" + pad(Math.abs(off) % 60) : "");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())} ${zone}`;
}

// date-only rendering for values that are calendar dates, not instants:
// patches_index.updated is the newest patch date at UTC midnight, so turning it
// into a wall-clock "last fetched" timestamp would invent a time that never
// happened.
function fmtDate(ts) {
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(String(ts == null ? "" : ts));
  return m ? m[1] : String(ts || "");
}

// live page metadata: browser tab titles double as history/bookmark labels
function setPageMeta(title, description) {
  document.title = title;
  const meta = document.querySelector && document.querySelector('meta[name="description"]');
  if (meta && meta.setAttribute) meta.setAttribute("content", description || title);
}

// Reflect UI state into the URL so a filtered/searched view can be shared and
// survives a reload. replaceState (not pushState): toggling chips must not
// stack history entries. Falls back to assigning location.search only where
// the History API is absent (the DOM shim used by tools/_smoke_web.js).
function syncURLState(values) {
  const params = new URLSearchParams(location.search || "");
  for (const [key, value] of Object.entries(values)) {
    if (value == null || value === "") params.delete(key);
    else params.set(key, String(value));
  }
  const qs = params.toString();
  const next = qs ? "?" + qs : "";
  if (typeof history !== "undefined" && history.replaceState) {
    history.replaceState(null, "", (location.pathname || "") + next);
  } else if (location.search !== next) {
    location.search = next;
  }
}

function numberify(html) {
  return html.replace(/(\d+(?:\.\d+)?\s*→\s*\d+(?:\.\d+)?)/g, '<span class="num">$1</span>');
}

function inlineBold(html) {
  // parser-encoded **bold** markers -> <strong>; runs on already-escaped HTML
  return html.replace(/\*\*([^*]+?)\*\*/g, "<strong>$1</strong>");
}

// parser-encoded inline media: ![alt](src) images and [text](url) links
// (https only). Runs on already-escaped HTML in a single pass so image alt /
// link text are not reprocessed by the other passes (an alt with [x](y) would
// otherwise be linkified inside an attribute).
function media(html) {
  return html.replace(/(!\[([^\]]*)\]|\[([^\]]+)\])\(([^)]+)\)/g, (m, pre, alt, text, url) => {
    // plain http (and protocol-relative //host) is rejected: mixed content on
    // the https site, and the comment above has always claimed https-only
    if (!/^https:\/\//i.test(url)) return m;
    if (pre.startsWith("!")) {
      // referrerpolicy: the images are hotlinked from Blizzard's CDN
      return `<img src="${url}" alt="${alt || ""}" loading="lazy" referrerpolicy="no-referrer">`;
    }
    return `<a href="${url}" target="_blank" rel="noopener noreferrer">${text}</a>`;
  });
}

// shared post-escape chain: **bold** -> <strong>, [text](url)/![alt](src) ->
// <a>/<img>, "N → N" -> .num
function postProcess(html) {
  return numberify(media(inlineBold(html)));
}

function deaccent(s) {
  return String(s).normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
}

// EN display-name spellings in OW1-era pages that map to canonical slugs
const LEGACY_ALIASES = {
  "McCree": "cassidy",
  "Solider: 76": "soldier-76",
  "Soldier:76": "soldier-76",
  "Junkerqueen": "junker-queen",
  "Iliari": "illari",
};

function reEscape(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// case-sensitive whole-token match; avoids \b so names ending in ")" match
function nameMatch(name, text) {
  const re = new RegExp("(?:^|[^A-Za-z0-9])(" + reEscape(name) + ")(?![A-Za-z0-9])");
  const m = re.exec(text);
  if (!m) return null;
  return { index: m.index + m[0].indexOf(m[1]), len: m[1].length };
}

/* ---------- rich-text rendering (patch detail) ---------- */

// Render structure-preserved parser output: paragraphs separated by blank
// lines, "- " list items (nested lists indented 2 spaces per level). Every
// text fragment is escaped; the parser never emits raw HTML.
function renderRich(el, text) {
  const paras = String(text == null ? "" : text).split(/\n{2,}/);
  for (const para of paras) {
    const trimmed = para.trim();
    if (!trimmed) continue;
    if (/^- /.test(trimmed)) {
      el.appendChild(renderList(trimmed));
    } else {
      const p = document.createElement("p");
      p.innerHTML = postProcess(esc(trimmed).replace(/\n/g, "<br>"));
      el.appendChild(p);
    }
  }
}

function renderList(text) {
  const ul = document.createElement("ul");
  const stack = [ul];
  for (const rawLine of text.split("\n")) {
    const m = rawLine.match(/^(\s*)- (.*)$/);
    if (!m) continue;
    const depth = Math.floor(m[1].length / 2);
    while (stack.length - 1 > depth) stack.pop();
    if (stack.length - 1 < depth) {
      const parent = stack[stack.length - 1];
      const nested = document.createElement("ul");
      (parent.lastElementChild || parent).appendChild(nested);
      stack.push(nested);
    }
    const li = document.createElement("li");
    li.innerHTML = postProcess(esc(m[2]).replace(/\n/g, "<br>"));
    stack[stack.length - 1].appendChild(li);
  }
  return ul;
}

// No inline onerror handler: images that fail to load are hidden by the single
// capture-phase error listener installed in installImageFallback(), which keeps
// the page compatible with a strict Content-Security-Policy.
function iconImg(path, alt, cls) {
  return `<img class="${esc(cls || "")}" src="${esc(path)}" alt="${esc(alt || "")}" loading="lazy">`;
}

function heroIconPath(slug) {
  return `assets/icons/heroes/${esc(slug)}.png`;
}

// Hero icons that actually exist (written by tools/download_icons.py). A hero
// that only ever appeared in hero_attr records has no captured portrait, so
// rendering one anyway would 404 on every list page. null = manifest missing:
// fall back to rendering optimistically (the load-error listener hides misses).
let heroIconSet = null;

async function loadHeroIconSet() {
  try {
    const data = await fetchJSON("assets/icons/index.json");
    heroIconSet = new Set(data.heroes || []);
  } catch {
    heroIconSet = null;
  }
  return heroIconSet;
}

function heroAvatar(slug, alt, cls) {
  if (!slug) return "";
  if (heroIconSet && !heroIconSet.has(String(slug))) return "";
  return iconImg(heroIconPath(slug), alt, cls);
}

function abilityIconPath(heroSlug, abilitySlug) {
  return `assets/icons/abilities/${esc(heroSlug)}/${esc(abilitySlug)}.png`;
}

function siteBadges(sites) {
  return (sites || []).map((s) => `<span class="badge ${esc(s)}">${SITE_LABEL[s] || s}</span>`).join(" ");
}

function modeBadge(mode) {
  if (!mode || mode === "standard") return "";
  return `<span class="badge mode mode-${esc(mode)}">${MODE_LABEL[mode] || mode}</span>`;
}

// 「英雄改动」badge: only standard-mode patches whose content actually
// contributes to the hero balance history (pairing.py `has_hero_changes`).
// Special-mode patches (愚人节/PTR/实验/试玩/社区创造/…) carry the flag but
// must never show the badge.
function heroChangesBadge(p) {
  if (p.mode !== "standard" || !p.has_hero_changes) return "";
  return `<span class="badge hero-changes">英雄改动</span>`;
}

// display-only badges: content categories (categories.py) — the patch content
// mentions the category phrase but mode classification is untouched, so
// standard-titled mixed patches keep their hero data. The patch's own mode key
// is skipped: the mode badge already renders it.
function categoryBadges(p) {
  if (!p || !p.categories) return "";
  return p.categories
    .filter((k) => k !== p.mode)
    .map((k) => `<span class="badge mode mode-${esc(k)}">${CATEGORY_LABEL[k] || k}</span>`)
    .join(" ");
}

/* ---------- time browser (index.html) ---------- */

// Sticky year/month jump bar. The shell (two selects + button) is built once;
// its options are refilled from whatever is currently visible, so a category
// filter can never leave a jump target that no longer exists. Built with
// createElement/appendChild only so the smoke DOM shim can exercise it.
const jumpState = { years: new Map(), year: "" };

function buildJumpBar() {
  const bar = document.getElementById("jump-bar");
  const hint = document.createElement("span");
  hint.className = "jump-hint";
  hint.textContent = "跳转到：";
  const yearSel = document.createElement("select");
  yearSel.id = "jump-year";
  yearSel.title = "选择年份";
  yearSel.setAttribute("aria-label", "选择年份");
  const monthSel = document.createElement("select");
  monthSel.id = "jump-month";
  monthSel.title = "选择月份";
  monthSel.setAttribute("aria-label", "选择月份");
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "jump-btn";
  btn.textContent = "跳转";
  bar.appendChild(hint);
  bar.appendChild(yearSel);
  bar.appendChild(monthSel);
  bar.appendChild(btn);

  yearSel.addEventListener("change", () => {
    jumpState.year = yearSel.value;
    fillJumpMonths(jumpState.years, jumpState.year, "");
  });
  btn.addEventListener("click", () => {
    document.getElementById(`year-${yearSel.value}-month-${monthSel.value}`)
      ?.scrollIntoView?.({ behavior: "smooth" });
  });
}

function fillJumpBar(years) {
  const yearSel = document.getElementById("jump-year");
  const monthSel = document.getElementById("jump-month");
  if (!yearSel || !monthSel) return;
  const yearList = [...years.keys()].sort((a, b) => b.localeCompare(a));
  const prevYear = jumpState.year || yearSel.value;
  yearSel.replaceChildren();
  for (const y of yearList) {
    const opt = document.createElement("option");
    opt.value = y;
    opt.textContent = `${y} 年`;
    yearSel.appendChild(opt);
  }
  const year = yearList.includes(prevYear) ? prevYear : (yearList[0] || "");
  jumpState.years = years;
  jumpState.year = year;
  yearSel.value = year;
  fillJumpMonths(years, year, monthSel.value);
}

function fillJumpMonths(years, year, prevMonth) {
  const monthSel = document.getElementById("jump-month");
  if (!monthSel) return;
  const months = [...(years.get(year) || new Map()).keys()].sort((a, b) => b.localeCompare(a));
  monthSel.replaceChildren();
  for (const m of months) {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = MONTH_LABEL[Number(m)];
    monthSel.appendChild(opt);
  }
  monthSel.value = months.includes(prevMonth) ? prevMonth : (months[0] || "");
}

// sticky-bar height -> --sticky-h so the anchor offset can never be smaller
// than the bar itself (the chips row makes the bar taller on narrow screens)
function trackStickyHeight() {
  const bar = document.getElementById("jump-bar");
  if (!bar || typeof ResizeObserver === "undefined") return;
  const root = document.documentElement;
  if (!root || !root.style) return;
  const apply = () => root.style.setProperty("--sticky-h", `${bar.offsetHeight || 0}px`);
  new ResizeObserver(apply).observe(bar);
  apply();
}

let allPatches = [];
const filter = { selected: new Set() };

function filterMatches(p) {
  if (filter.selected.size === 0) return true;
  return [...filter.selected].some((k) =>
    k === "hero_changes"
      ? (p.mode === "standard" && p.has_hero_changes)
      : (p.mode === k || (p.categories || []).includes(k)));
}

function groupByYearMonth(patches) {
  const years = new Map();
  for (const p of patches) {
    const [y, m] = p.date.split("-");
    if (!years.has(y)) years.set(y, new Map());
    const months = years.get(y);
    if (!months.has(m)) months.set(m, []);
    months.get(m).push(p);
  }
  return years;
}

function renderTimeBrowser(patches, filterFn) {
  const container = document.getElementById("patch-list");
  const visible = filterFn ? patches.filter(filterFn) : patches;
  container.replaceChildren();
  fillJumpBar(groupByYearMonth(visible));

  const count = document.getElementById("patch-count");
  if (count) {
    const active = [...filter.selected].map((k) => CATEGORY_LABEL[k] || k);
    count.textContent = `共 ${visible.length} 条补丁${active.length ? `　筛选：${active.join(" / ")}` : ""}`;
  }
  if (!visible.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const p = document.createElement("p");
    p.textContent = "当前筛选下没有补丁。";
    const clear = document.createElement("button");
    clear.type = "button";
    clear.className = "jump-btn";
    clear.textContent = "清空筛选";
    clear.addEventListener("click", () => setFilter([]));
    empty.appendChild(p);
    empty.appendChild(clear);
    container.appendChild(empty);
    return;
  }

  const years = groupByYearMonth(visible);
  for (const [year, months] of [...years.entries()].sort((a, b) => b[0].localeCompare(a[0]))) {
    const yearSection = document.createElement("section");
    yearSection.className = "year";
    yearSection.id = `year-${year}`;
    yearSection.innerHTML = `<h2 class="year-title">${esc(year)}</h2>`;
    for (const [month, entries] of [...months.entries()].sort((a, b) => b[0].localeCompare(a[0]))) {
      const monthSection = document.createElement("div");
      monthSection.className = "month";
      monthSection.id = `year-${year}-month-${month}`;
      monthSection.innerHTML = `<h3 class="month-title">${MONTH_LABEL[Number(month)]}</h3>`;
      const list = document.createElement("div");
      list.className = "patch-list";
      for (const p of entries) {
        const site = p.sites.includes("cn") ? "cn" : "en";
        // the entry title is the first section title (Hotfix Update / 在线修正
        // 更新), falling back to the same-language official title before the
        // other language's section title (a CN patch whose CN side was never
        // archived must show its Chinese long title, not the EN section title)
        const title = site === "cn"
          ? (p.first_section_cn || p.title_cn || p.first_section_en || p.title_en)
          : (p.first_section_en || p.title_en || p.first_section_cn || p.title_cn);
        const chars = site === "cn" ? (p.chars_cn ?? p.chars_en) : (p.chars_en ?? p.chars_cn);
        const a = document.createElement("a");
        a.className = "patch-entry";
        a.href = `patch.html?id=${encodeURIComponent(p.id)}&lang=${site}`;
        a.innerHTML = `
          <span class="patch-entry-date">${esc(p.date)}</span>
          ${siteBadges(p.sites)}
          ${modeBadge(p.mode)}
          ${heroChangesBadge(p)}
          ${categoryBadges(p)}
          <span class="patch-entry-title">${esc(title || p.id)}</span>
          ${chars ? `<span class="patch-entry-chars">${Number(chars).toLocaleString()} 字</span>` : ""}`;
        list.appendChild(a);
      }
      monthSection.appendChild(list);
      yearSection.appendChild(monthSection);
    }
    container.appendChild(yearSection);
  }
}

// Multi-select content filter chips, appended inside the sticky jump bar.
function buildCategoryChips(patches) {
  const present = new Set();
  for (const p of patches) {
    for (const k of p.categories || []) present.add(k);
  }
  const chips = document.createElement("div");
  chips.className = "chips";
  chips.id = "cat-chips";
  chips.setAttribute("role", "group");
  chips.setAttribute("aria-label", "按内容分类筛选补丁");
  const allBtn = document.createElement("button");
  allBtn.type = "button";
  allBtn.className = "chip active";
  allBtn.dataset.cat = "";
  allBtn.textContent = "全部";
  allBtn.addEventListener("click", () => toggleCat(""));
  chips.appendChild(allBtn);
  for (const key of CATEGORY_ORDER) {
    if (!present.has(key)) continue;
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.dataset.cat = key;
    b.textContent = CATEGORY_LABEL[key] || key;
    b.addEventListener("click", () => toggleCat(key));
    chips.appendChild(b);
  }
  // structural hero-changes chip: not a content category, appended after the
  // CATEGORY_ORDER chips when at least one standard-mode patch carries the flag
  if (patches.some((p) => p.mode === "standard" && p.has_hero_changes)) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.dataset.cat = "hero_changes";
    b.textContent = CATEGORY_LABEL.hero_changes;
    b.addEventListener("click", () => toggleCat("hero_changes"));
    chips.appendChild(b);
  }
  document.getElementById("jump-bar").appendChild(chips);
  syncChips();
}

function toggleCat(key) {
  if (key === "") {
    filter.selected.clear();
  } else if (filter.selected.has(key)) {
    filter.selected.delete(key);
  } else {
    filter.selected.add(key);
  }
  syncChips();
  renderTimeBrowser(allPatches, filterMatches);
  syncURLState({ cat: [...filter.selected].join(",") });
}

function syncChips() {
  const chips = document.getElementById("cat-chips");
  if (!chips) return;
  for (const btn of chips.children) {
    const key = btn.dataset.cat || "";
    const active = key === "" ? filter.selected.size === 0 : filter.selected.has(key);
    btn.className = "chip" + (active ? " active" : "");
    btn.setAttribute?.("aria-pressed", active ? "true" : "false");
  }
}

// smoke-test hook: same semantics as the chips, callable directly
function setFilter(keys) {
  filter.selected = new Set((keys || []).filter((k) => CATEGORY_LABEL[k]));
  syncChips();
  renderTimeBrowser(allPatches, filterMatches);
  syncURLState({ cat: [...filter.selected].join(",") });
}

function getFilter() {
  return [...filter.selected];
}

async function initIndex() {
  const data = await fetchJSON("data/patches_index.json");
  const updated = document.getElementById("updated");
  updated.textContent = fmtDate(data.updated) || "-";
  updated.title = "最新补丁日期（不是抓取时间）";
  allPatches = data.patches || [];

  // ?cat=a,b seeds the initial filter; every later change is written back to
  // the URL by toggleCat/setFilter so the current view is shareable
  const q = new URLSearchParams(location.search).get("cat");
  if (q) {
    for (const k of q.split(",")) {
      if (CATEGORY_LABEL[k]) filter.selected.add(k);
    }
  }

  buildJumpBar();
  buildCategoryChips(allPatches);
  renderTimeBrowser(allPatches, filterMatches);
  trackStickyHeight();
  setPageMeta(
    "守望先锋 · 补丁说明归档",
    `按时间浏览守望先锋补丁说明：${allPatches.length} 个补丁，中英文合并展示。`);
}

/* ---------- entry search (entries.html) ---------- */

const ENTRY_DIM_ORDER = ["weapon", "ability", "perk", "hero_attr", "hero"];
const HERO_ROLE_ORDER = ["tank", "damage", "support"];
const ENTRY_PAGE_SIZE = 60;

// Renamed heroes / source-site typos users still type. Folded with every other
// searchable field, so "McCree"/"麦克雷" reach Cassidy without touching the data.
const HERO_SEARCH_ALIASES = {
  cassidy: ["McCree", "麦克雷"],
  "soldier-76": ["Solider: 76", "Soldier:76"],
  "junker-queen": ["Junkerqueen"],
  illari: ["Iliari"],
  "d-va": ["DVa", "DVA"],
  "d-mon": ["DMon"],
  "wrecking-ball": ["WreckingBall"],
  "lifeweaver": ["LifeWeaver"],
};

// Search folding: NFKD turns full-width forms into ASCII, stripping combining
// marks removes accents (Lúcio -> lucio) and the punctuation pass makes
// "D.Va" / "B.O.B." / "Soldier: 76" tokenizable. Everything downstream (matching,
// ranking, highlighting) works on folded text.
function foldSearch(value) {
  return String(value == null ? "" : value)
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function compactSearch(value) {
  return foldSearch(value).replace(/ /g, "");
}

// One precomputed document per entry: the flat token list (ASCII exact/prefix
// matching), the joined text (CJK substring matching) and compacted names
// (whole-name matching for "soldier76"/"dva"/"bob").
function buildEntrySearchDoc(entry) {
  const fields = [
    entry.name_cn, entry.name_en, entry.slug,
    entry.hero_cn, entry.hero_en, entry.hero_slug,
    ...(entry.variants || []),
    DIM_LABEL[entry.dimension] || entry.dimension,
    ...(HERO_SEARCH_ALIASES[entry.hero_slug] || []),
  ].filter(Boolean).map(foldSearch).filter(Boolean);
  const names = [entry.name_cn, entry.name_en, entry.slug].filter(Boolean).map(foldSearch);
  const heroes = [entry.hero_cn, entry.hero_en, entry.hero_slug].filter(Boolean).map(foldSearch);
  entry._tokens = [...new Set(fields.join(" ").split(" ").filter(Boolean))];
  entry._text = fields.join(" ");
  entry._nameCompact = [...new Set(names.map((n) => n.replace(/ /g, "")))];
  entry._heroTokens = [...new Set(heroes.join(" ").split(" ").filter(Boolean))];
  entry._heroCompact = [...new Set(heroes.map((n) => n.replace(/ /g, "")))];
  entry._compactAll = [...new Set([...entry._nameCompact, ...entry._heroCompact])];
  // mixed-script fields (e.g. "士兵76") are the only place an ASCII query token
  // may legitimately sit inside a longer token; keeping them apart from the
  // Latin fields avoids "dva" matching "advan…
  entry._cjkText = fields.filter((f) => /[\u3400-\u9fff]/.test(f)).join(" ");
  return entry;
}

function parseEntryQuery(raw) {
  const text = foldSearch(raw);
  return { text, tokens: [...new Set(text.split(" ").filter(Boolean))] };
}

function tokenHits(tokens, compacts, token) {
  return tokens.some((t) => t === token || t.startsWith(token))
    || compacts.some((c) => c.startsWith(token));
}

// Every query token must hit something (multi-word AND). ASCII tokens match
// token-exactly, as a prefix, as a prefix of a compacted name, or inside a
// mixed-script field ("76" in "士兵76"); a token containing CJK falls back to
// substring matching (Chinese has no spaces).
function entryMatches(doc, tokens) {
  return tokens.every((token) => {
    if (/[\u3400-\u9fff\uf900-\ufaff]/.test(token)) return doc._text.includes(token);
    return tokenHits(doc._tokens, doc._compactAll, token) || doc._cjkText.includes(token);
  });
}

// 0 exact name, 1 name prefix, 2 hero-name match (searching a hero lists their
// entries behind the hero card), 3 anything else that matched.
function entryRank(doc, queryText, tokens) {
  const compactQuery = queryText.replace(/ /g, "");
  if (doc._nameCompact.some((n) => n === compactQuery)) return 0;
  if (doc._nameCompact.some((n) => compactQuery.length >= 2 && n.startsWith(compactQuery))) return 1;
  if (tokens.every((t) => tokenHits(doc._heroTokens, doc._heroCompact, t))) return 2;
  return 3;
}

// wrap the first occurrence of any query token in <mark>
function highlightTokens(text, tokens) {
  const s = String(text == null ? "" : text);
  if (!tokens || !tokens.length) return esc(s);
  const lower = s.toLowerCase();
  let best = null;
  for (const token of tokens) {
    const i = lower.indexOf(token);
    if (i >= 0 && (!best || i < best.index)) best = { index: i, token };
  }
  if (!best) return esc(s);
  const end = best.index + best.token.length;
  return esc(s.slice(0, best.index)) + `<mark>${esc(s.slice(best.index, end))}</mark>` + esc(s.slice(end));
}

// shared by the list page and by the detail pages (a linked card keeps the
// current search so "← 词条检索" goes back to the same result set)
const entrySearchState = { q: "", dim: "", limit: ENTRY_PAGE_SIZE };
let entryDocs = [];
let entryFiltered = [];

function entryHref(entry) {
  const params = new URLSearchParams();
  params.set("hero", entry.hero_slug || "");
  params.set("key", entry.key || "");
  const q = (entrySearchState.q || "").trim();
  if (q) params.set("q", q);
  if (entrySearchState.dim) params.set("dim", entrySearchState.dim);
  return `entry.html?${params.toString()}`;
}

function entriesHref() {
  const params = new URLSearchParams();
  const q = (entrySearchState.q || "").trim();
  if (q) params.set("q", q);
  if (entrySearchState.dim) params.set("dim", entrySearchState.dim);
  const qs = params.toString();
  return qs ? `entries.html?${qs}` : "entries.html";
}

// point the detail pages' "back" affordances at the current search state
function applyEntriesNav() {
  const href = entriesHref();
  for (const id of ["back-entries", "nav-entries"]) {
    const el = document.getElementById(id);
    if (el) el.href = href;
  }
}

// read ?q/?dim for the detail pages so their links keep the search context
function absorbEntrySearchParams() {
  const params = new URLSearchParams(location.search);
  const dim = params.get("dim") || "";
  entrySearchState.q = params.get("q") || "";
  entrySearchState.dim = ENTRY_DIM_ORDER.includes(dim) ? dim : "";
  applyEntriesNav();
}

function selectedEntryMatches() {
  const { text, tokens } = parseEntryQuery(entrySearchState.q);
  const hits = [];
  for (const entry of entryDocs) {
    if (entrySearchState.dim && entry.dimension !== entrySearchState.dim) continue;
    if (tokens.length && !entryMatches(entry, tokens)) continue;
    hits.push({ entry, rank: tokens.length ? entryRank(entry, text, tokens) : 3 });
  }
  if (tokens.length) {
    hits.sort((a, b) => a.rank - b.rank
      || (b.entry.changes || 0) - (a.entry.changes || 0)
      || String(a.entry.name_cn || a.entry.name_en || "")
        .localeCompare(String(b.entry.name_cn || b.entry.name_en || ""), "zh"));
  }
  return hits;
}

function entryEmptyState() {
  const box = document.createElement("div");
  box.className = "empty-state";
  const q = (entrySearchState.q || "").trim();
  const dimLabel = entrySearchState.dim ? (DIM_LABEL[entrySearchState.dim] || entrySearchState.dim) : "";
  const p = document.createElement("p");
  p.textContent = q
    ? `没有匹配「${q}」的${dimLabel ? dimLabel + "类" : ""}词条。`
    : "当前筛选下没有词条。";
  const clear = document.createElement("button");
  clear.type = "button";
  clear.className = "jump-btn";
  clear.textContent = "清空搜索";
  clear.addEventListener("click", () => resetEntrySearch(false));
  const all = document.createElement("button");
  all.type = "button";
  all.className = "jump-btn ghost";
  all.textContent = "查看全部词条";
  all.addEventListener("click", () => resetEntrySearch(true));
  box.appendChild(p);
  box.appendChild(clear);
  box.appendChild(all);
  return box;
}

function resetEntrySearch(clearDim) {
  entrySearchState.q = "";
  if (clearDim) entrySearchState.dim = "";
  const input = document.getElementById("search");
  if (input) input.value = "";
  syncDimChips();
  applyEntryFilter();
}

function syncDimChips() {
  const filters = document.getElementById("filters");
  if (!filters) return;
  for (const chip of filters.children) {
    const active = (chip.dataset.dim || "") === entrySearchState.dim;
    chip.classList.toggle("active", active);
    chip.setAttribute("aria-pressed", active ? "true" : "false");
  }
}

function renderEntryResults() {
  const total = entryFiltered.length;
  const shown = Math.min(entrySearchState.limit, total);
  const count = document.getElementById("result-count");
  if (count) count.textContent = `共 ${total} / ${entryDocs.length} 个词条`;
  const { tokens } = parseEntryQuery(entrySearchState.q);
  const grid = document.getElementById("results");
  grid.replaceChildren();
  for (const hit of entryFiltered.slice(0, shown)) grid.appendChild(entryCard(hit.entry, tokens));
  grid.dataset.shown = String(shown);
  const status = document.getElementById("entry-status");
  if (!status) return;
  status.replaceChildren();
  if (!total) {
    status.appendChild(entryEmptyState());
  } else if (shown < total) {
    const more = document.createElement("button");
    more.type = "button";
    more.id = "load-more";
    more.className = "jump-btn";
    more.textContent = `加载更多（还剩 ${total - shown} 条）`;
    more.addEventListener("click", showMoreEntries);
    status.appendChild(more);
  }
}

// smoke-test hook + the "load more" handler: appending never re-sorts/re-filters
function showMoreEntries() {
  entrySearchState.limit += ENTRY_PAGE_SIZE;
  renderEntryResults();
}

function applyEntryFilter() {
  entryFiltered = selectedEntryMatches();
  entrySearchState.limit = ENTRY_PAGE_SIZE;
  const browse = document.getElementById("hero-browse");
  if (browse) browse.hidden = !(entrySearchState.q.trim() === "" && !entrySearchState.dim);
  renderEntryResults();
  syncURLState({ q: entrySearchState.q.trim(), dim: entrySearchState.dim });
}

async function initEntries() {
  const [data, heroData] = await Promise.all([
    fetchJSON("data/entries_index.json"),
    // auxiliary: the hero browse section degrades to hidden if it is missing
    fetchJSON("data/heroes_index.json").catch(() => ({ heroes: [] })),
    loadHeroIconSet(),
  ]);
  entryDocs = (data.entries || []).map(buildEntrySearchDoc);

  buildHeroBrowse(heroData.heroes || [], entryDocs);

  const params = new URLSearchParams(location.search);
  const dim = params.get("dim") || "";
  entrySearchState.q = params.get("q") || "";
  entrySearchState.dim = ENTRY_DIM_ORDER.includes(dim) ? dim : "";

  const filters = document.getElementById("filters");
  filters.replaceChildren();
  const chipDefs = [["", "全部"], ...ENTRY_DIM_ORDER.map((d) => [d, DIM_LABEL[d]])];
  for (const [chipDim, label] of chipDefs) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = label;
    b.dataset.dim = chipDim;
    filters.appendChild(b);
  }
  syncDimChips();

  const searchEl = document.getElementById("search");
  searchEl.value = params.get("q") || "";

  // debounce so a fast typist does not re-filter/re-render per keystroke; the
  // first paint stays synchronous
  let timer = 0;
  searchEl.addEventListener("input", (ev) => {
    entrySearchState.q = ev.target.value || "";
    clearTimeout(timer);
    timer = setTimeout(applyEntryFilter, 120);
  });
  filters.addEventListener("click", (ev) => {
    const chip = ev.target.closest?.(".chip");
    if (!chip) return;
    entrySearchState.dim = chip.dataset.dim || "";
    syncDimChips();
    applyEntryFilter();
  });
  applyEntryFilter();
  setPageMeta(
    "守望先锋 · 词条检索",
    `搜索 ${entryDocs.length} 个技能 / 武器 / 威能 / 英雄属性词条，追溯每个词条的完整更改记录。`);
}

// "按英雄浏览": the hero timeline page was only reachable from an entry page
// before, even though heroes_index.json carries role + names for every hero
function buildHeroBrowse(heroes, entries) {
  const host = document.getElementById("hero-browse");
  if (!host || !heroes.length) return;
  const counts = new Map();
  for (const e of entries) counts.set(e.hero_slug, (counts.get(e.hero_slug) || 0) + 1);
  host.replaceChildren();
  const title = document.createElement("h2");
  title.className = "section-title";
  title.textContent = "按英雄浏览";
  host.appendChild(title);
  const roles = [...HERO_ROLE_ORDER, "__other__"];
  for (const role of roles) {
    const group = heroes.filter((h) => (HERO_ROLE_ORDER.includes(h.role) ? h.role : "__other__") === role);
    if (!group.length) continue;
    const rt = document.createElement("h3");
    rt.className = "role-title";
    rt.textContent = role === "__other__" ? "其他" : (ROLE_LABEL[role] || role);
    host.appendChild(rt);
    const grid = document.createElement("div");
    grid.className = "hero-grid";
    for (const h of group) grid.appendChild(heroCard(h, counts.get(h.slug) || 0));
    host.appendChild(grid);
  }
}

function heroCard(hero, entryCount) {
  const a = document.createElement("a");
  a.className = "hero-card";
  a.href = `hero.html?slug=${encodeURIComponent(hero.slug)}`;
  const cn = hero.cn || hero.en || hero.slug;
  a.innerHTML = `
    ${heroAvatar(hero.slug, cn, "hero-card-avatar")}
    <span class="hero-card-names">
      <span class="cn">${esc(cn)}</span>
      <span class="en">${esc(hero.en || "")}</span>
    </span>
    <span class="count">${entryCount}</span>`;
  return a;
}

function entryCard(e, tokens, withState = true) {
  const a = document.createElement("a");
  a.className = "entry-card";
  a.href = withState
    ? entryHref(e)
    : `entry.html?hero=${encodeURIComponent(e.hero_slug)}&key=${encodeURIComponent(e.key)}`;
  const meta = [
    `<span class="badge dim dim-${esc(e.dimension)}">${DIM_LABEL[e.dimension] || e.dimension}</span>`,
    `<span class="badge hero-role">${esc(ROLE_LABEL[e.hero_role] || e.hero_role || "")}</span>`,
    e.edited ? `<span class="badge edited">官方事后编辑</span>` : "",
  ].filter(Boolean).join(" ");
  const range = e.first_date && e.last_date && e.first_date !== e.last_date
    ? `${esc(e.first_date)} ~ ${esc(e.last_date)}` : esc(e.first_date || e.last_date || "");
  const avatar = e.hero_slug
    ? heroAvatar(e.hero_slug, e.hero_cn || e.hero_en || "", "card-avatar") : "";
  const nameCn = highlightTokens(e.name_cn || e.name_en || e.key, tokens);
  const nameEn = e.name_cn && e.name_en && e.name_cn !== e.name_en
    ? ` / ${highlightTokens(e.name_en, tokens)}` : "";
  // the card count is the merged row count, i.e. exactly what the detail page lists
  const changes = e.changes == null ? e.count : e.changes;
  a.innerHTML = `
    <div class="card-top">${avatar}${meta}</div>
    <div class="cn">${nameCn}${nameEn}</div>
    <div class="en">${highlightTokens(e.hero_cn || e.hero_en || "", tokens)}</div>
    <div class="card-meta">${changes} 条更改记录${range ? ` · ${range}` : ""}</div>`;
  return a;
}

/* ---------- hero timeline (hero.html) ---------- */

function entryKey(e) {
  const dim = e.dimension || (e.kind === "perk" ? "perk" : "other");
  if (dim === "weapon" || dim === "ability") {
    return `${dim}::${e.ability_slug || e.ability_en || e.ability_cn || ""}`;
  }
  if (dim === "perk") return `perk::${e.perk_slug || e.perk_cn || e.perk_en || ""}`;
  if (dim === "hero_attr") return `attr::${e.subject || e.metric || "other"}`;
  return `other::`;
}

function entryTitle(e) {
  const dim = e.dimension || (e.kind === "perk" ? "perk" : "other");
  if (dim === "weapon" || dim === "ability") {
    return e.ability_cn && e.ability_en ? `${e.ability_cn} / ${e.ability_en}` : (e.ability_cn || e.ability_en || "-");
  }
  if (dim === "perk") {
    return e.perk_cn && e.perk_en ? `${e.perk_cn} / ${e.perk_en}` : (e.perk_cn || e.perk_en || "-");
  }
  if (dim === "hero_attr") return ATTR_LABEL[e.subject] || e.subject || "其他";
  return "其他改动";
}

// Display name of an entries_index entry (the index learns the CURRENT official
// name from the ability map; timeline records may still carry the 2016 spelling,
// which is why the detail page used to show "脉冲步枪" for "重脉冲步枪").
function entryDisplayName(entry) {
  if (!entry) return "";
  const cn = entry.name_cn || "";
  const en = entry.name_en || "";
  if (cn && en) return cn === en ? cn : `${cn} / ${en}`;
  return cn || en || entry.key || "";
}

// Kind badge text, corrected per dimension: weapon records carry kind "ability"
// (they were parsed from ability blocks) and used to render "技能改动".
function kindLabel(kind, dimension) {
  if (dimension === "weapon") return "武器改动";
  if (dimension === "hero_attr") return "属性改动";
  return KIND_LABEL[kind] || "";
}

// Aliases worth showing on the detail page: variants minus the canonical names
// (the ability map stores both names in variants, which made every alias line
// repeat the title).
function entryAliases(entry) {
  if (!entry || !entry.variants) return [];
  const canonical = new Set([entry.name_cn, entry.name_en].filter(Boolean).map((s) => s.toLowerCase()));
  const seen = new Set();
  const out = [];
  for (const variant of entry.variants) {
    if (!variant) continue;
    const key = variant.toLowerCase();
    if (canonical.has(key) || seen.has(key)) continue;
    seen.add(key);
    out.push(variant);
  }
  return out;
}

/* ---------- EN/CN record merging (entry + hero pages) ---------- */

// patches_index.patches -> site patch id -> patch.html link for that side.
// Shared by the entry page and the hero timeline (both link a record back to
// the archived patch it came from).
function buildPatchLinkMap(patches) {
  const map = {};
  for (const p of patches || []) {
    if (p.patch_id_en) map[p.patch_id_en] = `patch.html?id=${encodeURIComponent(p.id)}&lang=en`;
    if (p.patch_id_cn) map[p.patch_id_cn] = `patch.html?id=${encodeURIComponent(p.id)}&lang=cn`;
  }
  return map;
}

// patches_index.patches -> site patch id -> {id (p-* logical), other, title_cn, title_en}
function buildPairMap(patches) {
  const map = {};
  for (const p of patches || []) {
    if (p.patch_id_en && p.patch_id_cn) {
      const meta = { id: p.id, title_cn: p.title_cn, title_en: p.title_en };
      map[p.patch_id_en] = { ...meta, other: p.patch_id_cn };
      map[p.patch_id_cn] = { ...meta, other: p.patch_id_en };
    }
  }
  return map;
}

function digitTokens(text) {
  return Array.from(String(text || "").matchAll(/\d+(?:\.\d+)?/g), (m) => m[0]);
}

// veto guard: when both sides carry numbers, a merged pair must share at least
// one exact numeric token, else they are (almost certainly) different changes
function numbersOverlap(a, b) {
  const ta = digitTokens(a);
  const tb = new Set(digitTokens(b));
  if (!ta.length || !tb.size) return true;
  return ta.some((t) => tb.has(t));
}

// Merge the EN+CN records of the same change (paired patches) into one row,
// Chinese first. Rows are {m: record to render, en: en record | null}; merged
// rows carry en_patch as a render marker. Gate: equal counts AND (kind
// ability/weapon/perk OR one-to-one) AND numeric-fingerprint consistency —
// positional merging misaligns `other` lines (23% share no numbers), so those
// only merge when each side has exactly one record.
function mergeEntryRecords(records, pairMap) {
  const groups = new Map(); // pairId|key -> {en: [], cn: []}
  for (const e of records || []) {
    const pair = pairMap[e.patch];
    if (!pair) continue;
    const gkey = `${pair.id}|${entryKey(e)}`;
    if (!groups.has(gkey)) groups.set(gkey, { en: [], cn: [] });
    groups.get(gkey)[e.site === "en" ? "en" : "cn"].push(e);
  }
  const consumed = new Set();
  const rows = [];
  for (const e of records || []) {
    if (consumed.has(e)) continue;
    const pair = pairMap[e.patch];
    if (pair) {
      const g = groups.get(`${pair.id}|${entryKey(e)}`);
      const en = g.en;
      const cn = g.cn;
      const key = entryKey(e);
      const oneToOne = en.length === 1 && cn.length === 1;
      const mergeableKind = key.startsWith("ability::") || key.startsWith("weapon::") || key.startsWith("perk::");
      if (en.length === cn.length && (mergeableKind || oneToOne)) {
        const i = (e.site === "en" ? en : cn).indexOf(e);
        const enRec = en[i];
        const cnRec = cn[i];
        if (enRec && cnRec && numbersOverlap(enRec.text_en || "", cnRec.text_cn || "")) {
          rows.push({
            m: {
              ...cnRec,
              text_en: enRec.text_en,
              lines_en: enRec.lines_en,
              url_en: enRec.url,
              en_patch: enRec.patch,
              patch_title: pair.title_cn || cnRec.patch_title,
            },
            en: enRec,
          });
          consumed.add(enRec).add(cnRec);
          continue;
        }
      }
    }
    rows.push({ m: e, en: null });
  }
  return rows;
}

async function initHero() {
  const slug = new URLSearchParams(location.search).get("slug");
  if (!slug) { location.href = "entries.html"; return; }
  let hero;
  try {
    hero = await fetchJSON(`data/heroes/${encodeURIComponent(slug)}.json`);
  } catch {
    document.getElementById("hero-name").textContent = "未找到该英雄";
    return;
  }
  document.getElementById("hero-name").textContent =
    `${hero.names.cn || hero.names.en || slug} / ${hero.names.en || ""}`.trim();
  document.getElementById("hero-role").textContent =
    ROLE_LABEL[hero.role] || hero.role || "";

  const timeline = hero.timeline || [];
  const values = hero.values || {};
  const heroName = `${hero.names.cn || hero.names.en || slug} / ${hero.names.en || ""}`.trim();
  setPageMeta(
    `${hero.names.cn || hero.names.en || slug} · 英雄改动轨迹 · 守望先锋归档`,
    `${heroName} 的完整补丁改动历史（${timeline.length} 条记录）。`);
  // pairing + patch links are auxiliary: if the index is missing the page
  // degrades to unmerged rows with no internal patch links
  let pairMap = {};
  let patchLinks = {};
  let entryNames = {};
  try {
    const index = await fetchJSON("data/patches_index.json");
    pairMap = buildPairMap(index.patches);
    patchLinks = buildPatchLinkMap(index.patches);
  } catch { /* no pairing data: keep single-site rows */ }
  // canonical group titles (renamed abilities must not show their 2016 name)
  try {
    const entries = (await fetchJSON("data/entries_index.json")).entries || [];
    for (const entry of entries) {
      const name = entryDisplayName(entry);
      if (name) entryNames[entry.key] = name;
    }
  } catch { /* no entries index: fall back to the record names */ }
  absorbEntrySearchParams();

  // the default view is standard-only (special-mode patches must not pollute
  // the balance history); ?modes=all or the toggle opt into them
  let showAll = new URLSearchParams(location.search).get("modes") === "all";
  const DIM_ORDER = ["weapon", "ability", "perk", "hero_attr", "other"];
  const main = document.getElementById("timeline");
  const count = document.createElement("p");
  count.className = "sub";
  main.appendChild(count);
  const toggle = document.createElement("label");
  toggle.className = "mode-toggle";
  toggle.innerHTML = `<input type="checkbox"${showAll ? " checked" : ""}> 包含非常规模式补丁（愚人节/实验/试玩等）`;
  main.appendChild(toggle);
  toggle.querySelector("input").addEventListener("change", (ev) => {
    showAll = ev.target.checked;
    render();
  });

  function render() {
    main.querySelectorAll(".dim-section").forEach((el) => el.remove());
    const recs = timeline.filter((e) => showAll || (e.mode || "standard") === "standard");
    const rows = mergeEntryRecords(recs, pairMap);
    count.textContent = `共 ${rows.length} 条记录`;
    const groups = new Map(); // key -> {dim, title, entries}
    for (const row of rows) {
      const e = row.m;
      const key = entryKey(e);
      const dim = e.dimension || (e.kind === "perk" ? "perk" : "other");
      if (!groups.has(key)) {
        groups.set(key, { dim, title: entryNames[`${slug}::${key}`] || entryTitle(e), entries: [] });
      }
      groups.get(key).entries.push(row);
    }
    for (const dim of DIM_ORDER) {
      const dimEntries = [...groups.values()].filter((g) => g.dim === dim);
      if (!dimEntries.length) continue;
      const dimSection = document.createElement("section");
      dimSection.className = "dim-section";
      dimSection.innerHTML = `<h2 class="dim-title"><span class="badge dim dim-${esc(dim)}">${DIM_LABEL[dim]}</span></h2>`;
      for (const { title, entries } of dimEntries) {
        const group = document.createElement("section");
        group.className = "timeline-group";
        group.innerHTML = `<h2>${esc(title)}${valueChips(values, entries[0].m)}</h2>`;
        const body = document.createElement("div");
        for (const row of entries) {
          body.appendChild(entryNode(row.m, { patchHref: patchLinks[row.m.patch] || "" }));
        }
        group.appendChild(body);
        dimSection.appendChild(group);
      }
      main.appendChild(dimSection);
    }
  }
  render();
}

function valueChips(values, entry) {
  const prefix = entry.kind === "perk" ? `perk:${entry.perk_slug}:`
    : entry.dimension === "hero_attr" ? `attr:${entry.subject || "other"}:`
    : `${entry.ability_slug}:`;
  const chips = [];
  for (const [key, points] of Object.entries(values)) {
    if (!key.startsWith(prefix)) continue;
    const arrow = points.map((p) => fmtNum(p.value)).join(" → ");
    chips.push(`<span class="values" title="${esc(key)}">${esc(arrow)}</span>`);
  }
  return chips.length ? `<span class="values-wrap">${chips.join(" ")}</span>` : "";
}

function entryNode(e, opts = {}) {
  const div = document.createElement("div");
  div.className = "entry";
  const head = document.createElement("div");
  head.className = "head";
  const patchLink = opts.patchHref && e.patch
    ? `<a class="patch-link" href="${esc(opts.patchHref)}">${e.patch_title ? esc(e.patch_title) : esc(e.patch)}</a>`
    : `<span class="patch-link">${e.patch_title ? esc(e.patch_title) : esc(e.patch)}</span>`;
  const edits = opts.edits || [];
  const editBadge = edits.length
    ? `<span class="badge edited" title="${esc(edits.map((x) => fmtLocalTs(x.ts) + (x.title ? " · " + x.title : "")).join("；"))}">官方事后编辑</span>`
    : "";
  // merged EN+CN rows (marked by en_patch) show both site badges, Chinese first
  const siteBadge = e.en_patch
    ? `<span class="badge cn">${SITE_LABEL.cn}</span> <span class="badge en">${SITE_LABEL.en}</span>`
    : `<span class="badge ${esc(e.site)}">${SITE_LABEL[e.site]}</span>`;
  head.innerHTML = `
    ${siteBadge}
    <span class="badge kind">${esc(kindLabel(e.kind, e.dimension))}</span>
    ${e.subject ? `<span class="badge attr">${ATTR_LABEL[e.subject] || e.subject}</span>` : ""}
    ${editBadge}
    <span>${esc(e.date)}</span>
    ${patchLink}`;
  div.appendChild(head);

  const text = document.createElement("div");
  text.className = "text";
  if (e.kind === "perk") {
    const status = document.createElement("span");
    status.className = `perk-status ${esc(e.status)}`;
    status.textContent = STATUS_LABEL[e.status] || e.status;
    text.appendChild(status);
    const lines = (e.lines_cn && e.lines_cn.length ? e.lines_cn : e.lines_en) || [];
    const ul = document.createElement("ul");
    for (const line of lines) {
      const li = document.createElement("li");
      li.innerHTML = numberify(esc(line));
      ul.appendChild(li);
    }
    text.appendChild(ul);
    if (e.lines_cn?.length && e.lines_en?.length) {
      const en = document.createElement("div");
      en.className = "text en-text";
      en.innerHTML = numberify(esc(e.lines_en.join(" / ")));
      text.appendChild(en);
    }
  } else {
    const line = e.text_cn || e.text_en || "";
    text.innerHTML = numberify(esc(line));
    if (e.text_cn && e.text_en && e.text_cn !== e.text_en) {
      const en = document.createElement("div");
      en.className = "text en-text";
      en.innerHTML = numberify(esc(e.text_en));
      text.appendChild(en);
    }
  }
  div.appendChild(text);

  if (e.before != null && e.after != null) {
    const num = document.createElement("div");
    num.className = "num-line";
    num.innerHTML = `数值变化：<span class="num">${fmtNum(e.before)} → ${fmtNum(e.after)}</span>${e.metric ? `（${esc(e.metric)}）` : ""}`;
    div.appendChild(num);
  } else if (e.by_pct != null) {
    const num = document.createElement("div");
    num.className = "num-line";
    num.innerHTML = `变化幅度：<span class="num">${e.by_pct}%</span>${e.metric ? `（${esc(e.metric)}）` : ""}`;
    div.appendChild(num);
  }
  if (e.url) {
    const link = document.createElement("div");
    link.className = "patch-link";
    link.innerHTML = `<a href="${esc(e.url)}" target="_blank" rel="noopener">查看官方补丁原文 ↗</a>`;
    div.appendChild(link);
  }
  if (e.url_en) {
    const link = document.createElement("div");
    link.className = "patch-link";
    link.innerHTML = `<a href="${esc(e.url_en)}" target="_blank" rel="noopener">英文原文 ↗</a>`;
    div.appendChild(link);
  }
  return div;
}

/* ---------- entry detail (entry.html) ---------- */

function valueList(values, entry) {
  const prefix = entry.kind === "perk" ? `perk:${entry.perk_slug}:`
    : entry.dimension === "hero_attr" ? `attr:${entry.subject || "other"}:`
    : `${entry.ability_slug}:`;
  const rows = [];
  for (const [key, points] of Object.entries(values)) {
    if (!key.startsWith(prefix)) continue;
    const metric = key.slice(prefix.length);
    const arrow = points.map((p) => fmtNum(p.value)).join(" → ");
    rows.push(`<div class="value-row">${esc(metric || "数值")}：<span class="num">${esc(arrow)}</span></div>`);
  }
  return rows.length ? `<div class="values-list">${rows.join("")}</div>` : "";
}

async function initEntry() {
  const params = new URLSearchParams(location.search);
  const slug = params.get("hero");
  const key = params.get("key");
  if (!slug || !key) { location.href = "entries.html"; return; }
  absorbEntrySearchParams();

  let hero;
  try {
    hero = await fetchJSON(`data/heroes/${encodeURIComponent(slug)}.json`);
  } catch {
    document.getElementById("entry-name").textContent = "未找到该词条";
    return;
  }
  let edits = { edits: {} };
  let patches = { patches: [] };
  let index = { entries: [] };
  try {
    [edits, patches, index] = await Promise.all([
      fetchJSON("data/official_edits.json"),
      fetchJSON("data/patches_index.json"),
      fetchJSON("data/entries_index.json").catch(() => ({ entries: [] })),
    ]);
  } catch { /* auxiliary data missing: degrade to no badges / no patch links */ }
  await loadHeroIconSet();
  const editsByPatch = edits.edits || {};
  const patchLinks = buildPatchLinkMap(patches.patches);
  const indexEntry = (index.entries || []).find((e) => e.key === key) || null;

  const timeline = hero.timeline || [];
  const heroName = `${hero.names.cn || ""}${hero.names.cn && hero.names.en ? " / " : ""}${hero.names.en || ""}`.trim();
  const isHero = key === `hero::${slug}`;

  if (isHero) {
    // hero-overview meta reflects the standard-only surface (its entry cards
    // come from the standard-only entries_index)
    const stdTimeline = timeline.filter((e) => (e.mode || "standard") === "standard");
    const edited = stdTimeline.some((e) => editsByPatch[e.patch]);
    const dates = stdTimeline.map((e) => e.date).sort();
    const range = dates[0] !== dates[dates.length - 1]
      ? `${dates[0]} ~ ${dates[dates.length - 1]}` : dates[0];
    // merged rows on this page: the index carries the same number, so the hero
    // card and this meta line can never disagree
    const heroRows = mergeEntryRecords(stdTimeline, buildPairMap(patches.patches));
    const heroChanges = indexEntry && indexEntry.changes != null ? indexEntry.changes : heroRows.length;
    const heroTitle = entryDisplayName(indexEntry) || heroName || slug;
    document.getElementById("entry-name").textContent = heroTitle;
    setPageMeta(`${heroTitle} · 英雄 · 守望先锋词条`,
      `${heroTitle} 的全部词条与 ${heroChanges} 条更改记录。`);
    document.getElementById("entry-hero").innerHTML =
      `<span class="entry-hero-link"><a href="hero.html?slug=${encodeURIComponent(slug)}">${esc(heroName || slug)}</a>（全部词条总览）</span>`;
    document.getElementById("entry-meta").innerHTML = `
      <span class="badge dim dim-hero">英雄</span>
      <span class="badge hero-role">${esc(ROLE_LABEL[hero.role] || hero.role || "")}</span>
      ${edited ? `<span class="badge edited">官方事后编辑</span>` : ""}
      <span>${heroChanges} 条更改记录</span>
      <span>${esc(range)}</span>`;
    const body = document.getElementById("entry-body");
    body.textContent = "";
    let idx;
    try {
      idx = await fetchJSON("data/entries_index.json");
    } catch {
      document.getElementById("entry-hero").innerHTML += ` · <span class="meta">（词条索引缺失，无法列出全部词条）</span>`;
      return;
    }
    const cards = document.createElement("div");
    cards.className = "entry-grid hero-entry-grid";
    for (const e of idx.entries) {
      if (e.hero_slug === slug && e.dimension !== "hero") cards.appendChild(entryCard(e));
    }
    body.appendChild(cards);
    return;
  }

  const allRecords = timeline.filter((e) => key === `${slug}::${entryKey(e)}`);
  if (!allRecords.length) {
    document.getElementById("entry-name").textContent = "未找到该词条";
    return;
  }

  const dim = allRecords[0].dimension || (allRecords[0].kind === "perk" ? "perk" : "other");
  // canonical name from the index; the newest record is only a fallback (the
  // oldest one is the one with the 2016 spelling)
  const displayName = entryDisplayName(indexEntry) || entryTitle(allRecords[allRecords.length - 1]);
  document.getElementById("entry-name").textContent = displayName;
  setPageMeta(`${displayName} · ${heroName || slug} · 守望先锋词条`,
    `${heroName || slug} ${displayName} 的完整改动记录。`);
  const aliases = entryAliases(indexEntry);
  document.getElementById("entry-hero").innerHTML =
    `<span class="entry-hero-link"><a href="hero.html?slug=${encodeURIComponent(slug)}">${esc(heroName || slug)}</a>（全部词条）</span>`
    + (aliases.length ? `<span class="entry-aliases">别名：${aliases.map((a) => esc(a)).join("、")}</span>` : "");

  // default view is standard-only (special-mode records must not pollute the
  // entry history); the toggle or ?modes=all opt into them
  const body = document.getElementById("entry-body");
  body.textContent = "";
  let showAll = new URLSearchParams(location.search).get("modes") === "all";
  const toggle = document.createElement("label");
  toggle.className = "mode-toggle";
  toggle.innerHTML = `<input type="checkbox"${showAll ? " checked" : ""}> 包含非常规模式补丁（愚人节/实验/试玩等）`;
  toggle.querySelector("input").addEventListener("change", (ev) => {
    showAll = ev.target.checked;
    renderRecords();
  });
  body.appendChild(toggle);
  const valuesBox = document.createElement("div");
  valuesBox.id = "entry-values";
  body.appendChild(valuesBox);
  const recordsBox = document.createElement("div");
  recordsBox.id = "entry-records";
  body.appendChild(recordsBox);

  function renderRecords() {
    const records = allRecords.filter((e) => showAll || (e.mode || "standard") === "standard");
    // merge paired EN+CN records of the same change into one row (Chinese first)
    const rows = mergeEntryRecords(records, buildPairMap(patches.patches));
    const edited = records.some((e) => editsByPatch[e.patch]);
    const dates = records.map((e) => e.date).sort();
    const range = dates[0] !== dates[dates.length - 1]
      ? `${dates[0]} ~ ${dates[dates.length - 1]}` : dates[0];
    document.getElementById("entry-meta").innerHTML = `
      <span class="badge dim dim-${esc(dim)}">${DIM_LABEL[dim] || dim}</span>
      <span class="badge kind">${esc(kindLabel(allRecords[0].kind, dim))}</span>
      ${edited ? `<span class="badge edited">官方事后编辑</span>` : ""}
      <span>${rows.length} 条更改记录</span>
      <span>${esc(range)}</span>`;
    valuesBox.innerHTML = valueList(hero.values || {}, records[0] || allRecords[0]);
    recordsBox.textContent = "";
    const group = document.createElement("div");
    group.className = "timeline-group";
    const head = document.createElement("h2");
    head.textContent = "更改记录";
    group.appendChild(head);
    if (!rows.length) {
      const empty = document.createElement("p");
      empty.className = "sub";
      empty.textContent = "该词条无常规模式记录（可勾选上方查看非常规模式补丁）";
      group.appendChild(empty);
    } else {
      const list = document.createElement("div");
      for (const row of rows) {
        // merged rows carry the official-edit badges of BOTH site patches (deduped)
        const enEdits = row.en ? (editsByPatch[row.en.patch] || []) : [];
        const mergedEdits = enEdits.length
          ? [...(editsByPatch[row.m.patch] || []), ...enEdits]
              .filter((x, i, arr) => arr.findIndex((y) => y.ts === x.ts) === i)
          : (editsByPatch[row.m.patch] || []);
        list.appendChild(entryNode(row.m, {
          patchHref: patchLinks[row.m.patch] || "",
          edits: mergedEdits,
        }));
      }
      group.appendChild(list);
    }
    recordsBox.appendChild(group);
  }
  renderRecords();
}

/* ---------- patch detail (patch.html) ---------- */

// Content language of the patch currently rendered. Names are picked from that
// side even when the other side's name is present — an English patch page must
// not title a hero "血律" and a Chinese one must not title it "Doctrine".
let patchLang = "cn";

const ROLE_LABEL_EN = { tank: "Tank", damage: "Damage", support: "Support" };

function patchName(obj, cnKey, enKey) {
  if (!obj) return "";
  const cn = obj[cnKey];
  const en = obj[enKey];
  return patchLang === "en" ? (en || cn || "") : (cn || en || "");
}

function patchRoleLabel(role) {
  return (patchLang === "en" ? ROLE_LABEL_EN[role] : ROLE_LABEL[role]) || "";
}

function buildToc(entries) {
  const toc = document.getElementById("patch-toc");
  toc.replaceChildren();
  if (!entries.length) { toc.hidden = true; return; }
  toc.hidden = false;
  for (const e of entries) {
    if (!e.text) continue; // empty-titled blocks (rare) get no TOC link
    const a = document.createElement("a");
    a.href = "#" + e.id;
    a.textContent = e.text;
    if (e.level > 1) a.className = "toc-l2";
    toc.appendChild(a);
  }
  if (typeof IntersectionObserver === "undefined") return; // smoke shim / old browsers
  const io = new IntersectionObserver((items) => {
    for (const item of items) {
      if (!item.isIntersecting) continue;
      toc.querySelectorAll("a").forEach((a) =>
        a.classList.toggle("active", a.getAttribute("href") === "#" + item.target.id));
    }
  }, { rootMargin: "-5% 0px -85% 0px" });
  for (const e of entries) {
    const el = document.getElementById(e.id);
    if (el) io.observe(el);
  }
}

// OW1-era raw_text: inject hero portraits and ability icons beside matched
// names (case-sensitive whole-token, first occurrence per slug). Every text
// fragment is escaped; icon srcs are local slug-based paths only.
async function renderRawText(el, text) {
  let heroIdx, abilityMap;
  try {
    [heroIdx, abilityMap] = await Promise.all([
      fetchJSON("data/heroes_index.json"),
      fetchJSON("data/ability_map.json"),
    ]);
  } catch {
    el.textContent = text; // maps missing: plain text fallback
    return;
  }
  const heroBySlug = {};
  for (const h of heroIdx.heroes || []) heroBySlug[h.slug] = h;
  const candidates = [];
  for (const h of heroIdx.heroes || []) {
    candidates.push({ keys: new Set([h.en, deaccent(h.en)]), slug: h.slug, kind: "hero" });
  }
  for (const [name, slug] of Object.entries(LEGACY_ALIASES)) {
    candidates.push({ keys: new Set([name]), slug, kind: "hero" });
  }
  for (const [name, slug] of Object.entries(abilityMap.by_en || {})) {
    candidates.push({ keys: new Set([name, deaccent(name)]), slug, kind: "ability" });
  }

  const used = new Set();
  const matches = [];
  for (const cand of candidates) {
    for (const key of cand.keys) {
      const m = nameMatch(key, text);
      if (!m) continue;
      const mark = cand.kind + ":" + cand.slug;
      if (used.has(mark)) continue;
      used.add(mark);
      const ability = cand.kind === "ability" ? (abilityMap.abilities || {})[cand.slug] : null;
      matches.push({
        index: m.index, len: m.len, mark, kind: cand.kind, slug: cand.slug,
        heroSlug: cand.kind === "hero" ? cand.slug
          : (ability && ability.heroes && ability.heroes.length === 1 ? ability.heroes[0] : null),
        heroes: cand.kind === "ability" ? (ability && ability.heroes) || [] : null,
      });
      break; // one occurrence per candidate
    }
  }
  matches.sort((a, b) => a.index - b.index);
  let out = "";
  let pos = 0;
  let lastHero = "";
  for (const m of matches) {
    if (m.index < pos) continue; // overlapping match: keep the earlier one
    let hero = m.heroSlug;
    if (m.kind === "ability" && !hero) {
      if (!lastHero || !m.heroes.includes(lastHero)) continue; // ambiguous, no context
      hero = lastHero;
    }
    const alt = m.kind === "hero" ? (heroBySlug[m.slug]?.en || m.slug) : m.slug;
    const path = m.kind === "hero" ? heroIconPath(m.slug)
      : abilityIconPath(hero, m.slug);
    out += esc(text.slice(pos, m.index)) + iconImg(path, alt, "legacy-icon")
      + esc(text.slice(m.index, m.index + m.len));
    pos = m.index + m.len;
    if (m.kind === "hero" || m.heroSlug) lastHero = hero;
  }
  el.innerHTML = postProcess(out + esc(text.slice(pos)));
}

// {site}-YYYY-MM-DD-N -> data/patches/<site>/YYYY-MM-DD-N.json. Explicit regex
// instead of positional slicing: a malformed id must fail visibly, not silently
// request the wrong file.
function patchFileFor(patchId, site) {
  const m = /^[a-z]+-(\d{4}-\d{2}-\d{2})-(\d+)$/.exec(String(patchId || ""));
  return m ? `data/patches/${site}/${m[1]}-${m[2]}.json` : "";
}

function buildLangSwitch(patchId, langs, active) {
  const switcher = document.getElementById("lang-switch");
  if (!switcher) return;
  switcher.replaceChildren();
  for (const s of langs) {
    const a = document.createElement("a");
    a.className = `lang-btn ${s === active ? "active" : ""}`;
    a.href = `patch.html?id=${encodeURIComponent(patchId)}&lang=${s}`;
    a.textContent = SITE_LABEL[s];
    if (s === active) a.setAttribute("aria-current", "page");
    switcher.appendChild(a);
  }
}

function buildOfficialLinks(meta, sites) {
  const links = document.getElementById("patch-links");
  if (!links) return;
  links.replaceChildren();
  for (const s of sites) {
    const url = s === "en" ? meta.url_en : meta.url_cn;
    if (!url) continue;
    const a = document.createElement("a");
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = `${SITE_LABEL[s]}原文 ↗`;
    links.appendChild(a);
  }
}

async function initPatch() {
  const params = new URLSearchParams(location.search);
  const id = params.get("id");
  const lang = params.get("lang") === "en" ? "en" : "cn";
  if (!id) { location.href = "index.html"; return; }

  const index = await fetchJSON("data/patches_index.json");
  const meta = index.patches.find((p) => p.id === id);
  if (!meta) {
    document.getElementById("patch-title").textContent = "未找到该补丁";
    setPageMeta("未找到该补丁 · 守望先锋补丁归档");
    return;
  }

  const sites = meta.sites || [];
  const langs = sites.slice().sort((a, b) => (a === "cn" ? -1 : 1));
  const active = sites.includes(lang) ? lang : (langs[0] || "cn");
  patchLang = active;
  if (document.documentElement) {
    document.documentElement.lang = active === "en" ? "en" : "zh-CN";
  }

  // Header shell first: the language switch and the official links are built
  // before the archive file is requested, so a missing side still lets the
  // reader switch to the other language instead of being stuck.
  document.getElementById("patch-date").textContent = meta.date;
  document.getElementById("patch-sites").innerHTML =
    siteBadges(sites) + modeBadge(meta.mode) + categoryBadges(meta);
  document.getElementById("patch-title").textContent = meta.title_cn || meta.title_en || id;
  buildLangSwitch(id, langs, active);
  buildOfficialLinks(meta, sites);

  const titleOf = (patch) => (patch && patch.title) || meta.title_cn || meta.title_en || id;
  const setPatchMeta = (title) => setPageMeta(
    `${meta.date} · ${title} · 守望先锋补丁`,
    `${meta.date} 守望先锋补丁说明：${title}`);

  const patchId = active === "en" ? meta.patch_id_en : meta.patch_id_cn;
  const file = patchFileFor(patchId, active);
  let patch;
  try {
    if (!file) throw new Error(`无法识别的补丁编号：${patchId || "(缺失)"}`);
    patch = await fetchJSON(file);
  } catch {
    // index entry exists but the archived JSON is missing: render what we know
    // instead of leaving the page blank on an unhandled rejection
    const article = document.getElementById("patch-article");
    article.replaceChildren();
    const missing = document.createElement("p");
    missing.className = "text";
    missing.textContent = "该补丁内容暂缺（归档数据缺失或解析失败）。";
    article.appendChild(missing);
    buildToc([]);
    setPatchMeta(document.getElementById("patch-title").textContent);
    return;
  }

  document.getElementById("patch-title").textContent = patch.title;
  setPatchMeta(titleOf(patch));
  await loadHeroIconSet();

  // official post-publication edits badge
  let editsByPatch = {};
  try {
    editsByPatch = (await fetchJSON("data/official_edits.json")).edits || {};
  } catch { /* official_edits.json missing: skip badge */ }
  const editEvents = (editsByPatch[meta.patch_id_en] || []).concat(editsByPatch[meta.patch_id_cn] || []);
  if (editEvents.length) {
    const latest = editEvents.reduce((a, b) => ((b.ts || "") > (a.ts || "") ? b : a));
    const titles = editEvents.map((x) => (x.title || fmtLocalTs(x.ts) || "")).filter(Boolean).join("；");
    document.getElementById("patch-edits").innerHTML =
      `<span class="badge edited" title="${esc(titles)}">官方事后编辑 ${editEvents.length} 次${latest.ts ? `（最近 ${esc(fmtLocalTs(latest.ts))}）` : ""}</span>`;
  }

  const article = document.getElementById("patch-article");
  article.replaceChildren();
  const tocEntries = [];
  let secIdx = 0;
  for (const section of patch.sections || []) {
    const sec = document.createElement("section");
    sec.className = "timeline-group";
    const role = patchRoleLabel(section.role);
    const secTitle = `${section.title || ""}${role ? `（${role}）` : ""}`;
    if (secTitle) sec.innerHTML = `<h2 id="sec-${secIdx}">${esc(secTitle)}</h2>`;
    tocEntries.push({ id: `sec-${secIdx}`, text: secTitle, level: 1 });
    const body = document.createElement("div");
    if (section.description) {
      const d = document.createElement("div");
      d.className = "text desc";
      renderRich(d, section.description);
      body.appendChild(d);
    }
    if (section.dev) {
      const d = document.createElement("div");
      d.className = "text dev-note";
      renderRich(d, section.dev);
      body.appendChild(d);
    }
    for (const [mi, map] of (section.maps || []).entries()) {
      const mc = document.createElement("div");
      mc.className = "map-update";
      const mapTitle = [map.map_name, map.area].filter(Boolean).join(" ");
      if (mapTitle) {
        const t = document.createElement("div");
        t.className = "text map-update-name";
        t.innerHTML = `<strong>${esc(mapTitle)}</strong>`;
        mc.appendChild(t);
      }
      const cmp = document.createElement("div");
      cmp.className = "map-compare";
      const pairs = [["修改前", map.before, "before"], ["修改后", map.after, "after"]];
      for (const [label, src, side] of pairs) {
        if (!src) continue;
        const fig = document.createElement("figure");
        // map asset keys are patch/section/map scoped (a patch can hold several
        // map sections whose image indices restart at 0)
        fig.innerHTML = `<img src="assets/maps/${esc(patch.id)}/s${esc(secIdx)}/${esc(mi)}-${side}.png" alt="${esc(mapTitle || label)}" loading="lazy"><figcaption>${esc(label)}</figcaption>`;
        cmp.appendChild(fig);
      }
      mc.appendChild(cmp);
      body.appendChild(mc);
    }
    let heroN = 0;
    for (const hero of section.heroes || []) {
      const hb = heroBlock(hero);
      hb.id = `hero-${secIdx}-${heroN}`;
      tocEntries.push({
        id: hb.id, text: patchName(hero, "name_cn", "name_en") || hero.slug, level: 2,
      });
      body.appendChild(hb);
      heroN++;
    }
    let blkN = 0;
    for (const block of section.blocks || []) {
      const b = document.createElement("div");
      b.className = "entry";
      b.id = `blk-${secIdx}-${blkN}`;
      tocEntries.push({ id: b.id, text: block.title || "", level: 2 });
      const title = document.createElement("div");
      title.className = "text";
      title.innerHTML = `<strong>${esc(block.title || "")}</strong>`;
      b.appendChild(title);
      if (block.body) {
        const p = document.createElement("div");
        p.className = "text";
        renderRich(p, block.body);
        b.appendChild(p);
      }
      if (block.dev) {
        const p = document.createElement("div");
        p.className = "text dev-note";
        p.textContent = block.dev;
        b.appendChild(p);
      }
      body.appendChild(b);
      blkN++;
    }
    sec.appendChild(body);
    article.appendChild(sec);
    secIdx++;
  }
  buildToc(tocEntries);
  if (patch.raw_text) {
    // OW1-era pages degrade to a single structure-preserved text blob
    const rt = document.createElement("div");
    rt.className = "raw-text";
    article.appendChild(rt);
    await renderRawText(rt, patch.raw_text);
  }
}

function heroBlock(hero) {
  const block = document.createElement("div");
  block.className = "hero-block";
  const name = patchName(hero, "name_cn", "name_en") || hero.slug;
  block.innerHTML = `<h3 class="hero-block-name">${heroAvatar(hero.slug, name, "hero-avatar")}${esc(name)}</h3>`;
  if (hero.dev_note) {
    const d = document.createElement("div");
    d.className = "text en-text dev-note";
    d.textContent = hero.dev_note;
    block.appendChild(d);
  }
  for (const line of hero.general || []) {
    const text = typeof line === "string" ? line : (line.text_cn || line.text_en || "");
    if (!text) continue;
    const ul = document.createElement("ul");
    ul.className = "change-list";
    const li = document.createElement("li");
    li.innerHTML = numberify(esc(text));
    ul.appendChild(li);
    block.appendChild(ul);
  }
  for (const perk of hero.perks || []) {
    const p = document.createElement("div");
    p.className = "entry perk-block";
    const status = document.createElement("span");
    status.className = `perk-status ${esc(perk.status)}`;
    status.textContent = STATUS_LABEL[perk.status] || perk.status;
    const h = document.createElement("div");
    h.className = "text";
    h.innerHTML = `<strong>${esc(patchName(perk, "name_cn", "name_en") || "威能")}</strong> `;
    h.appendChild(status);
    p.appendChild(h);
    const lines = (perk.lines_cn && perk.lines_cn.length ? perk.lines_cn : perk.lines_en) || [];
    if (lines.length) {
      const ul = document.createElement("ul");
      ul.className = "change-list";
      for (const line of lines) {
        const li = document.createElement("li");
        li.innerHTML = numberify(esc(line));
        ul.appendChild(li);
      }
      p.appendChild(ul);
    }
    if (perk.lines_cn?.length && perk.lines_en?.length) {
      const d = document.createElement("div");
      d.className = "text en-text";
      d.textContent = perk.lines_en.join(" / ");
      p.appendChild(d);
    }
    block.appendChild(p);
  }
  for (const item of hero.stadium_items || []) {
    const p = document.createElement("div");
    p.className = "entry stadium-item";
    const status = document.createElement("span");
    status.className = `perk-status ${esc(item.status)}`;
    status.textContent = STATUS_LABEL[item.status] || item.status;
    const h = document.createElement("div");
    h.className = "text";
    const itemName = patchName(item, "name_cn", "name_en");
    h.innerHTML = `<strong>${esc(itemName)}</strong> `;
    if (item.rarity) {
      const r = document.createElement("span");
      r.className = `item-badge rarity-${esc(String(item.rarity).toLowerCase())}`;
      r.textContent = item.rarity;
      h.appendChild(r);
    }
    if (item.kind && ITEM_KIND_LABEL[item.kind]) {
      const k = document.createElement("span");
      k.className = "item-badge kind";
      k.textContent = ITEM_KIND_LABEL[item.kind];
      h.appendChild(k);
    }
    h.appendChild(status);
    p.appendChild(h);
    const lines = (item.lines_cn && item.lines_cn.length ? item.lines_cn : item.lines_en) || [];
    if (lines.length) {
      const ul = document.createElement("ul");
      ul.className = "change-list";
      for (const line of lines) {
        const li = document.createElement("li");
        li.innerHTML = numberify(esc(line));
        ul.appendChild(li);
      }
      p.appendChild(ul);
    }
    block.appendChild(p);
  }
  for (const ability of hero.abilities || []) {
    const a = document.createElement("div");
    a.className = "entry";
    const aname = patchName(ability, "name_cn", "name_en");
    a.innerHTML = `<div class="text"><strong>${ability.slug && hero.slug ? iconImg(abilityIconPath(hero.slug, ability.slug), aname, "ability-icon") : ""}${esc(aname)}</strong></div>`;
    const changes = ability.changes || [];
    if (changes.length) {
      const ul = document.createElement("ul");
      ul.className = "change-list";
      for (const change of changes) {
        const li = document.createElement("li");
        li.innerHTML = numberify(esc(change.text_cn || change.text_en || ""));
        ul.appendChild(li);
      }
      a.appendChild(ul);
    }
    block.appendChild(a);
  }
  return block;
}

/* ---------- page bootstrap ---------- */

const PAGE_INIT = {
  index: initIndex, entries: initEntries, entry: initEntry, hero: initHero, patch: initPatch,
};

// A failed data request must never leave a blank page: render the reason plus a
// retry affordance into <main>. (initIndex/initPatch used to reject unhandled.)
function mountLoadError(err) {
  const host = (document.querySelector && document.querySelector("main")) || document.body;
  if (!host) return;
  host.textContent = "";
  const box = document.createElement("div");
  box.className = "load-error";
  box.textContent = `数据加载失败：${err && err.message ? err.message : String(err)}`;
  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = "jump-btn";
  retry.textContent = "重试";
  retry.addEventListener("click", () => location.reload());
  host.appendChild(box);
  host.appendChild(retry);
}

function runPage(fn) {
  Promise.resolve().then(fn).catch(mountLoadError);
}

// one capture-phase listener replaces the per-image inline onerror handlers
// (inline handlers cannot coexist with a 'self'-only script CSP)
function installImageFallback() {
  if (!document.addEventListener) return;
  document.addEventListener("error", (ev) => {
    const target = ev.target;
    if (target && target.tagName === "IMG") target.style.display = "none";
  }, true);
}

installImageFallback();

// <body data-page="…"> picks the page initializer (replaces the inline
// <script>initXxx()</script> call each HTML page used to carry)
const pageName = document.body && document.body.dataset && document.body.dataset.page;
if (pageName && PAGE_INIT[pageName]) runPage(PAGE_INIT[pageName]);
