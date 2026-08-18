/* Shared helpers for the OW patch archive site (time browser + hero query). */
"use strict";

const ROLE_LABEL = { tank: "重装", damage: "输出", support: "支援" };
const KIND_LABEL = { ability: "技能改动", perk: "威能改动", general: "其他改动" };
const DIM_LABEL = { weapon: "武器", ability: "技能", perk: "威能", hero_attr: "英雄属性", hero: "英雄", other: "其他" };
const ATTR_LABEL = {
  health: "生命值", ultimate_cost: "终极技能消耗", move_speed: "移动速度",
  base_stat: "基础属性", other: "其他",
};
const SITE_LABEL = { en: "英文站", cn: "中文站" };
const STATUS_LABEL = {
  added: "新增", removed: "移除", reworked: "重做", moved: "变更", changed: "调整",
};
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

function numberify(html) {
  return html.replace(/(\d+(?:\.\d+)?\s*→\s*\d+(?:\.\d+)?)/g, '<span class="num">$1</span>');
}

function siteBadges(sites) {
  return (sites || []).map((s) => `<span class="badge ${esc(s)}">${SITE_LABEL[s] || s}</span>`).join(" ");
}

/* ---------- time browser (index.html) ---------- */

async function initIndex() {
  const data = await fetchJSON("data/patches_index.json");
  document.getElementById("updated").textContent = (data.updated || "").slice(0, 16) || "-";
  const patches = data.patches || [];

  // group by year -> month
  const years = new Map();
  for (const p of patches) {
    const [y, m] = p.date.split("-");
    if (!years.has(y)) years.set(y, new Map());
    const months = years.get(y);
    if (!months.has(m)) months.set(m, []);
    months.get(m).push(p);
  }

  const container = document.getElementById("patch-list");
  for (const [year, months] of [...years.entries()].sort((a, b) => b[0].localeCompare(a[0]))) {
    const yearSection = document.createElement("section");
    yearSection.className = "year";
    yearSection.innerHTML = `<h2 class="year-title">${esc(year)}</h2>`;
    for (const [month, entries] of [...months.entries()].sort((a, b) => b[0].localeCompare(a[0]))) {
      const monthSection = document.createElement("div");
      monthSection.className = "month";
      monthSection.innerHTML = `<h3 class="month-title">${MONTH_LABEL[Number(month)]}</h3>`;
      const list = document.createElement("div");
      list.className = "patch-list";
      for (const p of entries) {
        const site = p.sites.includes("cn") ? "cn" : "en";
        const title = site === "cn" ? (p.title_cn || p.title_en) : (p.title_en || p.title_cn);
        const a = document.createElement("a");
        a.className = "patch-entry";
        a.href = `patch.html?id=${encodeURIComponent(p.id)}&lang=${site}`;
        a.innerHTML = `
          <span class="patch-entry-date">${esc(p.date)}</span>
          ${siteBadges(p.sites)}
          <span class="patch-entry-title">${esc(title || p.id)}</span>`;
        list.appendChild(a);
      }
      monthSection.appendChild(list);
      yearSection.appendChild(monthSection);
    }
    container.appendChild(yearSection);
  }
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
  const groups = new Map(); // key -> {dim, title, entries}
  for (const e of timeline) {
    const key = entryKey(e);
    const dim = e.dimension || (e.kind === "perk" ? "perk" : "other");
    if (!groups.has(key)) groups.set(key, { dim, title: entryTitle(e), entries: [] });
    groups.get(key).entries.push(e);
  }

  const DIM_ORDER = ["weapon", "ability", "perk", "hero_attr", "other"];
  const main = document.getElementById("timeline");
  const count = document.createElement("p");
  count.className = "sub";
  count.textContent = `共 ${timeline.length} 条记录`;
  main.appendChild(count);

  for (const dim of DIM_ORDER) {
    const dimEntries = [...groups.values()].filter((g) => g.dim === dim);
    if (!dimEntries.length) continue;
    const dimSection = document.createElement("section");
    dimSection.className = "dim-section";
    dimSection.innerHTML = `<h2 class="dim-title"><span class="badge dim dim-${esc(dim)}">${DIM_LABEL[dim]}</span></h2>`;
    for (const { title, entries } of dimEntries) {
      const group = document.createElement("section");
      group.className = "timeline-group";
      group.innerHTML = `<h2>${esc(title)}${valueChips(values, entries[0])}</h2>`;
      const body = document.createElement("div");
      for (const e of entries) body.appendChild(entryNode(e));
      group.appendChild(body);
      dimSection.appendChild(group);
    }
    main.appendChild(dimSection);
  }
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
    ? `<span class="badge edited" title="${esc(edits.map((x) => (x.ts || "").slice(0, 16) + (x.title ? " · " + x.title : "")).join("；"))}">官方事后编辑</span>`
    : "";
  head.innerHTML = `
    <span class="badge ${esc(e.site)}">${SITE_LABEL[e.site]}</span>
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
    const edited = timeline.some((e) => editsByPatch[e.patch]);
    const dates = timeline.map((e) => e.date).sort();
    const range = dates[0] !== dates[dates.length - 1]
      ? `${dates[0]} ~ ${dates[dates.length - 1]}` : dates[0];
    document.getElementById("entry-name").textContent = heroName || slug;
    document.getElementById("entry-hero").innerHTML =
      `<span class="entry-hero-link"><a href="hero.html?slug=${encodeURIComponent(slug)}">${esc(heroName || slug)}</a>（全部词条总览）</span>`;
    document.getElementById("entry-meta").innerHTML = `
      <span class="badge dim dim-hero">英雄</span>
      <span class="badge hero-role">${esc(ROLE_LABEL[hero.role] || hero.role || "")}</span>
      ${edited ? `<span class="badge edited">官方事后编辑</span>` : ""}
      <span>${timeline.length} 条更改记录</span>
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

  const records = timeline.filter((e) => key === `${slug}::${entryKey(e)}`);
  if (!records.length) {
    document.getElementById("entry-name").textContent = "未找到该词条";
    return;
  }

  const dim = records[0].dimension || (records[0].kind === "perk" ? "perk" : "other");
  document.getElementById("entry-name").textContent = entryTitle(records[0]);
  document.getElementById("entry-hero").innerHTML =
    `<span class="entry-hero-link"><a href="hero.html?slug=${encodeURIComponent(slug)}">${esc(heroName || slug)}</a>（全部词条）</span>`;

  const edited = records.some((e) => editsByPatch[e.patch]);
  const dates = records.map((e) => e.date).sort();
  const range = dates[0] !== dates[dates.length - 1]
    ? `${dates[0]} ~ ${dates[dates.length - 1]}` : dates[0];
  document.getElementById("entry-meta").innerHTML = `
    <span class="badge dim dim-${esc(dim)}">${DIM_LABEL[dim] || dim}</span>
    <span class="badge kind">${KIND_LABEL[records[0].kind] || ""}</span>
    ${edited ? `<span class="badge edited">官方事后编辑</span>` : ""}
    <span>${records.length} 条更改记录</span>
    <span>${esc(range)}</span>`;

  const body = document.getElementById("entry-body");
  body.innerHTML = valueList(hero.values || {}, records[0]);
  const group = document.createElement("div");
  group.className = "timeline-group";
  const head = document.createElement("h2");
  head.textContent = "更改记录";
  group.appendChild(head);
  const list = document.createElement("div");
  for (const e of records) {
    list.appendChild(entryNode(e, {
      patchHref: patchLinks[e.patch] || "",
      edits: editsByPatch[e.patch] || [],
    }));
  }
  group.appendChild(list);
  body.appendChild(group);
}

/* ---------- patch detail (patch.html) ---------- */

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
  document.getElementById("patch-sites").innerHTML = siteBadges(sites);
  document.getElementById("patch-title").textContent = patch.title;

  // official post-publication edits badge
  let editsByPatch = {};
  try {
    editsByPatch = (await fetchJSON("data/official_edits.json")).edits || {};
  } catch { /* official_edits.json missing: skip badge */ }
  const editEvents = (editsByPatch[meta.patch_id_en] || []).concat(editsByPatch[meta.patch_id_cn] || []);
  if (editEvents.length) {
    const latest = editEvents.reduce((a, b) => ((b.ts || "") > (a.ts || "") ? b : a));
    const titles = editEvents.map((x) => (x.title || x.ts || "")).filter(Boolean).join("；");
    document.getElementById("patch-edits").innerHTML =
      `<span class="badge edited" title="${esc(titles)}">官方事后编辑 ${editEvents.length} 次${latest.ts ? `（最近 ${esc(latest.ts.slice(0, 16))}）` : ""}</span>`;
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

  const main = document.getElementById("patch-body");
  for (const section of patch.sections || []) {
    const sec = document.createElement("section");
    sec.className = "timeline-group";
    const role = ROLE_LABEL[section.role] || "";
    sec.innerHTML = `<h2>${esc(section.title || "")}${role ? `（${role}）` : ""}</h2>`;
    const body = document.createElement("div");
    if (section.description) {
      const d = document.createElement("div");
      d.className = "text";
      d.textContent = section.description;
      body.appendChild(d);
    }
    for (const hero of section.heroes || []) {
      body.appendChild(heroBlock(hero));
    }
    for (const block of section.blocks || []) {
      const b = document.createElement("div");
      b.className = "entry";
      const title = document.createElement("div");
      title.className = "text";
      title.innerHTML = `<strong>${esc(block.title || "")}</strong>`;
      b.appendChild(title);
      if (block.body) {
        const p = document.createElement("div");
        p.className = "text";
        p.textContent = block.body;
        b.appendChild(p);
      }
      if (block.dev) {
        const p = document.createElement("div");
        p.className = "text en-text";
        p.textContent = block.dev;
        b.appendChild(p);
      }
      body.appendChild(b);
    }
    sec.appendChild(body);
    main.appendChild(sec);
  }
}

function heroBlock(hero) {
  const block = document.createElement("div");
  block.className = "hero-block";
  const name = hero.name_cn || hero.name_en || hero.slug;
  block.innerHTML = `<h3 class="hero-block-name">${esc(name)}</h3>`;
  if (hero.dev_note) {
    const d = document.createElement("div");
    d.className = "text en-text";
    d.textContent = hero.dev_note;
    block.appendChild(d);
  }
  for (const line of hero.general || []) {
    const d = document.createElement("div");
    d.className = "text";
    d.textContent = typeof line === "string" ? line : (line.text_cn || line.text_en || "");
    block.appendChild(d);
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
    for (const line of lines) {
      const d = document.createElement("div");
      d.className = "text";
      d.textContent = line;
      p.appendChild(d);
    }
    if (perk.lines_cn?.length && perk.lines_en?.length) {
      const d = document.createElement("div");
      d.className = "text en-text";
      d.textContent = perk.lines_en.join(" / ");
      p.appendChild(d);
    }
    block.appendChild(p);
  }
  for (const ability of hero.abilities || []) {
    const a = document.createElement("div");
    a.className = "entry";
    a.innerHTML = `<div class="text"><strong>${esc(ability.name_cn || ability.name_en || "")}</strong></div>`;
    for (const change of ability.changes || []) {
      const d = document.createElement("div");
      d.className = "text";
      d.innerHTML = numberify(esc(change.text_cn || change.text_en || ""));
      a.appendChild(d);
    }
    block.appendChild(a);
  }
  return block;
}
