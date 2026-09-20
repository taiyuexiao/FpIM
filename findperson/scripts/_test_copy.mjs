// 验证复制按钮:点击后出现“已复制”提示
import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import http from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";

const chromePath = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const debugPort = 9469;
const userDataDir = path.join(tmpdir(), `copy-test-${Date.now()}`);
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
  await send("Page.navigate", { url: "http://localhost:5173/" });
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
  // 等历史会话气泡加载
  let n = 0;
  for (let i = 0; i < 20; i++) {
    n = await evaljs(`document.querySelectorAll('.copy-instruction-button').length`);
    if (n > 0) break;
    await delay(500);
  }
  console.log("BTNS", n);
  await evaljs(`document.querySelector('.copy-instruction-button')?.click()`);
  await delay(600);
  console.log("TIP", await evaljs(`document.querySelector('.copied-tip')?.textContent || 'NONE'`));
} finally {
  chrome.kill();
  setTimeout(() => process.exit(0), 500).unref();
}
