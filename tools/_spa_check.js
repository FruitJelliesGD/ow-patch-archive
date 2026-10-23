/* Headless SPA navigation regression check, run in a real browser.
 *
 * The smoke test (tools/_smoke_web.js) exercises the page initializers against
 * a DOM shim, but it cannot see whether a click reloaded the document. This
 * check drives the real site: every in-site link must swap the view without a
 * document navigation, URL/title/state must follow, and history/scroll must
 * survive.
 *
 * Run:  npx -p playwright node tools/_spa_check.js
 */
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const PORT = 8974;

function check(ok, label, failures) {
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}`);
  if (!ok) failures.push(label);
}

async function waitPage(page, name) {
  await page.waitForFunction((n) => document.body && document.body.dataset.page === n, name);
}

async function main() {
  const failures = [];
  // -u: unbuffered stdout so the "serving at" readiness line arrives on the pipe
  const server = spawn("python", ["-u", "tools/serve.py", "--port", String(PORT)], { cwd: ROOT });
  let browser;
  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("server startup timeout")), 60000);
      server.stdout.on("data", (d) => {
        const s = String(d);
        if (s.includes("serving at")) { clearTimeout(timer); resolve(); }
        else if (s.includes("Traceback") || s.includes("Error")) { clearTimeout(timer); reject(new Error("serve.py: " + s)); }
      });
      server.on("exit", (code) => reject(new Error("serve.py exited " + code)));
    });

    browser = await chromium.launch();
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    const consoleErrors = [];
    let loads = 0;
    page.on("load", () => { loads += 1; });
    page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
    page.on("pageerror", (err) => consoleErrors.push("pageerror: " + err.message));

    const base = `http://127.0.0.1:${PORT}`;
    await page.goto(`${base}/index.html`);
    await page.waitForSelector(".patch-entry");
    const baselineLoads = loads;
    await page.evaluate(() => { window.__spaMarker = "spa-" + Math.random(); });
    const marker = await page.evaluate(() => window.__spaMarker);

    // ---- 1. top navigation: index -> entries ----
    await page.getByRole("link", { name: "词条检索" }).first().click();
    await waitPage(page, "entries");
    await page.waitForSelector("#results .entry-card");
    {
      const info = await page.evaluate(() => ({
        marker: window.__spaMarker,
        page: document.body.dataset.page,
        href: location.pathname + location.search,
        title: document.title,
        active: (document.querySelector(".topnav a.active") || {}).textContent || "",
        cards: document.querySelectorAll("#results .entry-card").length,
      }));
      check(info.marker === marker, "index -> entries: no document reload", failures);
      check(loads === baselineLoads, `index -> entries: no load event (${loads - baselineLoads})`, failures);
      check(info.page === "entries" && /\/entries\.html(\?|$)/.test(info.href),
        `index -> entries: URL ${info.href}`, failures);
      check(/词条检索/.test(info.title), `index -> entries: title ${info.title}`, failures);
      check(info.active.trim() === "词条检索", "index -> entries: topnav active state", failures);
      check(info.cards > 0, "index -> entries: entry cards rendered", failures);
    }

    // ---- 2. search -> entry detail -> back link keeps the search ----
    await page.fill("#search", "soldier 76");
    await page.waitForFunction(() => new URLSearchParams(location.search).get("q") === "soldier 76");
    await page.waitForSelector("#results .entry-card");
    await page.click("#results .entry-card");
    await waitPage(page, "entry");
    await page.waitForFunction(() => {
      const el = document.getElementById("entry-name");
      return el && el.textContent && el.textContent !== "-";
    });
    {
      const info = await page.evaluate(() => ({
        marker: window.__spaMarker,
        href: location.pathname + location.search,
        title: document.title,
        back: (document.getElementById("back-entries") || {}).getAttribute
          ? document.getElementById("back-entries").getAttribute("href") : "",
      }));
      check(info.marker === marker, "entries -> entry: no document reload", failures);
      check(/\/entry\.html(\?|$)/.test(info.href) && /q=soldier/.test(info.href),
        `entries -> entry: URL ${info.href}`, failures);
      check(/词条/.test(info.title), `entries -> entry: title ${info.title}`, failures);
      check(/q=soldier/.test(info.back), `entry back link keeps search (${info.back})`, failures);
    }
    await page.click("#back-entries");
    await waitPage(page, "entries");
    await page.waitForFunction(() => {
      const input = document.getElementById("search");
      return input && input.value === "soldier 76";
    });
    {
      const info = await page.evaluate(() => ({
        marker: window.__spaMarker,
        href: location.pathname + location.search,
        q: document.getElementById("search").value,
      }));
      check(info.marker === marker, "entry -> entries: no document reload", failures);
      check(/q=soldier/.test(info.href) && info.q === "soldier 76",
        `entry -> entries: restored search (${info.q})`, failures);
    }

    // ---- 3. entries -> hero timeline -> back ----
    await page.fill("#search", "");
    await page.waitForFunction(() => {
      const browse = document.getElementById("hero-browse");
      return browse && !browse.hidden
        && new URLSearchParams(location.search).get("q") === null;
    });
    await page.click(".hero-card");
    await waitPage(page, "hero");
    await page.waitForSelector("#timeline .dim-section");
    {
      const info = await page.evaluate(() => ({
        marker: window.__spaMarker,
        href: location.pathname + location.search,
        title: document.title,
      }));
      check(info.marker === marker, "entries -> hero: no document reload", failures);
      check(/\/hero\.html(\?|$)/.test(info.href) && /slug=/.test(info.href),
        `entries -> hero: URL ${info.href}`, failures);
      check(/英雄改动轨迹/.test(info.title), `entries -> hero: title ${info.title}`, failures);
    }
    await page.click("#back-entries");
    await waitPage(page, "entries");
    await page.waitForSelector("#results .entry-card");

    // ---- 4. index -> patch detail; language switch keeps the view/scroll ----
    await page.getByRole("link", { name: "按时间浏览补丁" }).first().click();
    await waitPage(page, "index");
    await page.waitForSelector(".patch-entry");
    await page.click('.patch-entry[href*="p-2025-03-18-1"]');
    await waitPage(page, "patch");
    await page.waitForFunction(() => document.querySelectorAll("#lang-switch .lang-btn").length === 2);
    await page.waitForSelector("#patch-article .timeline-group");
    {
      const info = await page.evaluate(() => ({
        marker: window.__spaMarker,
        href: location.pathname + location.search,
        title: document.title,
      }));
      check(info.marker === marker, "index -> patch: no document reload", failures);
      check(/\/patch\.html(\?|$)/.test(info.href) && /id=p-2025-03-18-1/.test(info.href),
        `index -> patch: URL ${info.href}`, failures);
      check(/补丁/.test(info.title), `index -> patch: title ${info.title}`, failures);
    }
    // In-page hash links must keep native anchor behavior (no SPA re-render).
    const tocHash = await page.evaluate(() => {
      const link = document.querySelector("#patch-toc a");
      if (!link) return "";
      const href = link.getAttribute("href");
      link.click();
      return href;
    });
    await page.waitForFunction((h) => h && location.hash === h, tocHash);
    {
      const info = await page.evaluate(() => ({
        marker: window.__spaMarker,
        hash: location.hash,
      }));
      check(info.marker === marker && info.hash === tocHash,
        `patch TOC hash stays native (${info.hash})`, failures);
    }
    await page.evaluate(() => window.scrollTo({ top: 600, left: 0, behavior: "instant" }));
    await page.waitForTimeout(150);
    const scrollBefore = await page.evaluate(() => window.scrollY);
    // Dispatch the click in-page instead of Playwright's locator click: a normal
    // locator click first scrolls the switch into view, which would destroy the
    // very position this assertion is about.
    await page.evaluate(() => {
      const link = document.querySelector("#lang-switch .lang-btn:not(.active)");
      if (link) link.click();
    });
    await page.waitForFunction(() => {
      const active = document.querySelector("#lang-switch .lang-btn.active");
      return document.documentElement.lang === "en"
        && active && active.textContent.trim() === "英文站"
        && document.querySelectorAll("#patch-article .timeline-group").length > 0;
    });
    await page.waitForTimeout(250);
    {
      const info = await page.evaluate(() => ({
        marker: window.__spaMarker,
        href: location.pathname + location.search,
        lang: document.documentElement.lang,
        active: (document.querySelector("#lang-switch .lang-btn.active") || {}).textContent || "",
        scrollY: window.scrollY,
      }));
      check(info.marker === marker, "patch language switch: no document reload", failures);
      check(/lang=en/.test(info.href) && info.lang === "en" && /英文站/.test(info.active),
        `patch language switch: EN view (${info.href}, lang=${info.lang})`, failures);
      check(Math.abs(info.scrollY - scrollBefore) < 300,
        `patch language switch: keeps scroll (${scrollBefore} -> ${info.scrollY})`, failures);
    }
    await page.click("header a.back");
    await waitPage(page, "index");
    await page.waitForSelector(".patch-entry");
    {
      const info = await page.evaluate(() => ({
        marker: window.__spaMarker,
        lang: document.documentElement.lang,
      }));
      check(info.marker === marker && info.lang === "zh-CN",
        `patch -> index: html lang reset (${info.lang})`, failures);
    }

    // ---- 5. browser back/forward re-renders instead of reloading ----
    await page.evaluate(() => history.back());
    await waitPage(page, "patch");
    await page.waitForFunction(() => document.querySelectorAll("#lang-switch .lang-btn").length === 2);
    {
      const info = await page.evaluate(() => ({
        marker: window.__spaMarker,
        page: document.body.dataset.page,
        href: location.pathname + location.search,
      }));
      check(info.marker === marker && info.page === "patch",
        `browser back: patch view restored without reload (${info.href})`, failures);
    }
    await page.evaluate(() => history.forward());
    await waitPage(page, "index");
    await page.waitForSelector(".patch-entry");
    {
      const info = await page.evaluate(() => ({
        marker: window.__spaMarker,
        page: document.body.dataset.page,
      }));
      check(info.marker === marker && info.page === "index",
        "browser forward: index restored without reload", failures);
    }

    // ---- 6. scroll position is restored when going back ----
    await page.getByRole("link", { name: "词条检索" }).first().click();
    await waitPage(page, "entries");
    await page.waitForSelector("#results .entry-card");
    await page.evaluate(() => window.scrollTo({ top: 600, left: 0, behavior: "instant" }));
    await page.waitForTimeout(200);
    const scrollBeforeBack = await page.evaluate(() => window.scrollY);
    // Delay the Ana hero JSON so history.back() lands while initEntry is still
    // pending: this is the exact race where a late initializer used to leave
    // the new URL showing the old view.
    const slowHero = "**/data/heroes/ana.json";
    await page.route(slowHero, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 400));
      await route.continue();
    });
    // In-page click again: a locator click would scroll the card into view and
    // replace the position we are trying to preserve.
    await page.evaluate(() => {
      const card = document.querySelector('#results .entry-card[href*="hero=ana"]')
        || document.querySelector("#results .entry-card");
      if (card) card.click();
    });
    await waitPage(page, "entry");
    await page.evaluate(() => history.back());
    await waitPage(page, "entries");
    await page.unroute(slowHero);
    await page.waitForTimeout(400);
    {
      const info = await page.evaluate(() => ({
        marker: window.__spaMarker,
        y: window.scrollY,
      }));
      check(info.marker === marker, "browser back to entries: no document reload", failures);
      check(scrollBeforeBack > 100 && Math.abs(info.y - scrollBeforeBack) < 100,
        `browser back restores scroll (${scrollBeforeBack} -> ${info.y})`, failures);
    }

    // ---- 7. a direct deep link still loads as a normal page ----
    const deep = await context.newPage();
    try {
      await deep.goto(`${base}/entry.html?hero=soldier-76&key=soldier-76%3A%3Aweapon%3A%3Aheavy-pulse-rifle`);
      await deep.waitForFunction(() => {
        const el = document.getElementById("entry-name");
        return el && el.textContent.includes("重脉冲步枪");
      });
      check(true, "deep link: entry detail renders directly", failures);
    } catch (err) {
      check(false, "deep link failed: " + (err && err.message), failures);
    } finally {
      await deep.close().catch(() => {});
    }

    check(loads === baselineLoads,
      `SPA session kept one document load (${loads - baselineLoads} extra)`, failures);
    check(consoleErrors.length === 0,
      `no console/page errors (${consoleErrors.slice(0, 3).join(" | ")})`, failures);

    await context.close().catch(() => {});
  } finally {
    if (browser) await browser.close().catch(() => {});
    server.kill();
  }

  if (failures.length) {
    console.error("SPA FAIL:\n" + failures.join("\n"));
    process.exit(1);
  }
  console.log("ALL SPA ASSERTIONS OK");
}

main().catch((e) => {
  console.error("SPA CHECK ERROR:", e && e.message);
  process.exit(1);
});
