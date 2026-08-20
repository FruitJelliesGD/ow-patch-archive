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

    // legacy page: TOC hidden -> article spans the full grid row
    await page.goto(`http://127.0.0.1:${PORT}/patch.html?id=en-2016-07-19-1`);
    await page.waitForSelector(".raw-text");
    const legacy = await page.evaluate(() => {
      const article = document.getElementById("patch-article");
      const cs = getComputedStyle(article);
      return {
        tocHidden: document.getElementById("patch-toc").hidden,
        colStart: cs.gridColumnStart,
        colEnd: cs.gridColumnEnd,
        width: article.getBoundingClientRect().width,
      };
    });
    check(legacy.tocHidden === true, "legacy: TOC hidden", failures);
    check(legacy.colStart === "1" && legacy.colEnd === "-1",
      `legacy: article spans full row (${legacy.colStart} / ${legacy.colEnd})`, failures);
    check(legacy.width > 500, `legacy: content width ${Math.round(legacy.width)}`, failures);

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
