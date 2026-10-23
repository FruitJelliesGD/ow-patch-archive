/* Headless layout regression check for the patch page, run in a real browser
 * (the smoke test's DOM shim has no CSS engine, so computed styles live here).
 *
 * Covers two layout bugs:
 *   1. legacy (TOC-hidden) pages must span the full row, not the 230px column;
 *   2. the section intro description must carry the card's 16px padding.
 *
 * Run:  npx -p playwright node tools/_layout_check.js
 */
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const PORT = 8973;

function check(ok, label, failures) {
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}`);
  if (!ok) failures.push(label);
}

async function main() {
  const failures = [];
  // -u: unbuffered stdout so the "serving at" readiness line arrives on the pipe
  const server = spawn("python", ["-u", "tools/serve.py", "--port", String(PORT)], { cwd: ROOT });
  let browser;
  try {
    await new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error("server startup timeout")), 30000);
      server.stdout.on("data", (d) => {
        const s = String(d);
        if (s.includes("serving at")) { clearTimeout(t); resolve(); }
        else if (s.includes("Traceback") || s.includes("Error")) { clearTimeout(t); reject(new Error("serve.py: " + s)); }
      });
      server.on("exit", (code) => reject(new Error("serve.py exited " + code)));
    });

    browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

    // structured legacy page: renders like a modern patch (TOC visible,
    // two-column, no raw-text blob)
    await page.goto(`http://127.0.0.1:${PORT}/patch.html?id=en-2016-07-19-1`);
    await page.waitForSelector(".hero-block");
    const legacy = await page.evaluate(() => {
      const article = document.getElementById("patch-article");
      const toc = document.getElementById("patch-toc");
      const ar = article.getBoundingClientRect();
      const tr = toc.getBoundingClientRect();
      return {
        tocVisible: !toc.hidden,
        articleAfterToc: ar.left >= tr.right - 1,
        hasRawText: !!document.querySelector(".raw-text"),
        hasAvatar: !!document.querySelector(".hero-avatar"),
      };
    });
    check(legacy.tocVisible, "legacy: TOC visible", failures);
    check(legacy.articleAfterToc, "legacy: article to the right of the TOC", failures);
    check(!legacy.hasRawText, "legacy: no raw-text blob (structured)", failures);
    check(legacy.hasAvatar, "legacy: hero avatar rendered", failures);

    // non-square ability icons (wide weapon art) must keep their ratio:
    // object-fit contain + a rendered box wider than tall, never squished
    await page.waitForFunction(() =>
      [...document.querySelectorAll(".ability-icon")]
        .some((i) => i.naturalWidth > i.naturalHeight && i.complete));
    const iconRatio = await page.evaluate(() => {
      const wide = [...document.querySelectorAll(".ability-icon")]
        .find((i) => i.naturalWidth > i.naturalHeight);
      if (!wide) return { found: false };
      const r = wide.getBoundingClientRect();
      return {
        found: true,
        objectFit: getComputedStyle(wide).objectFit,
        wide: r.width > r.height,
        rect: `${Math.round(r.width)}x${Math.round(r.height)}`,
      };
    });
    check(iconRatio.found, "icon ratio: wide ability icon found", failures);
    check(iconRatio.objectFit === "contain",
      `icon ratio: object-fit ${iconRatio.objectFit}`, failures);
    check(iconRatio.wide, `icon ratio: wide icon renders wide (${iconRatio.rect})`, failures);
    check(Number(iconRatio.rect.split("x")[0]) <= 60,
      `icon ratio: box capped at 60px (${iconRatio.rect})`, failures);

    // modern page: TOC visible, article in column 2, intro padded 16px
    await page.goto(`http://127.0.0.1:${PORT}/patch.html?id=p-2026-08-11-1`);
    await page.waitForSelector(".patch-toc a");
    const modern = await page.evaluate(() => {
      const article = document.getElementById("patch-article");
      const toc = document.getElementById("patch-toc");
      const desc = document.querySelector(".patch-body .desc");
      const ar = article.getBoundingClientRect();
      const tr = toc.getBoundingClientRect();
      return {
        tocHidden: toc.hidden,
        articleAfterToc: ar.left >= tr.right - 1, // auto-placed in column 2
        articleLeft: Math.round(ar.left),
        descPaddingLeft: desc ? getComputedStyle(desc).paddingLeft : null,
      };
    });
    check(modern.tocHidden === false, "modern: TOC visible", failures);
    check(modern.articleAfterToc,
      `modern: article to the right of the TOC (left ${modern.articleLeft})`, failures);
    check(modern.descPaddingLeft === "16px",
      `modern: intro padding-left ${modern.descPaddingLeft}`, failures);

    // a TOC hidden for any other reason must collapse the grid to one column
    await page.evaluate(() => { document.getElementById("patch-toc").hidden = true; });
    const collapsed = await page.evaluate(() => {
      const cs = getComputedStyle(document.getElementById("patch-article"));
      return { colStart: cs.gridColumnStart, colEnd: cs.gridColumnEnd };
    });
    check(collapsed.colStart === "1" && collapsed.colEnd === "-1",
      `collapsed TOC: article spans full row (${collapsed.colStart} / ${collapsed.colEnd})`, failures);

    // ---- 8. index filter bar: grouping, counts, summary, mobile collapse ----
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(`http://127.0.0.1:${PORT}/index.html`);
    await page.waitForSelector("#cat-chips .chip");
    {
      const info = await page.evaluate(() => ({
        groups: [...document.querySelectorAll(".chip-group-label")].map((e) => e.textContent),
        chips: document.querySelectorAll("#cat-chips .chip").length,
        toggleDisplay: getComputedStyle(document.getElementById("filter-toggle")).display,
        overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      }));
      check(JSON.stringify(info.groups) === JSON.stringify(["模式", "内容", "结构"]),
        `index filter: group labels (${info.groups.join("|")})`, failures);
      check(info.chips === 18, `index filter: chip count ${info.chips}`, failures);
      check(info.toggleDisplay === "none", `index filter: desktop toggle hidden (${info.toggleDisplay})`, failures);
      check(!info.overflow, "index filter: no desktop horizontal overflow", failures);
    }
    await page.evaluate(() => setFilter(["event", "crossover"], "all"));
    await page.waitForFunction(() => !document.getElementById("filter-summary").hidden);
    {
      const info = await page.evaluate(() => ({
        summary: document.getElementById("filter-summary-text").textContent,
        matchVisible: !document.getElementById("filter-match").hidden,
        clearVisible: !document.getElementById("filter-clear").hidden,
        overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      }));
      check(/已选：/.test(info.summary) && info.matchVisible && info.clearVisible,
        `index filter: summary row (${info.summary})`, failures);
      check(!info.overflow, "index filter: no horizontal overflow with summary", failures);
    }
    // URL seeding (shareable link): ?cat=…&match=all must restore the view
    await page.goto(`http://127.0.0.1:${PORT}/index.html?cat=event,crossover&match=all`);
    await page.waitForSelector(".patch-entry");
    {
      const info = await page.evaluate(() => ({
        selected: getFilter().join(","),
        match: getFilterMatch(),
        summaryVisible: !document.getElementById("filter-summary").hidden,
        visible: document.querySelectorAll(".patch-entry").length,
        total: allPatches.length,
      }));
      check(info.selected === "event,crossover" && info.match === "all" && info.summaryVisible,
        `index filter: URL seeds state (${info.selected}, ${info.match})`, failures);
      check(info.visible > 0 && info.visible < info.total,
        `index filter: URL-seeded list is filtered (${info.visible}/${info.total})`, failures);
    }
    // old shared links (?cat=…, no match) keep their OR meaning
    await page.goto(`http://127.0.0.1:${PORT}/index.html?cat=event,crossover`);
    await page.waitForSelector(".patch-entry");
    {
      const info = await page.evaluate(() => ({
        selected: getFilter().join(","),
        match: getFilterMatch(),
        visible: document.querySelectorAll(".patch-entry").length,
      }));
      check(info.selected === "event,crossover" && info.match === "any",
        `index filter: legacy ?cat keeps OR (${info.match})`, failures);
      check(info.visible > 0, `index filter: legacy ?cat renders (${info.visible})`, failures);
    }

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`http://127.0.0.1:${PORT}/index.html`);
    // the mobile bar starts collapsed, so the chips are attached but hidden
    await page.waitForSelector("#cat-chips .chip", { state: "attached" });
    {
      const info = await page.evaluate(() => ({
        toggleDisplay: getComputedStyle(document.getElementById("filter-toggle")).display,
        collapsed: document.getElementById("jump-bar").classList.contains("filters-collapsed"),
        chipsDisplay: getComputedStyle(document.getElementById("cat-chips")).display,
        overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      }));
      check(info.toggleDisplay !== "none", `index filter: mobile toggle visible (${info.toggleDisplay})`, failures);
      check(info.collapsed && info.chipsDisplay === "none",
        `index filter: mobile chips start collapsed (${info.chipsDisplay})`, failures);
      check(!info.overflow, "index filter: no mobile horizontal overflow", failures);
    }
    await page.click("#filter-toggle");
    {
      const info = await page.evaluate(() => ({
        expanded: document.getElementById("filter-toggle").getAttribute("aria-expanded"),
        chipsDisplay: getComputedStyle(document.getElementById("cat-chips")).display,
        overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      }));
      check(info.expanded === "true" && info.chipsDisplay !== "none",
        `index filter: mobile toggle expands (${info.expanded}, ${info.chipsDisplay})`, failures);
      check(!info.overflow, "index filter: expanded mobile chips do not widen the page", failures);
    }

    await browser.close();
  } finally {
    if (browser) await browser.close().catch(() => {});
    server.kill();
  }

  if (failures.length) {
    console.error("LAYOUT FAIL:\n" + failures.join("\n"));
    process.exit(1);
  }
  console.log("ALL LAYOUT ASSERTIONS OK");
}

main().catch((e) => {
  console.error("LAYOUT CHECK ERROR:", e && e.message);
  process.exit(1);
});
