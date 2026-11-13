// Phone-width screenshot of a flow, via the Chrome DevTools Protocol (no extra dependencies).
//   node scripts/phone_shot.mjs <url> <out.png> '[{"scroll":"text"},{"click":"text"},{"wait":800}]' [light|dark] [height]
// "click" taps the nearest button/link around the smallest element whose text contains the string;
// "scroll" brings that element to the top of the viewport.
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [url, out, stepsJson = "[]", scheme = "dark", height = "844"] = process.argv.slice(2);
const steps = JSON.parse(stepsJson);
const port = 9300 + Math.floor(Math.random() * 600);
const chrome = spawn(process.env.CHROME ?? "C:/Program Files/Google/Chrome/Application/chrome.exe", [
  "--headless=new",
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${mkdtempSync(join(tmpdir(), "shot-"))}`,
  "about:blank",
]);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
await sleep(2500);
const page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0;
const pend = new Map();
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.method === "Runtime.exceptionThrown") console.error("page error:", JSON.stringify(d.params.exceptionDetails).slice(0, 400));
  if (d.method === "Runtime.consoleAPICalled" && d.params.type === "error") console.error("console.error:", JSON.stringify(d.params.args).slice(0, 400));
  if (d.method === "Network.requestWillBeSent" && process.env.SHOT_DEBUG) console.error("req:", d.params.requestId, d.params.request.url.slice(0, 120));
  if (d.method === "Network.loadingFailed") console.error("net fail:", d.params.errorText, d.params.requestId);
  if (d.id && pend.has(d.id)) pend.get(d.id)(d.result ?? d.error);
};
await new Promise((r) => (ws.onopen = r));
const send = (method, params = {}) =>
  new Promise((r) => {
    const i = ++id;
    pend.set(i, r);
    ws.send(JSON.stringify({ id: i, method, params }));
  });
const evaluate = async (expression) =>
  { const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }); if (r?.exceptionDetails || !r?.result) console.error("eval:", JSON.stringify(r).slice(0, 300)); return r?.result?.value; };

await send("Runtime.enable");
await send("Network.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 390, height: Number(height), deviceScaleFactor: 2, mobile: true });
await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: scheme }] });
await send("Page.navigate", { url });
await sleep(6000);
const find = (text) => `(() => {
  const want = ${JSON.stringify(text)}.toLowerCase();
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    const el = n.parentElement;
    if (el && el.offsetParent !== null && n.nodeValue.toLowerCase().includes(want)) return el;
  }
  // text split across nodes: fall back to the smallest element whose text contains it
  const all = [...document.querySelectorAll('h1,h2,h3,h4,p,span,button,a,li,div')].filter(e => e.offsetParent !== null && e.childElementCount < 6 && (e.textContent||'').toLowerCase().includes(want));
  all.sort((x, y) => (x.textContent||'').length - (y.textContent||'').length);
  return all[0] || null;
})()`;
for (const s of steps) {
  if (s.wait) await sleep(s.wait);
  if (s.scroll) {
    const ok = await evaluate(`(() => { const e = ${find(s.scroll)}; if (!e) return false; e.scrollIntoView({block: 'start'}); window.scrollBy(0, -${s.offset ?? 60}); return true; })()`);
    if (!ok) console.error("not found:", s.scroll);
    await sleep(500);
  }
  if (s.click) {
    const ok = await evaluate(`(() => { const e = ${find(s.click)}; if (!e) return false; (e.closest('button,a,[role=button]') || e).click(); return true; })()`);
    if (!ok) console.error("not found:", s.click);
    await sleep(s.after ?? 2500);
  }
}
const shot = await send("Page.captureScreenshot", { format: "png" });
writeFileSync(out, Buffer.from(shot.data, "base64"));
console.log(out);
ws.close();
chrome.kill();
process.exit(0);
