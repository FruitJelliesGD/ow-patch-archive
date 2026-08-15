/* Shared helpers for the OW patch timeline site. */
"use strict";

const ROLE_LABEL = { tank: "重装", damage: "输出", support: "支援" };
const KIND_LABEL = { ability: "技能改动", perk: "威能改动", general: "其他改动" };
const SITE_LABEL = { en: "英文站", cn: "中文站" };
const STATUS_LABEL = {
  added: "新增", removed: "移除", reworked: "重做", moved: "变更", changed: "调整",
};

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

/* ---------- index page ---------- */

async function initIndex() {
  const data = await fetchJSON("data/heroes_index.json");
  document.getElementById("updated").textContent = (data.updated || "").slice(0, 16) || "-";
  const roles = { tank: [], damage: [], support: [], unknown: [] };
  for (const h of data.heroes) roles[h.role]?.push(h) ?? roles.unknown.push(h);

  const container = document.getElementById("roles");
  for (const [role, heroes] of Object.entries(roles)) {
    if (!heroes.length) continue;
    const section = document.createElement("section");
    section.className = `role-${role}`;
    section.innerHTML = `<h2 class="role-title">${esc(ROLE_LABEL[role] || role)}</h2><div class="hero-grid"></div>`;
    const grid = section.querySelector(".hero-grid");
    for (const h of heroes) {
      grid.appendChild(heroCard(h));
    }
    container.appendChild(section);
  }

  document.getElementById("search").addEventListener("input", (e) => {
    const q = (e.target.value || "").trim().toLowerCase();
    document.querySelectorAll(".hero-card").forEach((card) => {
      card.style.display = card.dataset.search.includes(q) ? "" : "none";
    });
  });
}

function heroCard(h) {
  const a = document.createElement("a");
  a.className = "hero-card";
  a.href = `hero.html?slug=${encodeURIComponent(h.slug)}`;
  a.dataset.search = [h.slug, h.en, h.cn].join(" ").toLowerCase();
  const count = h.count ?? "";
  a.innerHTML = `<span class="count">${esc(count)}</span>
    <div class="cn">${esc(h.cn || h.en)}</div>
    <div class="en">${esc(h.en || "")}</div>`;
  return a;
}

/* ---------- hero page ---------- */

async function initHero() {
  const slug = new URLSearchParams(location.search).get("slug");
  if (!slug) { location.href = "index.html"; return; }
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
  const groups = new Map(); // key -> {title, entries}
  for (const e of timeline) {
    let key, title;
    if (e.kind === "ability") {
      key = `ability::${e.ability_slug || e.ability_en || e.ability_cn}`;
      title = `${e.ability_cn || e.ability_en || "-"} / ${e.ability_en || ""}`.replace(" / ", " · ").replace(/^· | · $/g, "").trim();
      if (e.ability_en && e.ability_cn) title = `${e.ability_cn} / ${e.ability_en}`;
    } else if (e.kind === "perk") {
      key = `perk::${e.perk_cn || e.perk_en}`;
      title = `${e.perk_cn || ""} ${e.perk_en ? `(${e.perk_en})` : ""}`.trim() || "-";
    } else {
      key = "general";
      title = "其他改动";
    }
    if (!groups.has(key)) groups.set(key, { title, entries: [] });
    groups.get(key).entries.push(e);
  }

  const main = document.getElementById("timeline");
  const count = document.createElement("p");
  count.className = "sub";
  count.textContent = `共 ${timeline.length} 条记录`;
  main.appendChild(count);

  for (const { title, entries } of groups.values()) {
    const group = document.createElement("section");
    group.className = "timeline-group";
    group.innerHTML = `<h2>${esc(title)}</h2>`;
    const body = document.createElement("div");
    for (const e of entries) body.appendChild(entryNode(e));
    group.appendChild(body);
    main.appendChild(group);
  }
}

function entryNode(e) {
  const div = document.createElement("div");
  div.className = "entry";
  const head = document.createElement("div");
  head.className = "head";
  head.innerHTML = `
    <span class="badge ${esc(e.site)}">${SITE_LABEL[e.site]}</span>
    <span class="badge kind">${KIND_LABEL[e.kind]}</span>
    <span>${esc(e.date)}</span>
    <span class="patch-link">${e.patch_title ? esc(e.patch_title) : esc(e.patch)}</span>`;
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
  }
  if (e.url) {
    const link = document.createElement("div");
    link.className = "patch-link";
    link.innerHTML = `<a href="${esc(e.url)}" target="_blank" rel="noopener">查看官方补丁原文 ↗</a>`;
    div.appendChild(link);
  }
  return div;
}

function numberify(html) {
  return html.replace(/(\d+(?:\.\d+)?\s*→\s*\d+(?:\.\d+)?)/g, '<span class="num">$1</span>');
}
