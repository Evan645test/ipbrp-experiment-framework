import { spawn } from "node:child_process";
import { mkdtemp, open, access } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const origin = "http://localhost:5173/";
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function probe() {
  try {
    const response = await fetch(`${origin}data/manifest.json`, { signal: AbortSignal.timeout(1500) });
    if (!response.ok) return "occupied";
    const manifest = await response.json();
    return manifest.paperCount === 8 && Array.isArray(manifest.papers) && manifest.papers.length === 8 && manifest.papers.every((paper, index) => paper?.id === `paper-${String(index + 1).padStart(2, "0")}`) ? "ready" : "occupied";
  } catch (error) {
    return error instanceof SyntaxError ? "occupied" : "unavailable";
  }
}
function openBrowser() {
  return new Promise((resolve, reject) => {
    const child = spawn("/usr/bin/open", [origin], { stdio: "inherit" });
    child.once("error", reject);
    child.once("exit", code => code === 0 ? resolve() : reject(new Error("無法開啟瀏覽器，請手動開啟 http://localhost:5173/。")));
  });
}
try {
  if ((() => { const [major, minor] = process.versions.node.split(".").map(Number); return major < 22 || (major === 22 && minor < 13); })()) throw new Error("需要 Node.js 22.13 以上版本。");
  const status = await probe();
  if (status === "occupied") throw new Error("5173 已由其他網站使用。請先關閉該網站，再雙擊此入口。");
  if (status !== "ready") {
    await access(join(root, "node_modules/vinext/dist/cli.js")).catch(() => { throw new Error("網站套件尚未安裝。請在論文逐段精讀器資料夾執行 npm install，再重新開啟入口。"); });
    const logDir = await mkdtemp(join(tmpdir(), "paper-reader-"));
    const logPath = join(logDir, "startup.log");
    const log = await open(logPath, "a");
    const child = spawn(process.execPath, [join(root, "scripts/run-framework.mjs"), "dev"], {
      cwd: root, detached: true, stdio: ["ignore", log.fd, log.fd],
      env: { ...process.env, PATH: `${dirname(process.execPath)}:${process.env.PATH ?? ""}` },
    });
    let startupError;
    child.once("error", error => { startupError = error; });
    child.unref();
    await log.close();
    console.log("正在開啟論文導讀與逐段精讀……");
    let ready = false;
    for (let attempt = 0; attempt < 120; attempt++) {
      if (startupError) throw startupError;
      if (await probe() === "ready") { ready = true; break; }
      if (child.exitCode !== null) break;
      await delay(500);
    }
    if (!ready) {
      if (child.pid && child.exitCode === null) child.kill("SIGTERM");
      throw new Error(`網站未成功啟動，啟動記錄位於：${logPath}`);
    }
  }
  await openBrowser();
  console.log("已開啟統一閱讀入口。可以關閉這個視窗。");
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
