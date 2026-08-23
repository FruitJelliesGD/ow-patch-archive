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
  hero_changes: "英雄改动",
};
const CATEGORY_ORDER = [
  "quick_play_hacked", "april_fools", "experiment_6v6", "hero_trial", "ptr",
  "community_created", "event", "season", "new_hero", "new_map",
  "stadium", "arcade", "workshop", "owl",
];
const MONTH_LABEL = ["", "1月", "2月", "3月", "4月", "5月", "6月",
  "7月", "8月", "9月", "10月", "11月", "12月"];

async function fetchJSON(path) {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`failed to load ${path}: ${resp.status}`);
  return resp.json();
}

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
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
    if (!/^https?:\/\//i.test(url)) return m;
    if (pre.startsWith("!")) {
      return `<img src="${url}" alt="${alt || ""}" loading="lazy" onerror="this.style.display='none'">`;
    }
    return `<a href="${url}" target="_blank" rel="noopener">${text}</a>`;
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

function iconImg(path, alt, cls) {
  return `<img class="${esc(cls || "")}" src="${esc(path)}" alt="${esc(alt || "")}" loading="lazy" onerror="this.style.display='none'">`;
}

function heroIconPath(slug) {
  return `assets/icons/heroes/${esc(slug)}.png`;
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

// Sticky year/month jump bar: year select repopulates the month select with
// months that actually contain patches; the button smooth-scrolls to the
// matching year/month anchor. Built with createElement/appendChild only so
// the smoke DOM shim can exercise it.
function buildJumpBar(years) {
  const bar = document.getElementById("jump-bar");
  const hint = document.createElement("span");
  hint.className = "jump-hint";
  hint.textContent = "跳转到：";
  const yearSel = document.createElement("select");
  yearSel.id = "jump-year";
  yearSel.title = "选择年份";
  const monthSel = document.createElement("select");
  monthSel.id = "jump-month";
  monthSel.title = "选择月份";
  const btn = document.createElement("button");
  btn.className = "jump-btn";
  btn.textContent = "跳转";
  bar.appendChild(hint);
  bar.appendChild(yearSel);
  bar.appendChild(monthSel);
  bar.appendChild(btn);

  const yearList = [...years.keys()].sort((a, b) => b.localeCompare(a));
  for (const y of yearList) {
    const opt = document.createElement("option");
    opt.value = y;
    opt.textContent = `${y} 年`;
    yearSel.appendChild(opt);
  }
  let selYear = yearList[0];

  function fillMonths() {
    monthSel.replaceChildren();
    const months = [...(years.get(selYear) || new Map()).keys()].sort((a, b) => b.localeCompare(a));
    for (const m of months) {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = MONTH_LABEL[Number(m)];
      monthSel.appendChild(opt);
    }
  }

  yearSel.addEventListener("change", () => {
    selYear = yearSel.value;
    fillMonths();
  });
  btn.addEventListener("click", () => {
    document.getElementById(`year-${selYear}-month-${monthSel.value}`)
      ?.scrollIntoView?.({ behavior: "smooth" });
  });
  fillMonths();
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
        const title = site === "cn" ? (p.title_cn || p.title_en) : (p.title_en || p.title_cn);
        const firstSection = site === "cn"
          ? (p.first_section_cn || p.first_section_en)
          : (p.first_section_en || p.first_section_cn);
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
          ${firstSection ? `<span class="badge section" title="${esc(firstSection)}">${esc(firstSection)}</span>` : ""}
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
  const allBtn = document.createElement("button");
  allBtn.className = "chip active";
  allBtn.dataset.cat = "";
  allBtn.textContent = "全部";
  allBtn.addEventListener("click", () => toggleCat(""));
  chips.appendChild(allBtn);
  for (const key of CATEGORY_ORDER) {
    if (!present.has(key)) continue;
    const b = document.createElement("button");
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
}

function syncChips() {
  const chips = document.getElementById("cat-chips");
  if (!chips) return;
  for (const btn of chips.children) {
    const key = btn.dataset.cat || "";
    const active = key === "" ? filter.selected.size === 0 : filter.selected.has(key);
    btn.className = "chip" + (active ? " active" : "");
  }
}

// smoke-test hook: same semantics as the chips, callable directly
function setFilter(keys) {
  filter.selected = new Set((keys || []).filter((k) => CATEGORY_LABEL[k]));
  syncChips();
  renderTimeBrowser(allPatches, filterMatches);
}

function getFilter() {
  return [...filter.selected];
}

async function initIndex() {
  const data = await fetchJSON("data/patches_index.json");
  document.getElementById("updated").textContent = fmtLocalTs(data.updated) || "-";
  allPatches = data.patches || [];

  // ?cat=a,b seeds the initial filter (smoke-testable initial state; chip
  // clicks stay local state, the URL is not rewritten)
  const q = new URLSearchParams(location.search).get("cat");
  if (q) {
    for (const k of q.split(",")) {
      if (CATEGORY_LABEL[k]) filter.selected.add(k);
    }
  }

  buildJumpBar(groupByYearMonth(allPatches));
  buildCategoryChips(allPatches);
  renderTimeBrowser(allPatches, filterMatches);
}

/* ---------- entry search (entries.html) ---------- */

const ENTRY_DIM_ORDER = ["weapon", "ability", "perk", "hero_attr", "hero"];

async function initEntries() {
  let data;
  try {
    data = await fetchJSON("data/entries_index.json");
  } catch {
    document.getElementById("result-count").textContent = "词条索引加载失败";
    return;
  }
  const all = data.entries || [];

  const filters = document.getElementById("filters");
  const chips = [["", "全部"], ...ENTRY_DIM_ORDER.map((d) => [d, DIM_LABEL[d]])];
  for (const [dim, label] of chips) {
    const b = document.createElement("button");
    b.className = `chip ${dim === "" ? "active" : ""}`;
    b.textContent = label;
    b.dataset.dim = dim;
    filters.appendChild(b);
  }

  const state = { q: "", dim: "" };
  const render = () => {
    const q = state.q;
    const results = all.filter((e) => {
      if (state.dim && e.dimension !== state.dim) return false;
      if (!q) return true;
      const hay = [e.name_cn, e.name_en, e.slug, e.hero_cn, e.hero_en, e.hero_slug]
        .concat(e.variants || []).filter(Boolean).join(" ").toLowerCase();
      return hay.includes(q);
    });
    const count = document.getElementById("result-count");
    count.textContent = `共 ${results.length} / ${all.length} 个词条`;
    const grid = document.getElementById("results");
    grid.textContent = "";
    for (const e of results) grid.appendChild(entryCard(e));
  };

  document.getElementById("search").addEventListener("input", (ev) => {
    state.q = (ev.target.value || "").trim().toLowerCase();
    render();
  });
  filters.addEventListener("click", (ev) => {
    const chip = ev.target.closest?.(".chip");
    if (!chip) return;
    state.dim = chip.dataset.dim || "";
    filters.querySelectorAll(".chip").forEach((c) => c.classList.toggle("active", c === chip));
    render();
  });
  render();
}

function entryCard(e) {
  const a = document.createElement("a");
  a.className = "entry-card";
  a.href = `entry.html?hero=${encodeURIComponent(e.hero_slug)}&key=${encodeURIComponent(e.key)}`;
  const meta = [
    `<span class="badge dim dim-${esc(e.dimension)}">${DIM_LABEL[e.dimension] || e.dimension}</span>`,
    `<span class="badge hero-role">${esc(ROLE_LABEL[e.hero_role] || e.hero_role || "")}</span>`,
    e.edited ? `<span class="badge edited">官方事后编辑</span>` : "",
  ].filter(Boolean).join(" ");
  const range = e.first_date && e.last_date && e.first_date !== e.last_date
    ? `${esc(e.first_date)} ~ ${esc(e.last_date)}` : esc(e.first_date || e.last_date || "");
  a.innerHTML = `
    <div class="card-top">${meta}</div>
    <div class="cn">${esc(e.name_cn || e.name_en || e.key)}${e.name_cn && e.name_en && e.name_cn !== e.name_en ? ` / ${esc(e.name_en)}` : ""}</div>
    <div class="en">${esc(e.hero_cn || e.hero_en || "")}</div>
    <div class="card-meta">${e.count} 条记录${range ? ` · ${range}` : ""}</div>`;
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

/* ---------- EN/CN record merging (entry + hero pages) ---------- */

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
  // pairing data is auxiliary: if it is missing the page degrades to unmerged rows
  let pairMap = {};
  try {
    pairMap = buildPairMap((await fetchJSON("data/patches_index.json")).patches);
  } catch { /* no pairing data: keep single-site rows */ }

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
      if (!groups.has(key)) groups.set(key, { dim, title: entryTitle(e), entries: [] });
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
        for (const row of entries) body.appendChild(entryNode(row.m));
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
    <span class="badge kind">${KIND_LABEL[e.kind]}</span>
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

  let hero;
  try {
    hero = await fetchJSON(`data/heroes/${encodeURIComponent(slug)}.json`);
  } catch {
    document.getElementById("entry-name").textContent = "未找到该词条";
    return;
  }
  let edits = { edits: {} };
  let patches = { patches: [] };
  try {
    [edits, patches] = await Promise.all([
      fetchJSON("data/official_edits.json"),
      fetchJSON("data/patches_index.json"),
    ]);
  } catch { /* auxiliary data missing: degrade to no badges / no patch links */ }
  const editsByPatch = edits.edits || {};
  const patchLinks = {};
  for (const p of patches.patches || []) {
    if (p.patch_id_en) patchLinks[p.patch_id_en] = `patch.html?id=${encodeURIComponent(p.id)}&lang=en`;
    if (p.patch_id_cn) patchLinks[p.patch_id_cn] = `patch.html?id=${encodeURIComponent(p.id)}&lang=cn`;
  }

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
    // count merged EN+CN pairs as one change, consistent with the entry pages
    const heroRows = mergeEntryRecords(stdTimeline, buildPairMap(patches.patches));
    document.getElementById("entry-name").textContent = heroName || slug;
    document.getElementById("entry-hero").innerHTML =
      `<span class="entry-hero-link"><a href="hero.html?slug=${encodeURIComponent(slug)}">${esc(heroName || slug)}</a>（全部词条总览）</span>`;
    document.getElementById("entry-meta").innerHTML = `
      <span class="badge dim dim-hero">英雄</span>
      <span class="badge hero-role">${esc(ROLE_LABEL[hero.role] || hero.role || "")}</span>
      ${edited ? `<span class="badge edited">官方事后编辑</span>` : ""}
      <span>${heroRows.length} 条更改记录</span>
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
  document.getElementById("entry-name").textContent = entryTitle(allRecords[0]);
  document.getElementById("entry-hero").innerHTML =
    `<span class="entry-hero-link"><a href="hero.html?slug=${encodeURIComponent(slug)}">${esc(heroName || slug)}</a>（全部词条）</span>`;

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
      <span class="badge kind">${KIND_LABEL[allRecords[0].kind] || ""}</span>
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

async function initPatch() {
  const params = new URLSearchParams(location.search);
  const id = params.get("id");
  const lang = params.get("lang") === "en" ? "en" : "cn";
  if (!id) { location.href = "index.html"; return; }

  const index = await fetchJSON("data/patches_index.json");
  const meta = index.patches.find((p) => p.id === id);
  if (!meta) {
    document.getElementById("patch-title").textContent = "未找到该补丁";
    return;
  }

  const sites = meta.sites || [];
  const langs = sites.slice().sort((a, b) => (a === "cn" ? -1 : 1));
  const active = sites.includes(lang) ? lang : langs[0];
  const patchId = active === "en" ? meta.patch_id_en : meta.patch_id_cn;
  const parts = patchId.split("-");
  const file = `data/patches/${active}/${parts.slice(1, 4).join("-")}-${parts[4]}.json`;
  const patch = await fetchJSON(file);

  document.getElementById("patch-date").textContent = meta.date;
  document.getElementById("patch-sites").innerHTML = siteBadges(sites) + modeBadge(meta.mode) + categoryBadges(meta);
  document.getElementById("patch-title").textContent = patch.title;

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

  // language switch
  const switcher = document.getElementById("lang-switch");
  for (const s of langs) {
    const a = document.createElement("a");
    a.className = `lang-btn ${s === active ? "active" : ""}`;
    a.href = `patch.html?id=${encodeURIComponent(id)}&lang=${s}`;
    a.textContent = SITE_LABEL[s];
    switcher.appendChild(a);
  }
  const links = document.getElementById("patch-links");
  for (const s of sites) {
    const url = s === "en" ? meta.url_en : meta.url_cn;
    if (url) {
      const a = document.createElement("a");
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = `${SITE_LABEL[s]}原文 ↗`;
      links.appendChild(a);
    }
  }

  const article = document.getElementById("patch-article");
  article.replaceChildren();
  const tocEntries = [];
  let secIdx = 0;
  for (const section of patch.sections || []) {
    const sec = document.createElement("section");
    sec.className = "timeline-group";
    const role = ROLE_LABEL[section.role] || "";
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
        fig.innerHTML = `<img src="assets/maps/${esc(patch.id)}/s${esc(secIdx)}/${esc(mi)}-${side}.png" alt="${esc(mapTitle || label)}" loading="lazy" onerror="this.style.display='none'"><figcaption>${esc(label)}</figcaption>`;
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
        id: hb.id, text: hero.name_cn || hero.name_en || hero.slug, level: 2,
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
  const name = hero.name_cn || hero.name_en || hero.slug;
  block.innerHTML = `<h3 class="hero-block-name">${hero.slug ? iconImg(heroIconPath(hero.slug), name, "hero-avatar") : ""}${esc(name)}</h3>`;
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
    h.innerHTML = `<strong>${esc(perk.name_cn || perk.name_en || "威能")}</strong> `;
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
    const itemName = item.name_cn || item.name_en || "";
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
    const aname = ability.name_cn || ability.name_en || "";
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
