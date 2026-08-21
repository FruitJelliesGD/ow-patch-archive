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
    results.updatedFmt = /^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2} UTC[+-]\\d+(?::\\d{2})?$/.test(document.getElementById("updated").textContent);

    await initEntries();
    results.filterChips = document.getElementById("filters").children.length;
    results.entryCards = document.getElementById("results").children.length;
    results.firstCardHref = document.getElementById("results").children[0].href || "";

    location.search = "?hero=soldier-76&key=soldier-76%3A%3Aweapon%3A%3Aheavy-pulse-rifle";
    await initEntry();
    results.entryName = document.getElementById("entry-name").textContent;
    results.entryMeta = document.getElementById("entry-meta").textContent;
    results.entryHasValues = /value-row/.test(document.getElementById("entry-body").innerHTML || "");
    results.entryHasPatchLink = findHtml(document.getElementById("entry-body"), /patch\\.html\\?id=/);
    results.entryHasEditedBadge = findHtml(document.getElementById("entry-body"), /官方事后编辑/);

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
    results.patchHasMapImage = findHtml(modernBody, /assets\\/maps\\/en-2026-08-11-1\\/0-before\\.png/);
    results.patchHasStadiumItem = findHtml(modernBody, /stadium-item/);
    results.patchHasRarityBadge = findHtml(modernBody, /item-badge/);
    results.tocChildren = document.getElementById("patch-toc").children.length;
    results.tocHasSec0 = document.getElementById("patch-toc").children.some((a) => a.href === "#sec-0");
    results.tocHiddenModern = document.getElementById("patch-toc").hidden;

    location.search = "?id=en-2020-02-12-1&lang=en";
    await initPatch();
    results.patchHasContentLink = findHtml(document.getElementById("patch-article"), /<a href="https?:\\/\\//);

    location.search = "?id=en-2016-05-27-1&lang=en";
    await initPatch();
    results.patchEdited = document.getElementById("patch-edits").innerHTML || "";
    results.editTimeLocal = /最近 \\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2} UTC[+-]\\d+/.test(results.patchEdited);
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
    results.heroNoHashGroup = groupTitles.every((t) => !/hero-/.test(t));

    console.log(JSON.stringify(results, null, 1));
    if (results.indexPatches !== 342) fail.push("indexPatches=" + results.indexPatches);
    if (results.filterChips !== 6) fail.push("filterChips=" + results.filterChips);
    if (!results.firstCardHref.includes("entry.html?hero=")) fail.push("firstCardHref=" + results.firstCardHref);
    if (results.entryCards !== 987) fail.push("entryCards=" + results.entryCards);
    if (!/脉冲步枪/.test(results.entryName)) fail.push("entryName=" + results.entryName);
    if (!/更改记录/.test(results.entryMeta)) fail.push("entryMeta=" + results.entryMeta);
    if (!results.entryHasValues) fail.push("entry values rows missing");
    if (!results.entryHasPatchLink) fail.push("entry patch link missing");
    if (!results.entryHasEditedBadge) fail.push("entry edited badge missing");
    if (results.heroEntryCards !== 18) fail.push("hero entry cards=" + results.heroEntryCards);
    if (results.langButtons !== 2) fail.push("langButtons=" + results.langButtons);
    if (!results.patchTitle) fail.push("empty patch title");
    if (!results.patchHasAvatar) fail.push("patch hero avatar missing");
    if (!results.patchHasChangeList) fail.push("patch change-list missing");
    if (!results.patchHasAbilityIcon) fail.push("patch ability icon missing");
    if (!results.patchHasBold) fail.push("patch bold emphasis missing");
    if (!results.patchHasSectionDev) fail.push("patch section dev note missing");
    if (!results.patchHasMapCompare) fail.push("patch map-compare missing");
    if (!results.patchHasMapImage) fail.push("patch map image missing");
    if (!results.patchHasStadiumItem) fail.push("patch stadium item missing");
    if (!results.patchHasRarityBadge) fail.push("patch stadium rarity badge missing");
    if (!results.patchHasContentLink) fail.push("patch content link missing");
    if (!results.tocChildren || !results.tocHasSec0) fail.push("toc missing entries=" + results.tocChildren);
    if (results.tocHiddenModern) fail.push("modern toc should be visible");
    if (!results.legacyStructured || !results.legacyNoRawText) fail.push("legacy page not structured");
    if (!results.legacyHasAvatar) fail.push("legacy hero avatar missing");
    if (!results.legacyHasChangeList) fail.push("legacy change-list missing");
    if (!results.legacyTocVisible) fail.push("legacy toc should be visible");
    if (!results.legacyBastionIcon) fail.push("legacy Bastion icon missing");
    if (!results.updatedFmt) fail.push("index updated not local time=" + document.getElementById("updated").textContent);
    if (!/官方事后编辑/.test(results.patchEdited)) fail.push("patch edited badge=" + results.patchEdited);
    if (!results.editTimeLocal) fail.push("patch edit time not local=" + results.patchEdited);
    if (!results.heroHasWeapon || !results.heroHasStim) fail.push("weapon/stim group missing");
    if (!results.heroHasAttr) fail.push("hero attribute group missing");
    if (!results.heroHasValues) fail.push("values chip missing");
    if (!results.heroNoHashGroup) fail.push("hash-slug group found");
    if (fail.length) { console.error("ASSERT FAIL:", fail.join("; ")); process.exit(1); }
    console.log("ALL WEB ASSERTIONS OK");
  } catch (e) {
    console.error("RUNTIME ERROR:", e.stack || e.message);
    process.exit(1);
  }
})();
`);

run(document, location, fetch, console, URL, findHtml);
