/* Headless smoke test: run the site's init functions against real data with a
 * minimal DOM shim, asserting rendered structure (grouping, patch counts). */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const appJs = fs.readFileSync(path.join(ROOT, "web", "app.js"), "utf-8");

function makeEl(tag) {
  return {
    tagName: tag, children: [], _html: "", dataset: {}, style: {},
    className: "", id: "", href: "", target: "", rel: "",
    appendChild(c) { this.children.push(c); return c; },
    set textContent(v) { this._html = String(v); },
    get textContent() { return this._html; },
    set innerHTML(v) { this._html = v; },
    get innerHTML() { return this._html; },
    querySelector() { return makeEl("div"); },
    querySelectorAll() { return []; },
    addEventListener() {},
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

async function fetchJSON(requestPath) {
  const url = new URL(requestPath, "http://local");
  return JSON.parse(fs.readFileSync(path.join(ROOT, url.pathname), "utf-8"));
}
const fetch = async (p) => ({ ok: true, json: async () => fetchJSON(p) });
const location = { search: "", href: "" };

const run = new Function("document", "location", "fetch", "console", "URL", appJs + `
;(async () => {
  const results = {};
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

    await initHeroes();

    location.search = "?id=p-2025-03-18-1&lang=cn";
    await initPatch();
    results.patchTitle = document.getElementById("patch-title").textContent;
    results.langButtons = document.getElementById("lang-switch").children.length;
    results.patchSections = document.getElementById("patch-body").children.length;

    location.search = "?slug=soldier-76";
    await initHero();
    const groupTitles = [];
    for (const g of document.getElementById("timeline").children) {
      if (g.className === "timeline-group") groupTitles.push(g.innerHTML || "");
    }
    results.heroGroups = groupTitles.length;
    results.heroHasHelix = groupTitles.some((t) => /Helix|螺旋/.test(t));
    results.heroHasStim = groupTitles.some((t) => /Stim|强化/.test(t));
    results.heroHasAgility = groupTitles.some((t) => /Agility|敏捷/.test(t));
    results.heroNoHashGroup = groupTitles.every((t) => !/hero-/.test(t));

    console.log(JSON.stringify(results, null, 1));
    const fail = [];
    if (results.indexPatches !== 341) fail.push("indexPatches=" + results.indexPatches);
    if (results.langButtons !== 2) fail.push("langButtons=" + results.langButtons);
    if (!results.patchTitle) fail.push("empty patch title");
    if (!results.heroHasHelix || !results.heroHasStim) fail.push("helix/stim group missing");
    if (!results.heroNoHashGroup) fail.push("hash-slug group found");
    if (fail.length) { console.error("ASSERT FAIL:", fail.join("; ")); process.exit(1); }
    console.log("ALL WEB ASSERTIONS OK");
  } catch (e) {
    console.error("RUNTIME ERROR:", e.stack || e.message);
    process.exit(1);
  }
})();
`);

run(document, location, fetch, console, URL);
