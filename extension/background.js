// Walks an RWI thread *in the owner's own tab*: navigates page by page at reading
// pace, lets each page load its photos normally, saves it with Chrome's page
// capture (MHTML, like "Save page as"), and uploads that to the Rep Index.
// Nothing is fetched behind the page's back and nothing runs unless clicked.

const MAX_PAGES = 30;
const PAUSE = [3000, 6000]; // between pages, ms
let job = null;

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.type === "start") {
    if (job) return sendResponse({ ok: false, error: "A capture is already running." });
    job = { tabId: msg.tabId, cancelled: false };
    run(msg.tabId, msg.mode).finally(() => {
      job = null;
      badge("");
    });
    sendResponse({ ok: true });
  } else if (msg?.type === "stop" && job) {
    job.cancelled = true;
  }
});

const REDDIT = /^https:\/\/(www\.|old\.|new\.)?reddit\.com\/r\/[^/]+\/(comments|wiki)\//;

async function run(tabId, mode) {
  const tab = await chrome.tabs.get(tabId);
  if (REDDIT.test(tab.url || "")) return runSinglePage(tabId);
  const info = await inTab(tabId, readThread);
  if (!info?.isThread) return panel(tabId, "This isn't an RWI thread page.", "bad", 100, true);

  const others = [];
  for (let p = 1; p <= Math.min(info.total, MAX_PAGES); p++) if (p !== info.current) others.push(p);
  const pages = mode === "thread" ? [info.current, ...others] : [info.current];
  let posts = 0, photos = 0, missing = 0, saved = 0;

  for (const [i, p] of pages.entries()) {
    if (job.cancelled) break;
    if (i > 0) {
      await panel(tabId, `Next page in a moment…`, null, (i / pages.length) * 100);
      await sleep(PAUSE[0] + Math.random() * (PAUSE[1] - PAUSE[0]));
      if (job.cancelled) break;
      await navigate(tabId, p === 1 ? info.base : `${info.base}page-${p}`);
    }
    badge(`${i + 1}/${pages.length}`);
    await panel(tabId, `Page ${p} of ${info.total}: loading photos…`, null, (i / pages.length) * 100);

    const prep = await inTab(tabId, preparePage);
    if (prep?.challenged) return finish(tabId, info, `RWI asked for verification on page ${p} — stopped, no retry. ${saved} page(s) saved.`, "bad");
    await waitForImages(tabId);

    await panel(tabId, `Page ${p} of ${info.total}: saving…`, null, ((i + 0.5) / pages.length) * 100);
    let res;
    try {
      const mhtml = await chrome.pageCapture.saveAsMHTML({ tabId });
      res = await upload(mhtml, "multipart/related", "/api/capture/mhtml");
    } catch (e) {
      return finish(tabId, info, `Page ${p}: ${e.message || e}`, "bad");
    }
    saved += 1;
    posts += res.new_posts;
    photos += res.stored_photos;
    missing += res.missing_photos.length;
  }

  const stopped = job.cancelled ? "Stopped. " : "";
  const capped = mode === "thread" && info.total > MAX_PAGES ? ` (first ${MAX_PAGES} of ${info.total})` : "";
  const miss = missing ? `, ${missing} photo(s) didn't load` : "";
  await finish(tabId, info, `${stopped}Saved “${info.title}”: ${saved} page(s)${capped} — +${posts} posts, +${photos} photos${miss}.`, "good");
}

// Reddit thread or wiki page: one page, no pagination to walk.
async function runSinglePage(tabId) {
  badge("1/1");
  await panel(tabId, "Loading comments and photos…", null, 20);
  await inTab(tabId, preparePage);
  await waitForImages(tabId);
  await panel(tabId, "Saving…", null, 60);
  try {
    const mhtml = await chrome.pageCapture.saveAsMHTML({ tabId });
    const res = await upload(mhtml, "multipart/related", "/api/capture/mhtml");
    await panel(tabId, `Saved “${res.title}”: ${res.posts} ${res.kind === "wiki" ? "sections" : "posts"}, +${res.stored_photos} photos.`, "good", 100, true);
  } catch (e) {
    await panel(tabId, String(e.message || e), "bad", 100, true);
  }
}

async function finish(tabId, info, text, tone) {
  // Put the owner back where they started.
  const now = (await chrome.tabs.get(tabId)).url;
  if (now && now.split("#")[0] !== info.url.split("#")[0]) await navigate(tabId, info.url);
  await panel(tabId, text, tone, 100, true);
}

// ---- helpers run inside the RWI tab -------------------------------------------

function readThread() {
  const isThread = /\/threads\//.test(location.pathname);
  const canonical = document.querySelector('link[rel="canonical"]')?.href || location.href;
  const base = canonical.replace(/#.*$/, "").replace(/page-\d+\/?$/, "");
  const nav = document.querySelector(".pageNavSimple-el--current")?.textContent.match(/(\d+)\s+of\s+(\d+)/);
  return {
    isThread,
    url: location.href,
    base,
    current: nav ? +nav[1] : 1,
    total: nav ? +nav[2] : 1,
    title: document.querySelector("h1.p-title-value")?.textContent.trim() || document.title,
  };
}

async function preparePage() {
  if (/Just a moment/.test(document.title) || document.querySelector("#challenge-form, .cf-turnstile, #cf-challenge-running")) {
    return { challenged: true };
  }
  // Load every photo the way reading the whole page would: eager-load and scroll through.
  document.querySelectorAll("img").forEach((img) => (img.loading = "eager"));
  for (let y = 0; y < document.body.scrollHeight; y += Math.max(400, innerHeight * 0.9)) {
    scrollTo(0, y);
    await new Promise((r) => setTimeout(r, 180));
  }
  scrollTo(0, 0);
  return { challenged: false };
}

function imagesPending() {
  return [...document.querySelectorAll(".message-body img, shreddit-post img, shreddit-comment img, .thing img, .md img")].filter((i) => !i.complete).length;
}

function showPanel(text, tone, pct, final) {
  let el = document.getElementById("rep-index-panel");
  if (!el) {
    el = document.createElement("div");
    el.id = "rep-index-panel";
    el.style.cssText =
      "position:fixed;right:20px;bottom:20px;z-index:2147483647;width:340px;padding:14px 16px;border-radius:14px;" +
      "background:#121214;color:#ece6da;border:1px solid rgba(255,255,255,.12);box-shadow:0 20px 50px rgba(0,0,0,.5);" +
      "font:13px/1.45 -apple-system,BlinkMacSystemFont,Inter,sans-serif";
    el.innerHTML =
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">' +
      '<b style="font:italic 18px Georgia,serif;color:#c9a46a">Rep Index</b>' +
      '<button style="all:unset;cursor:pointer;color:#8f8a80;font-size:12px"></button></div>' +
      '<div class="msg"></div><div style="margin-top:10px;height:3px;border-radius:2px;background:rgba(255,255,255,.1)">' +
      '<div class="bar" style="height:100%;width:0;border-radius:2px;background:#c9a46a;transition:width .4s"></div></div>';
    document.body.appendChild(el);
  }
  const btn = el.querySelector("button");
  btn.textContent = final ? "Close" : "Stop";
  btn.onclick = () => (final ? el.remove() : (chrome.runtime.sendMessage({ type: "stop" }), (btn.textContent = "Stopping…")));
  const msg = el.querySelector(".msg");
  msg.textContent = text;
  msg.style.color = tone === "bad" ? "#d9826f" : tone === "good" ? "#7fb89a" : "#ece6da";
  if (pct != null) el.querySelector(".bar").style.width = pct + "%";
}

// ---- plumbing -------------------------------------------------------------------

async function inTab(tabId, func, args = []) {
  const [r] = await chrome.scripting.executeScript({ target: { tabId }, func, args });
  return r?.result;
}

function panel(tabId, text, tone, pct, final = false) {
  return inTab(tabId, showPanel, [text, tone, pct ?? null, final]).catch(() => {});
}

async function waitForImages(tabId, timeoutMs = 20000) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    if ((await inTab(tabId, imagesPending)) === 0) return;
    await sleep(700);
  }
}

function navigate(tabId, url) {
  return new Promise((resolve) => {
    const done = () => {
      chrome.tabs.onUpdated.removeListener(listener);
      clearTimeout(timer);
      resolve();
    };
    const listener = (id, change) => id === tabId && change.status === "complete" && done();
    const timer = setTimeout(done, 60000);
    chrome.tabs.onUpdated.addListener(listener);
    chrome.tabs.update(tabId, { url });
  });
}

async function upload(body, contentType, path) {
  const { endpoint, token } = await chrome.storage.local.get(["endpoint", "token"]);
  if (!endpoint || !token) throw new Error("Set the Rep Index address and token in the extension options.");
  const r = await fetch(endpoint.replace(/\/+$/, "") + path, {
    method: "POST",
    headers: { "content-type": contentType, "x-capture-token": token },
    body,
  });
  const text = await r.text();
  if (!r.ok) throw new Error(`Rep Index answered ${r.status}: ${text.slice(0, 160)}`);
  return JSON.parse(text);
}

function badge(text) {
  chrome.action.setBadgeBackgroundColor({ color: "#c9a46a" });
  chrome.action.setBadgeText({ text });
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
