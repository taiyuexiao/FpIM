// 截图验证:登录 -> 发起他人画像(出完整名片格式确认卡) + 用户气泡复制按钮
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import http from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";

const chromePath = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const targetUrl = "http://localhost:5173/";
const debugPort = 9468;
const shot = "C:/python/pycharm/shouwenzeren/_review_card.png";
const userDataDir = path.join(tmpdir(), `review-shot-${Date.now()}`);
await mkdir(userDataDir, { recursive: true });

const chrome = spawn(chromePath, [
  "--headless=new", "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
  `--remote-debugging-port=${debugPort}`, `--user-data-dir=${userDataDir}`,
  "--window-size=1440,960", "about:blank",
], { stdio: ["ignore", "pipe", "pipe"] });

let ws; let nextId = 1; const pending = new Map();
const delay = (ms) => new Promise((r) => setTimeout(r, ms));
function send(method, params = {}) {
  const id = nextId++;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}
async function evaljs(expression) {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 400));
  return r.result?.value;
}
function getJson(p) {
  return new Promise((resolve, reject) => {
    http.get({ host: "127.0.0.1", port: debugPort, path: p }, (res) => {
      let b = ""; res.on("data", (c) => (b += c)); res.on("end", () => resolve(JSON.parse(b)));
    }).on("error", reject);
  });
}

try {
  let tab;
  for (let i = 0; i < 40; i++) {
    try { tab = (await getJson("/json/list")).find((t) => t.type === "page"); if (tab) break; } catch {}
    await delay(250);
  }
  ws = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.addEventListener("open", res, { once: true }); ws.addEventListener("error", rej, { once: true }); });
  ws.addEventListener("message", (e) => {
    const p = JSON.parse(e.data);
    if (p.id && pending.has(p.id)) { const { resolve, reject } = pending.get(p.id); pending.delete(p.id); p.error ? reject(new Error(p.error.message)) : resolve(p.result); }
  });
  await send("Page.enable"); await send("Runtime.enable");
  await send("Page.navigate", { url: targetUrl });
  let hasForm = false;
  for (let i = 0; i < 20; i++) {
    await delay(500);
    hasForm = await evaljs(`!!document.querySelector('.login-form input')`);
    if (hasForm) break;
    if ((await evaljs(`location.pathname`)) !== "/login") break;
  }
  if (hasForm) {
    await evaljs(`(() => {
      const inputs = document.querySelectorAll('.login-form input');
      const set = (el, v) => { const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; s.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); };
      set(inputs[0], '123312312313'); set(inputs[1], '123456');
    })()`);
    await delay(300);
    await evaljs(`[...document.querySelectorAll('button')].find(b => b.textContent.includes('登录平台'))?.click()`);
    await delay(2500);
  }
  for (let i = 0; i < 20; i++) {
    if (await evaljs(`!!document.querySelector('.chat-composer textarea')`)) break;
    await delay(500);
  }
  await evaljs(`(() => {
    const ta = document.querySelector('.chat-composer textarea');
    if (!ta) return;
    const s = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    s.call(ta, '给徐轩增加标签：量子计算'); ta.dispatchEvent(new Event('input', { bubbles: true }));
  })()`);
  await delay(300);
  await evaljs(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === '发送')?.click()`);
  // 等确认卡出现
  let ok = false;
  for (let i = 0; i < 90; i++) {
    await delay(1000);
    ok = await evaljs(`!!document.querySelector('.review-person-preview')`);
    if (ok) break;
  }
  console.log("REVIEW_CARD", ok);
  const info = await evaljs(`JSON.stringify({
    name: document.querySelector('.review-person-preview .person-name')?.textContent || '',
    metas: [...document.querySelectorAll('.review-person-preview .person-meta')].map(e => e.textContent),
    tags: document.querySelectorAll('.review-person-preview .tag').length,
    copyBtns: document.querySelectorAll('.copy-instruction-button').length,
  })`);
  console.log("INFO", info);
  // 滚动到底部看最新卡
  await evaljs(`document.querySelector('.chat-thread-panel')?.scrollTo(0, 999999)`);
  await delay(500);
  const shotData = await send("Page.captureScreenshot", { format: "png" });
  await writeFile(shot, Buffer.from(shotData.data, "base64"));
  console.log("SHOT", shot);
  // 滚到顶部看用户气泡复制按钮
  await evaljs(`document.querySelector('.chat-thread-panel')?.scrollTo(0, 0)`);
  await delay(500);
  const shot2 = await send("Page.captureScreenshot", { format: "png" });
  await writeFile(shot.replace('.png', '_top.png'), Buffer.from(shot2.data, "base64"));
  console.log("SHOT2", shot.replace('.png', '_top.png'));
} finally {
  chrome.kill();
  setTimeout(() => process.exit(0), 500).unref();
}
