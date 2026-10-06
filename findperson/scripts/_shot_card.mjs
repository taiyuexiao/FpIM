// 截图验证:登录 -> 提问出推荐卡 -> 单击卡片开右侧详情 -> 截图
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import http from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";

const chromePath = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const targetUrl = "http://localhost:5173/";
const debugPort = 9467;
const shot = "C:/python/pycharm/shouwenzeren/_card_click.png";
const userDataDir = path.join(tmpdir(), `card-shot-${Date.now()}`);
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
  // 等登录表单
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
  // 等输入框渲染
  for (let i = 0; i < 20; i++) {
    if (await evaljs(`!!document.querySelector('.chat-composer textarea')`)) break;
    await delay(500);
  }
  // 提问
  await evaljs(`(() => {
    const ta = document.querySelector('.chat-composer textarea');
    if (!ta) return;
    const s = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    s.call(ta, '谁负责hadoop'); ta.dispatchEvent(new Event('input', { bubbles: true }));
  })()`);
  await delay(300);
  await evaljs(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === '发送')?.click()`);
  // 等推荐卡出现(LLM 可能要 60s+)
  let cards = 0;
  for (let i = 0; i < 90; i++) {
    await delay(1000);
    cards = await evaljs(`document.querySelectorAll('.result-card.is-clickable').length`);
    if (cards > 0) break;
  }
  console.log("CARDS", cards);
  // 单击第一张卡 -> 等 250ms 定时器 -> 侧栏应出现
  await evaljs(`document.querySelector('.result-card.is-clickable')?.click()`);
  await delay(1200);
  const sidebar = await evaljs(`JSON.stringify({
    visible: !!document.querySelector('.detail-sidebar'),
    label: document.querySelector('.detail-panel-label')?.textContent || '',
    name: document.querySelector('.detail-header h2')?.textContent || '',
  })`);
  console.log("SIDEBAR", sidebar);
  const shotData = await send("Page.captureScreenshot", { format: "png" });
  await writeFile(shot, Buffer.from(shotData.data, "base64"));
  console.log("SHOT", shot);
  // 双击 -> 应跳个人主页
  await evaljs(`document.querySelector('.result-card.is-clickable')?.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))`);
  await delay(1500);
  console.log("AFTER_DBLCLICK", await evaljs(`location.pathname`));
} finally {
  chrome.kill();
  setTimeout(() => process.exit(0), 500).unref();
}
