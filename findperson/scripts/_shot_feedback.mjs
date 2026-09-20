// 截图验证:登录管理员 -> 后台管理 -> 推荐反馈页签 -> 截图
import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import http from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { writeFile } from "node:fs/promises";

const chromePath = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const targetUrl = "http://localhost:5173/";
const debugPort = 9466;
const shot = "C:/python/pycharm/shouwenzeren/_feedback.png";
const userDataDir = path.join(tmpdir(), `fb-shot-${Date.now()}`);
await mkdir(userDataDir, { recursive: true });

const chrome = spawn(chromePath, [
  "--headless=new", "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
  `--remote-debugging-port=${debugPort}`, `--user-data-dir=${userDataDir}`,
  "--window-size=1440,960", "about:blank",
], { stdio: ["ignore", "pipe", "pipe"] });

let ws; let nextId = 1; const pending = new Map(); const events = [];
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
function getJson(urlPath) {
  return new Promise((resolve, reject) => {
    http.get({ host: "127.0.0.1", port: debugPort, path: urlPath }, (res) => {
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
    else events.push(p);
  });
  await send("Page.enable"); await send("Runtime.enable");
  await send("Page.navigate", { url: targetUrl });
  // 等登录表单渲染(最多 10s;若已登录会跳走,直接跳过)
  let hasForm = false;
  for (let i = 0; i < 20; i++) {
    await delay(500);
    hasForm = await evaljs(`!!document.querySelector('.login-form input')`);
    if (hasForm) break;
    const p = await evaljs(`location.pathname`);
    if (p !== "/login") break;
  }
  if (hasForm) {
  // 登录
  await evaljs(`(() => {
    const inputs = document.querySelectorAll('.login-form input');
    const set = (el, v) => { const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; s.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); };
    set(inputs[0], '123312312313'); set(inputs[1], '123456');
  })()`);
  await delay(300);
  await evaljs(`[...document.querySelectorAll('button')].find(b => b.textContent.includes('登录平台'))?.click()`);
  await delay(2500);
  }
  await evaljs(`[...document.querySelectorAll('a')].find(el => el.textContent.includes('后台管理'))?.click()`);
  await delay(2000);
  const landed = await evaljs(`location.pathname`);
  console.log("LANDED", landed);
  // 点 推荐反馈 页签
  await evaljs(`[...document.querySelectorAll('.el-tabs__item')].find(t => t.textContent.includes('推荐反馈'))?.click()`);
  await delay(2500);
  const info = await evaljs(`JSON.stringify({url: location.pathname, tab: document.querySelector('.el-tabs__item.is-active')?.textContent, bars: document.querySelectorAll('.activity-bar').length, reasons: document.querySelectorAll('.reason-row').length})`);
  console.log("INFO", info);
  const shotData = await send("Page.captureScreenshot", { format: "png" });
  await writeFile(shot, Buffer.from(shotData.data, "base64"));
  console.log("SHOT", shot);
} finally {
  chrome.kill();
  setTimeout(() => process.exit(0), 500).unref();
}
