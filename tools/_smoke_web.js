/* Headless smoke test: run the site's init functions against real data with a
 * minimal DOM shim, asserting rendered structure (grouping, patch counts,
 * entry search, entry detail, official-edit badges). */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const appJs = fs.readFileSync(path.join(ROOT, "web", "app.js"), "utf-8");

function loadData(rel) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, "data", rel), "utf-8"));
}
const patchIndex = loadData("patches_index.json");
const entryIndex = loadData("entries_index.json");
const heroIndex = loadData("heroes_index.json");

/* Expectations are derived from the data on disk, never hard-coded: a new
 * patch must not turn this suite red (that used to be the only way it failed).
 * What is asserted is structure — badges, grouping, merges, links — plus the
 * frontend/backend key contract (every category in data has a chip). */
const EXPECT = {
  indexPatches: patchIndex.patches.length,
  entryCards: entryIndex.entries.length,
  heroEntryCards: entryIndex.entries.filter(
    (e) => e.hero_slug === "ana" && e.dimension !== "hero").length,
  jumpYears: new Set(patchIndex.patches.map((p) => p.date.slice(0, 4))).size,
  heroes: heroIndex.heroes.length,
  categories: [...new Set(patchIndex.patches.flatMap((p) => p.categories || []))].sort(),
  hasHeroChip: patchIndex.patches.some((p) => p.mode === "standard" && p.has_hero_changes),
  pageSize: 60, // ENTRY_PAGE_SIZE in web/app.js
  heroSlugs: heroIndex.heroes.map((h) => h.slug),
  weaponEntries: entryIndex.entries.filter((e) => e.dimension === "weapon").length,
};

function makeEl(tag) {
  return {
    tagName: tag, children: [], _html: "", dataset: {}, style: {}, attrs: {},
    className: "", id: "", href: "", target: "", rel: "", hidden: false, value: "",
    appendChild(c) {
      this.children.push(c);
      if (c.id) elements[c.id] = c; // getElementById resolves appended nodes too
      return c;
    },
    replaceChildren() { this.children = []; this._html = ""; },
    remove() {},
    set textContent(v) { this._html = String(v); },
    get textContent() { return this._html; },
    set innerHTML(v) { this._html = v; },
    get innerHTML() { return this._html; },
    querySelector() { return makeEl("div"); },
    querySelectorAll() { return []; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    addEventListener() {},
    scrollIntoView() {},
    classList: {
      toggle() {},
      add() {},
      remove() {},
      contains() { return false; },
    },
  };
}
const elements = {};
const document = {
  createElement: (t) => makeEl(t),
  getElementById: (id) => {
    if (!elements[id]) elements[id] = makeEl("div");
    return elements[id];
  },
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
  documentElement: { lang: "zh-CN", style: { setProperty() {} } },
  title: "",
  body: makeEl("body"),
};
const history = {
  lastUrl: null,
  replaceState(_state, _title, url) { this.lastUrl = url; },
};

function findHtml(el, re) {
  if (re.test(el.innerHTML || "")) return true;
  if (re.test(el.className || "")) return true;
  return el.children.some((c) => findHtml(c, re));
}

async function fetchJSON(requestPath) {
  const url = new URL(requestPath, "http://local");
  const rel = url.pathname.replace(/^\//, "");
  // archive data lives at data/, page assets under web/ (the site root)
  for (const candidate of [path.join(ROOT, rel), path.join(ROOT, "web", rel)]) {
    if (fs.existsSync(candidate)) return JSON.parse(fs.readFileSync(candidate, "utf-8"));
  }
  throw new Error("missing fixture: " + rel);
}
const fetch = async (p) => ({ ok: true, json: async () => fetchJSON(p) });
const location = { search: "", href: "", pathname: "/index.html", reload() {} };

const run = new Function(
  "document", "location", "fetch", "console", "URL", "findHtml", "history", "ResizeObserver",
  `const EXPECT = ${JSON.stringify(EXPECT)};\n` + appJs + `
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
    results.indexCategoryBadge = /快速比赛：黑客入侵/.test(qpHackedEntryHtml);
    // 「英雄改动」 badge: standard-mode patches with hero balance content carry
    // it; special-mode patches with hero blocks (愚人节) and hero-less patches
    // (announcement) must not
    let heroBadgedEntryHtml = "", specialEntryHtml = "", announcementEntryHtml = "";
    for (const year of document.getElementById("patch-list").children) {
      for (const month of year.children) {
        for (const list of month.children) {
          if (list.className !== "patch-list") continue;
          for (const entry of list.children) {
            const href = entry.href || "";
            if (href.includes("p-2026-08-11-1")) heroBadgedEntryHtml = entry.innerHTML || "";
            if (href.includes("p-2026-04-01-1")) specialEntryHtml = entry.innerHTML || "";
            if (href.includes("en-2022-10-04-1")) announcementEntryHtml = entry.innerHTML || "";
          }
        }
      }
    }
    results.indexHasHeroChangesBadge = /badge hero-changes/.test(heroBadgedEntryHtml) && /英雄改动/.test(heroBadgedEntryHtml);
    results.indexSpecialNoHeroBadge = !/badge hero-changes/.test(specialEntryHtml);
    results.indexAnnouncementNoHeroBadge = !/badge hero-changes/.test(announcementEntryHtml);
    const chipBar = document.getElementById("cat-chips");
    results.chipKeys = chipBar.children.map((c) => c.dataset.cat || "");
    results.chipCount = results.chipKeys.length;
    setFilter(["event"]);
    let eventFiltered = 0;
    for (const year of document.getElementById("patch-list").children) {
      for (const month of year.children) {
        for (const list of month.children) {
          if (list.className === "patch-list") eventFiltered += list.children.length;
        }
      }
    }
    results.filteredCount = eventFiltered;
    setFilter([]);
    results.filterReset = getFilter().length === 0;
    // hero_changes filter: same predicate as the badge; every visible entry
    // must carry the badge
    setFilter(["hero_changes"]);
    let heroFiltered = 0;
    let heroFilterAllBadged = true;
    for (const year of document.getElementById("patch-list").children) {
      for (const month of year.children) {
        for (const list of month.children) {
          if (list.className !== "patch-list") continue;
          heroFiltered += list.children.length;
          for (const entry of list.children) {
            if (!/badge hero-changes/.test(entry.innerHTML || "")) heroFilterAllBadged = false;
          }
        }
      }
    }
    results.heroFilteredCount = heroFiltered;
    results.heroFilterAllBadged = heroFilterAllBadged;
    setFilter([]);
    // the "updated" label is a calendar date (newest patch), not a fetch time:
    // it must render as YYYY-MM-DD, never as an invented wall-clock instant
    results.updatedFmt = /^\\d{4}-\\d{2}-\\d{2}$/.test(document.getElementById("updated").textContent);

    // filter state is mirrored into the URL (replaceState) so the current view
    // can be shared / survives a reload
    setFilter(["event"]);
    results.urlSyncFilter = String(history.lastUrl || "").includes("cat=event");
    setFilter([]);
    results.urlSyncCleared = !String(history.lastUrl || "").includes("cat=");

    // a filter that matches nothing must explain itself instead of rendering an
    // empty page
    renderTimeBrowser(allPatches, () => false);
    results.emptyState = findHtml(document.getElementById("patch-list"), /当前筛选下没有补丁/);
    setFilter([]);

    // jump bar: year select (one option per year present in the data) + month
    // select populated for the default (latest) year; patch entries carry the
    // content char count. Looked up by id so DOM order is free to change.
    results.jumpYears = document.getElementById("jump-year").children.length;
    results.jumpMonths = document.getElementById("jump-month").children.length;
    results.indexHasChars = findHtml(document.getElementById("patch-list"), /\\d[\\d,]* 字/);
    // entry title = first section title (在线修正更新 / Hotfix Update); the
    // boilerplate official title is gone, as is the redundant section badge
    let aug12EntryHtml = "", aug20EntryHtml = "";
    for (const year of document.getElementById("patch-list").children) {
      for (const month of year.children) {
        for (const list of month.children) {
          if (list.className !== "patch-list") continue;
          for (const entry of list.children) {
            const href = entry.href || "";
            if (href.includes("p-2026-08-12-1")) aug12EntryHtml = entry.innerHTML || "";
            if (href.includes("en-2026-08-20-1")) aug20EntryHtml = entry.innerHTML || "";
          }
        }
      }
    }
    results.indexTitleIsFirstSection = /patch-entry-title">在线修正更新</.test(aug12EntryHtml)
      && /patch-entry-title">Hotfix Update</.test(aug20EntryHtml);
    results.indexNoSectionBadge = !findHtml(document.getElementById("patch-list"), /badge section/);
    // hybrid-stub entry (cn-2025-07-25-1 stub, no CN sections): the CN view
    // must fall back to the Chinese long title instead of the EN section title
    let jul24EntryHtml = "";
    for (const year of document.getElementById("patch-list").children) {
      for (const month of year.children) {
        for (const list of month.children) {
          if (list.className !== "patch-list") continue;
          for (const entry of list.children) {
            if ((entry.href || "").includes("p-2025-07-24-1")) jul24EntryHtml = entry.innerHTML || "";
          }
        }
      }
    }
    results.indexHybridTitleChinese = /patch-entry-title">[^<]*[\u4e00-\u9fff]/.test(jul24EntryHtml)
      && !/patch-entry-title">Hotfix Balance Update</.test(jul24EntryHtml);

    await initEntries();
    results.filterChips = document.getElementById("filters").children.length;
    results.entryCards = document.getElementById("results").children.length;
    results.firstCardHref = document.getElementById("results").children[0].href || "";
    results.entryCardAvatar = findHtml(document.getElementById("results"), /card-avatar/);
    // "按英雄浏览" grid: one card per hero in heroes_index.json
    results.heroBrowseCards = 0;
    (function countHeroCards(el) {
      for (const c of el.children) {
        if (c.className === "hero-card") results.heroBrowseCards++;
        countHeroCards(c);
      }
    })(document.getElementById("hero-browse"));
    results.heroBrowseVisible = document.getElementById("hero-browse").hidden !== true;
    results.heroBrowseFacts = findHtml(document.getElementById("hero-browse"), /heavy-pulse-rifle|士兵76|Soldier/);

    // ---- pagination: the default view must not build all 949 cards ----
    results.firstPageCards = document.getElementById("results").children.length;
    results.pageSizeHook = Number(document.getElementById("results").dataset.shown || 0);
    results.loadMoreVisible = !!document.getElementById("load-more");
    showMoreEntries();
    results.secondPageCards = document.getElementById("results").children.length;

    // ---- search regression probes (matching/ranking/aliases/labels) ----
    function probe(query, dim) {
      entrySearchState.q = query;
      entrySearchState.dim = dim || "";
      applyEntryFilter();
      return entryFiltered.map((h) => h.entry);
    }
    function probeKeys(query) { return probe(query).map((e) => e.key); }
    const KEY_SOLDIER_RIFLE = "soldier-76::weapon::heavy-pulse-rifle";
    const probes = [
      ["soldier 76", "both spellings of the hero name reach every soldier entry",
        () => { const k = probeKeys("soldier 76"); return k[0] === "hero::soldier-76" && k.length >= 20; }],
      ["soldier76", "compact hero name",
        () => { const k = probeKeys("soldier76"); return k[0] === "hero::soldier-76" && k.length >= 20; }],
      ["dva", "punctuated hero name, no 'advan…' false positive",
        () => { const k = probeKeys("dva");
          return k[0] === "hero::d-va" && !k.includes("symmetra::ability::advanced-teleportation"); }],
      ["d.va", "hero with dot",
        () => probeKeys("d.va")[0] === "hero::d-va"],
      ["dmon", "D.Mon without the dot",
        () => probeKeys("dmon")[0] === "hero::d-mon"],
      ["junkerqueen", "Junker Queen without the space",
        () => probeKeys("junkerqueen")[0] === "hero::junker-queen"],
      ["wreckingball", "Wrecking Ball without the space",
        () => probeKeys("wreckingball")[0] === "hero::wrecking-ball"],
      ["bob", "B.O.B. ability",
        () => probeKeys("bob").includes("ashe::ability::b-o-b")],
      ["ana grenade", "multi-word AND across hero + ability",
        () => { const k = probeKeys("ana grenade");
          return k.includes("ana::ability::biotic-grenade") && k.length < 10; }],
      ["士兵76 脉冲步枪", "multi-word CJK + ASCII",
        () => probeKeys("士兵76 脉冲步枪").includes(KEY_SOLDIER_RIFLE)],
      ["步枪", "CJK substring inside a longer name",
        () => probeKeys("步枪").includes(KEY_SOLDIER_RIFLE)],
      ["武器", "dimension label",
        () => { const k = probeKeys("武器"); return k.length === EXPECT.weaponEntries; }],
      ["麦克雷", "legacy CN hero name",
        () => probeKeys("麦克雷").includes("hero::cassidy")],
      ["mccree", "legacy EN hero name",
        () => probeKeys("mccree").includes("hero::cassidy")],
      ["lucio", "accent-insensitive",
        () => probeKeys("lucio")[0] === "hero::lucio"],
      ["!!!", "punctuation-only query is treated as no query",
        () => probeKeys("!!!").length === EXPECT.entryCards],
      ["zzzz", "no matches",
        () => probeKeys("zzzz").length === 0],
    ];
    results.probeFails = [];
    for (const [query, label, fn] of probes) {
      let ok = false;
      try { ok = !!fn(); } catch (e) { ok = false; }
      if (!ok) results.probeFails.push(query + " (" + label + ")");
    }
    results.probeCount = probes.length;
    // zero-result state is user-visible: message + two ways out
    probe("zzzz");
    results.emptyStateVisible = findHtml(document.getElementById("entry-status"), /没有匹配/);
    results.emptyStateActions = findHtml(document.getElementById("entry-status"), /清空搜索/)
      && findHtml(document.getElementById("entry-status"), /查看全部词条/);
    // highlighted hit
    probe("步枪");
    results.probeHighlight = findHtml(document.getElementById("results"), /<mark>/);
    // back to the default view (also proves the filter resets the page limit)
    probe("");
    results.resetCards = document.getElementById("results").children.length;
    // raw case survives in the URL
    entrySearchState.q = "D.Va";
    applyEntryFilter();
    results.urlKeepsCase = String(history.lastUrl || "").includes("q=D.Va");

    // ---- cross-language parity: the index changes field must equal the merged
    // row count the web renders (guards the Python port of mergeEntryRecords) ----
    const timelines = {};
    for (const heroSlug of EXPECT.heroSlugs) {
      timelines[heroSlug] = (await fetchJSON("data/heroes/" + heroSlug + ".json")).timeline || [];
    }
    const realPairMap = buildPairMap((await fetchJSON("data/patches_index.json")).patches);
    const parityFail = [];
    for (const entry of entryDocs) {
      const standard = (timelines[entry.hero_slug] || [])
        .filter((r) => (r.mode || "standard") === "standard");
      const recs = entry.dimension === "hero"
        ? standard
        : standard.filter((r) => entry.hero_slug + "::" + entryKey(r) === entry.key);
      const rows = mergeEntryRecords(recs, realPairMap).length;
      if (rows !== entry.changes) parityFail.push(entry.key + " js=" + rows + " index=" + entry.changes);
    }
    results.parityFails = parityFail;
    results.parityChecked = entryDocs.length;

    location.search = "?hero=soldier-76&key=soldier-76%3A%3Aweapon%3A%3Aheavy-pulse-rifle";
    await initEntry();
    results.entryName = document.getElementById("entry-name").textContent;
    results.entryAliases = document.getElementById("entry-hero").innerHTML || "";
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

    // a linked card carries the search: the detail page's back links must
    // return to the same filtered list
    location.search = "?hero=ana&key=ana%3A%3Aability%3A%3Abiotic-grenade&q=grenade&dim=ability";
    await initEntry();
    results.backHref = document.getElementById("back-entries").href || "";
    results.backLinkKeepsSearch = results.backHref === "entries.html?q=grenade&dim=ability";

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
    results.patchCategoryBadge = /快速比赛：黑客入侵/.test(document.getElementById("patch-sites").innerHTML || "");

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
    // hero timeline rows link back to the archived patch page (same internal
    // link the entry page has; it used to be a plain span here)
    results.heroPatchLink = findHtml(timelineEl, /patch\\.html\\?id=/);

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

    // OW1 raw_text fallback: no archived patch currently needs it (all 410
    // parse structurally), but README promises the degradation — so exercise it
    // directly instead of leaving it as dead, untested code.
    const rawEl = document.createElement("div");
    await renderRawText(rawEl, "Ana's Biotic Rifle and Soldier: 76 were tuned. <b>not html</b>");
    results.rawTextHeroIcons = /assets\\/icons\\/heroes\\/ana\\.png/.test(rawEl.innerHTML)
      && /assets\\/icons\\/heroes\\/soldier-76\\.png/.test(rawEl.innerHTML);
    results.rawTextEscaped = rawEl.innerHTML.includes("&lt;b&gt;not html&lt;/b&gt;")
      && !rawEl.innerHTML.includes("<b>not html</b>");

    console.log(JSON.stringify(results, null, 1));
    // --- structural assertions (data-independent) ---
    if (results.indexPatches !== EXPECT.indexPatches) fail.push("indexPatches=" + results.indexPatches + " expected=" + EXPECT.indexPatches);
    if (!results.urlSyncFilter) fail.push("filter state not mirrored into the URL");
    if (!results.urlSyncCleared) fail.push("cleared filter still present in the URL");
    if (!results.emptyState) fail.push("empty filter result has no empty state");
    if (!results.entryCardAvatar) fail.push("entry card hero avatar missing");
    if (!results.heroBrowseVisible) fail.push("hero browse section hidden on the default view");
    if (!results.heroBrowseFacts) fail.push("hero browse cards have no hero names");
    if (!results.heroPatchLink) fail.push("hero timeline patch links missing");
    if (!results.rawTextHeroIcons) fail.push("raw_text fallback does not inject hero icons");
    if (!results.rawTextEscaped) fail.push("raw_text fallback does not escape markup");
    if (results.filterChips !== 6) fail.push("filterChips=" + results.filterChips);
    if (!results.firstCardHref.includes("entry.html?hero=")) fail.push("firstCardHref=" + results.firstCardHref);
    // paginated list: first paint is one page, "load more" grows it, a new
    // filter/new query resets it
    const wantFirstPage = Math.min(EXPECT.pageSize, EXPECT.entryCards);
    if (results.entryCards !== wantFirstPage) fail.push("entryCards=" + results.entryCards + " expected first page " + wantFirstPage);
    if (results.firstPageCards !== wantFirstPage) fail.push("firstPageCards=" + results.firstPageCards);
    if (results.pageSizeHook !== wantFirstPage) fail.push("results dataset.shown=" + results.pageSizeHook);
    if (!results.loadMoreVisible) fail.push("load-more button missing on the default view");
    const wantSecondPage = Math.min(EXPECT.pageSize * 2, EXPECT.entryCards);
    if (results.secondPageCards !== wantSecondPage) fail.push("secondPageCards=" + results.secondPageCards + " expected " + wantSecondPage);
    if (results.resetCards !== wantFirstPage) fail.push("filter change kept the old page size: " + results.resetCards);
    if (results.probeFails.length) fail.push("search probes failed: " + results.probeFails.join(" | "));
    if (!results.emptyStateVisible) fail.push("zero-result search shows no message");
    if (!results.emptyStateActions) fail.push("zero-result search offers no way out");
    if (!results.probeHighlight) fail.push("search hit is not highlighted");
    if (!results.urlKeepsCase) fail.push("?q= lost the original capitalisation");
    if (results.parityFails.length) {
      fail.push("index changes != merged rows (" + results.parityFails.length + "): " + results.parityFails.slice(0, 5).join(" | "));
    }
    if (results.parityChecked !== EXPECT.entryCards) fail.push("parity checked " + results.parityChecked + " entries");
    if (!results.backLinkKeepsSearch) fail.push("detail back link lost the search: " + results.backHref);
    if (!results.indexHasModeBadge) fail.push("index mode badge missing");
    if (!results.indexHasQuickPlayHackedLabel) fail.push("index quick-play-hacked label missing");
    if (!results.indexCategoryBadge) fail.push("index category badge missing");
    // every category present in the data must have a chip (frontend/backend
    // label contract): a new category without a chip is unclickable
    const wantChips = ["", ...EXPECT.categories, ...(EXPECT.hasHeroChip ? ["hero_changes"] : [])].sort();
    if (JSON.stringify(results.chipKeys.slice().sort()) !== JSON.stringify(wantChips)) {
      fail.push("chipKeys=" + results.chipKeys.join("|") + " expected=" + wantChips.join("|"));
    }
    if (!(results.filteredCount > 0 && results.filteredCount < results.indexPatches)) fail.push("filteredCount=" + results.filteredCount);
    if (!results.filterReset) fail.push("filter reset failed");
    if (!results.indexHasHeroChangesBadge) fail.push("index hero-changes badge missing");
    if (!results.indexSpecialNoHeroBadge) fail.push("april-fools entry shows hero-changes badge");
    if (!results.indexAnnouncementNoHeroBadge) fail.push("announcement entry shows hero-changes badge");
    if (!(results.heroFilteredCount > 0 && results.heroFilteredCount < results.indexPatches)) fail.push("heroFilteredCount=" + results.heroFilteredCount);
    if (!results.heroFilterAllBadged) fail.push("hero-changes filter shows unbadged entry");
    if (results.jumpYears !== EXPECT.jumpYears) fail.push("jumpYears=" + results.jumpYears + " expected=" + EXPECT.jumpYears);
    if (!results.jumpMonths) fail.push("jump month options missing");
    if (!results.indexHasChars) fail.push("index chars missing");
    if (!results.indexTitleIsFirstSection) fail.push("index entry title is not the first section title");
    if (!results.indexNoSectionBadge) fail.push("index section badge still present");
    if (!results.indexHybridTitleChinese) fail.push("hybrid stub entry title not Chinese");
    // the detail page shows the index's canonical name, not the oldest record's
    if (results.entryName !== "重脉冲步枪 / Heavy Pulse Rifle") fail.push("entryName=" + results.entryName);
    if (!/更改记录/.test(results.entryMeta)) fail.push("entryMeta=" + results.entryMeta);
    if (!results.entryHasValues) fail.push("entry values rows missing");
    if (!results.entryHasPatchLink) fail.push("entry patch link missing");
    if (results.entryHasEditedBadge) fail.push("entry edited badge should be gone after edit reset");
    if (!results.entryHasMergedRow) fail.push("entry merged EN+CN row missing");
    if (!results.entryHasEnOnlyRow) fail.push("entry EN-only row should stay single");
    if (!results.entryHasBilingualText) fail.push("entry merged bilingual text missing");
    // card count (index changes) and detail rows must agree
    if (results.entryMergedCount !== "17") fail.push("entry merged count=" + results.entryMergedCount);
    if (results.heroEntryCards !== EXPECT.heroEntryCards) fail.push("hero entry cards=" + results.heroEntryCards + " expected=" + EXPECT.heroEntryCards);
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
    if (!results.patchCategoryBadge) fail.push("patch category badge missing");
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

run(document, location, fetch, console, URL, findHtml, history, undefined);
