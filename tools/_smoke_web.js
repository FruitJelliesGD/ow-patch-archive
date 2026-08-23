/* Headless smoke test: run the site's init functions against real data with a
 * minimal DOM shim, asserting rendered structure (grouping, patch counts,
 * entry search, entry detail, official-edit badges). */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const appJs = fs.readFileSync(path.join(ROOT, "web", "app.js"), "utf-8");

function makeEl(tag) {
  return {
    tagName: tag, children: [], _html: "", dataset: {}, style: {},
    className: "", id: "", href: "", target: "", rel: "", hidden: false,
    appendChild(c) { this.children.push(c); return c; },
    replaceChildren() { this.children = []; this._html = ""; },
    set textContent(v) { this._html = String(v); },
    get textContent() { return this._html; },
    set innerHTML(v) { this._html = v; },
    get innerHTML() { return this._html; },
    querySelector() { return makeEl("div"); },
    querySelectorAll() { return []; },
    getAttribute() { return null; },
    addEventListener() {},
    scrollIntoView() {},
    classList: { toggle() {} },
  };
}
const elements = {};
const document = {
  createElement: (t) => makeEl(t),
  getElementById: (id) => {
    if (!elements[id]) elements[id] = makeEl("div");
    return elements[id];
  },
  querySelectorAll: () => [],
};

function findHtml(el, re) {
  if (re.test(el.innerHTML || "")) return true;
  if (re.test(el.className || "")) return true;
  return el.children.some((c) => findHtml(c, re));
}

async function fetchJSON(requestPath) {
  const url = new URL(requestPath, "http://local");
  return JSON.parse(fs.readFileSync(path.join(ROOT, url.pathname), "utf-8"));
}
const fetch = async (p) => ({ ok: true, json: async () => fetchJSON(p) });
const location = { search: "", href: "" };

const run = new Function("document", "location", "fetch", "console", "URL", "findHtml", appJs + `
;(async () => {
  const results = {};
  const fail = [];
  try {
    await initIndex();
    let patchEntries = 0;
    for (const year of document.getElementById("patch-list").children) {
      for (const month of year.children) {
        for (const list of month.children) {
          if (list.className === "patch-list") patchEntries += list.children.length;
        }
      }
    }
    results.indexPatches = patchEntries;
    results.indexHasModeBadge = findHtml(document.getElementById("patch-list"), /愚人节/);
    results.indexHasQuickPlayHackedLabel = findHtml(document.getElementById("patch-list"), /快速比赛：黑客入侵/);
    let qpHackedEntryHtml = "";
    for (const year of document.getElementById("patch-list").children) {
      for (const month of year.children) {
        for (const list of month.children) {
          if (list.className !== "patch-list") continue;
          for (const entry of list.children) {
            if ((entry.href || "").includes("p-2026-01-08-1")) qpHackedEntryHtml = entry.innerHTML || "";
          }
        }
      }
    }
    results.indexQpHackedContentBadge = /快速比赛：黑客入侵/.test(qpHackedEntryHtml);
    results.updatedFmt = /^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2} UTC[+-]\\d+(?::\\d{2})?$/.test(document.getElementById("updated").textContent);

    // jump bar: year select (2016-2026) + month select populated for the
    // default (latest) year; patch entries carry the first-section badge and
    // the content char count
    const jumpBar = document.getElementById("jump-bar");
    results.jumpYears = jumpBar.children[1] ? jumpBar.children[1].children.length : 0;
    results.jumpMonths = jumpBar.children[2] ? jumpBar.children[2].children.length : 0;
    results.indexHasSectionBadge = findHtml(document.getElementById("patch-list"), /badge section/);
    results.indexHasChars = findHtml(document.getElementById("patch-list"), /\\d[\\d,]* 字/);

    await initEntries();
    results.filterChips = document.getElementById("filters").children.length;
    results.entryCards = document.getElementById("results").children.length;
    results.firstCardHref = document.getElementById("results").children[0].href || "";

    location.search = "?hero=soldier-76&key=soldier-76%3A%3Aweapon%3A%3Aheavy-pulse-rifle";
    await initEntry();
    results.entryName = document.getElementById("entry-name").textContent;
    results.entryMeta = document.getElementById("entry-meta").textContent;
    results.entryHasValues = findHtml(document.getElementById("entry-body"), /value-row/);
    results.entryHasPatchLink = findHtml(document.getElementById("entry-body"), /patch\\.html\\?id=/);
    results.entryHasEditedBadge = findHtml(document.getElementById("entry-body"), /官方事后编辑/);
    // merged EN+CN rows: one .entry carries BOTH site badges plus the EN
    // secondary line; unpaired EN-only records keep a single 英文站 badge
    results.entryHasMergedRow = false;
    results.entryHasEnOnlyRow = false;
    (function collectEntry(el) {
      const html = el.innerHTML || "";
      if (/badge cn/.test(html) && /badge en/.test(html)) results.entryHasMergedRow = true;
      if (/badge en/.test(html) && !/badge cn/.test(html)) results.entryHasEnOnlyRow = true;
      if (results.entryHasMergedRow && results.entryHasEnOnlyRow) return;
      for (const c of el.children) collectEntry(c);
    })(document.getElementById("entry-body"));
    results.entryHasBilingualText = findHtml(document.getElementById("entry-body"), /en-text/);
    results.entryMergedCount = /(\\d+) 条更改记录/.test(results.entryMeta)
      ? results.entryMeta.match(/(\\d+) 条更改记录/)[1] : "?";

    location.search = "?hero=ana&key=hero%3A%3Aana";
    await initEntry();
    const heroBody = document.getElementById("entry-body");
    const heroGrid = heroBody.children[heroBody.children.length - 1];
    results.heroEntryCards = heroGrid.children.length;

    location.search = "?id=p-2025-03-18-1&lang=cn";
    await initPatch();
    results.patchTitle = document.getElementById("patch-title").textContent;
    results.langButtons = document.getElementById("lang-switch").children.length;
    results.patchSections = document.getElementById("patch-article").children.length;

    location.search = "?id=p-2026-08-11-1&lang=en";
    await initPatch();
    const modernBody = document.getElementById("patch-article");
    results.patchHasAvatar = findHtml(modernBody, /hero-avatar/);
    results.patchHasChangeList = findHtml(modernBody, /change-list/);
    results.patchHasAbilityIcon = findHtml(modernBody, /ability-icon/);
    results.patchHasBold = findHtml(modernBody, /strong>Choose your path/);
    results.patchHasSectionDev = findHtml(modernBody, /Several underutilized perks/);
    results.patchHasMapCompare = findHtml(modernBody, /map-compare/);
    // map asset paths are section-scoped (s<global section index>); the page
    // must reference images from multiple map sections (collision regression)
    const mapSections = [];
    (function collectMapSections(el) {
      const html = el.innerHTML || "";
      const re = /assets\\/maps\\/en-2026-08-11-1\\/s(\\d+)\\/0-before\\.png/g;
      let m;
      while ((m = re.exec(html))) mapSections.push(m[1]);
      for (const c of el.children) collectMapSections(c);
    })(modernBody);
    results.mapSectionCount = [...new Set(mapSections)].length;
    results.patchHasStadiumItem = findHtml(modernBody, /stadium-item/);
    results.patchHasRarityBadge = findHtml(modernBody, /item-badge/);
    results.tocChildren = document.getElementById("patch-toc").children.length;
    results.tocHasSec0 = document.getElementById("patch-toc").children.some((a) => a.href === "#sec-0");
    results.tocHiddenModern = document.getElementById("patch-toc").hidden;

    location.search = "?id=en-2020-02-12-1&lang=en";
    await initPatch();
    results.patchHasContentLink = findHtml(document.getElementById("patch-article"), /<a href="https?:\\/\\//);

    location.search = "?id=p-2025-04-01-1&lang=en";
    await initPatch();
    results.patchHasModeBadge = /愚人节/.test(document.getElementById("patch-sites").innerHTML || "");

    location.search = "?id=p-2026-01-08-1&lang=en";
    await initPatch();
    results.patchQpHackedContentBadge = /快速比赛：黑客入侵/.test(document.getElementById("patch-sites").innerHTML || "");

    location.search = "?id=en-2016-05-27-1&lang=en";
    await initPatch();
    results.patchEdited = document.getElementById("patch-edits").innerHTML || "";
    results.legacyStructured = findHtml(document.getElementById("patch-article"), /timeline-group/);
    results.legacyNoRawText = !findHtml(document.getElementById("patch-article"), /raw-text/);

    location.search = "?id=en-2016-07-19-1&lang=en";
    await initPatch();
    const legacyBody = document.getElementById("patch-article");
    results.legacyHasAvatar = findHtml(legacyBody, /hero-avatar/);
    results.legacyHasChangeList = findHtml(legacyBody, /change-list/);
    results.legacyTocVisible = !document.getElementById("patch-toc").hidden;
    results.legacyBastionIcon = findHtml(legacyBody, /assets\\/icons\\/heroes\\/bastion\\.png/);

    location.search = "?slug=soldier-76";
    await initHero();
    const timelineEl = document.getElementById("timeline");
    const dimTitles = [];
    const groupTitles = [];
    let hasValuesChip = false;
    let heroHasMergedRow = false;
    let heroHasEnOnlyRow = false;
    (function collectHero(el) {
      const html = el.innerHTML || "";
      if (/badge cn/.test(html) && /badge en/.test(html)) heroHasMergedRow = true;
      if (/badge en/.test(html) && !/badge cn/.test(html)) heroHasEnOnlyRow = true;
      if (heroHasMergedRow && heroHasEnOnlyRow) return;
      for (const c of el.children) collectHero(c);
    })(timelineEl);
    for (const g of timelineEl.children) {
      if (g.className === "dim-section") {
        dimTitles.push(g.innerHTML || "");
        for (const sub of g.children) {
          if (sub.className === "timeline-group") {
            groupTitles.push(sub.innerHTML || "");
            if (/class="values"/.test(sub.innerHTML || "")) hasValuesChip = true;
          }
        }
      }
    }
    results.dimSections = dimTitles.length;
    results.heroHasWeapon = groupTitles.some((t) => /Helix|螺旋/.test(t));
    results.heroHasStim = groupTitles.some((t) => /Stim|强化/.test(t));
    results.heroHasAttr = dimTitles.some((t) => /英雄属性/.test(t));
    results.heroHasValues = hasValuesChip;
    // default view is standard-only: April Fools records must not appear
    results.heroDefaultNoSpecial = !findHtml(timelineEl, /Running speed increased by 100/);

    location.search = "?slug=soldier-76&modes=all";
    await initHero();
    const timelineAll = document.getElementById("timeline");
    results.heroAllShowsSpecial = findHtml(timelineAll, /Running speed increased by 100/);
    results.heroNoHashGroup = groupTitles.every((t) => !/hero-/.test(t));

    // unit: the numeric-fingerprint veto keeps a disjoint-digit pair unmerged
    // (real-data shape: juno 2025-07-09 "30%/65%" vs "100/75"), while a
    // shared-digit pair merges
    const vetoPairMap = {
      "en-2025-07-09-1": { id: "p-2025-07-09-1", other: "cn-2025-07-09-1" },
      "cn-2025-07-09-1": { id: "p-2025-07-09-1", other: "en-2025-07-09-1" },
    };
    const vetoRows = mergeEntryRecords([
      { patch: "en-2025-07-09-1", site: "en", date: "2025-07-09", kind: "general", dimension: "other", text_en: "Max overhealth reduced to 30% (Down from 65%)." },
      { patch: "cn-2025-07-09-1", site: "cn", date: "2025-07-09", kind: "general", dimension: "other", text_cn: "过量生命值从100降低至75。" },
    ], vetoPairMap);
    results.vetoKeepsSeparate = vetoRows.length === 2 && !vetoRows[0].en && !vetoRows[1].en;
    const mergeRows = mergeEntryRecords([
      { patch: "en-2025-03-25-1", site: "en", date: "2025-03-25", kind: "ability", dimension: "ability", ability_slug: "x", text_en: "Damage increased from 50 to 60." },
      { patch: "cn-2025-03-26-1", site: "cn", date: "2025-03-26", kind: "ability", dimension: "ability", ability_slug: "x", text_cn: "伤害从50提高至60。" },
    ], {
      "en-2025-03-25-1": { id: "p-2025-03-25-1", other: "cn-2025-03-26-1" },
      "cn-2025-03-26-1": { id: "p-2025-03-25-1", other: "en-2025-03-25-1" },
    });
    results.mergeSharedDigit = mergeRows.length === 1 && !!mergeRows[0].en;

    console.log(JSON.stringify(results, null, 1));
    if (results.indexPatches !== 343) fail.push("indexPatches=" + results.indexPatches);
    if (results.filterChips !== 6) fail.push("filterChips=" + results.filterChips);
    if (!results.firstCardHref.includes("entry.html?hero=")) fail.push("firstCardHref=" + results.firstCardHref);
    if (results.entryCards !== 905) fail.push("entryCards=" + results.entryCards);
    if (!results.indexHasModeBadge) fail.push("index mode badge missing");
    if (!results.indexHasQuickPlayHackedLabel) fail.push("index quick-play-hacked label missing");
    if (!results.indexQpHackedContentBadge) fail.push("index qp-hacked content badge missing");
    if (results.jumpYears !== 11) fail.push("jumpYears=" + results.jumpYears);
    if (!results.jumpMonths) fail.push("jump month options missing");
    if (!results.indexHasSectionBadge) fail.push("index section badge missing");
    if (!results.indexHasChars) fail.push("index chars missing");
    if (!/脉冲步枪/.test(results.entryName)) fail.push("entryName=" + results.entryName);
    if (!/更改记录/.test(results.entryMeta)) fail.push("entryMeta=" + results.entryMeta);
    if (!results.entryHasValues) fail.push("entry values rows missing");
    if (!results.entryHasPatchLink) fail.push("entry patch link missing");
    if (results.entryHasEditedBadge) fail.push("entry edited badge should be gone after edit reset");
    if (!results.entryHasMergedRow) fail.push("entry merged EN+CN row missing");
    if (!results.entryHasEnOnlyRow) fail.push("entry EN-only row should stay single");
    if (!results.entryHasBilingualText) fail.push("entry merged bilingual text missing");
    if (results.entryMergedCount !== "17") fail.push("entry merged count=" + results.entryMergedCount);
    if (results.heroEntryCards !== 18) fail.push("hero entry cards=" + results.heroEntryCards);
    if (results.langButtons !== 2) fail.push("langButtons=" + results.langButtons);
    if (!results.patchTitle) fail.push("empty patch title");
    if (!results.patchHasAvatar) fail.push("patch hero avatar missing");
    if (!results.patchHasChangeList) fail.push("patch change-list missing");
    if (!results.patchHasAbilityIcon) fail.push("patch ability icon missing");
    if (!results.patchHasBold) fail.push("patch bold emphasis missing");
    if (!results.patchHasSectionDev) fail.push("patch section dev note missing");
    if (!results.patchHasMapCompare) fail.push("patch map-compare missing");
    if (results.mapSectionCount < 3) fail.push("patch map sections=" + results.mapSectionCount);
    if (!results.patchHasStadiumItem) fail.push("patch stadium item missing");
    if (!results.patchHasRarityBadge) fail.push("patch stadium rarity badge missing");
    if (!results.patchHasContentLink) fail.push("patch content link missing");
    if (!results.patchHasModeBadge) fail.push("patch mode badge missing");
    if (!results.patchQpHackedContentBadge) fail.push("patch qp-hacked content badge missing");
    if (!results.tocChildren || !results.tocHasSec0) fail.push("toc missing entries=" + results.tocChildren);
    if (results.tocHiddenModern) fail.push("modern toc should be visible");
    if (!results.legacyStructured || !results.legacyNoRawText) fail.push("legacy page not structured");
    if (!results.legacyHasAvatar) fail.push("legacy hero avatar missing");
    if (!results.legacyHasChangeList) fail.push("legacy change-list missing");
    if (!results.legacyTocVisible) fail.push("legacy toc should be visible");
    if (!results.legacyBastionIcon) fail.push("legacy Bastion icon missing");
    if (!results.updatedFmt) fail.push("index updated not local time=" + document.getElementById("updated").textContent);
    if (results.patchEdited) fail.push("patch edited badge should be gone after edit reset=" + results.patchEdited);
    if (!results.heroHasWeapon || !results.heroHasStim) fail.push("weapon/stim group missing");
    if (!results.heroHasAttr) fail.push("hero attribute group missing");
    if (!results.heroHasValues) fail.push("values chip missing");
    if (!results.heroNoHashGroup) fail.push("hash-slug group found");
    if (!results.heroDefaultNoSpecial) fail.push("hero default view shows special-mode records");
    if (!results.heroAllShowsSpecial) fail.push("hero modes=all view missing special-mode records");
    if (!heroHasMergedRow) fail.push("hero page merged EN+CN row missing");
    if (!heroHasEnOnlyRow) fail.push("hero page EN-only row should stay single");
    if (!results.vetoKeepsSeparate) fail.push("merge fingerprint veto not keeping disjoint-digit pair separate");
    if (!results.mergeSharedDigit) fail.push("merge shared-digit pair not merged");
    if (fail.length) { console.error("ASSERT FAIL:", fail.join("; ")); process.exit(1); }
    console.log("ALL WEB ASSERTIONS OK");
  } catch (e) {
    console.error("RUNTIME ERROR:", e.stack || e.message);
    process.exit(1);
  }
})();
`);

run(document, location, fetch, console, URL, findHtml);
