#!/usr/bin/env node
/* One perf or Lighthouse run at a time on this laptop (W1-P1, MASTER-PLAN §5.0 #6). Ten agents share one i7-1255U: two
   Lighthouse runs side by side measure each other, not the page. The lock is a folder, made atomically with mkdir,
   holding owner.json {pkg, pid, host, at}. A lock older than 20 minutes whose process is gone is stale and is taken
   over; any other lock is waited for (never run beside). Screenshots and functional checks do not need it.

   In a tool:  const lock = await require("./perf_lock.cjs").acquire("w1-p1");  …  lock.release();
               (lock.waitedMs says how long it waited: report it with the numbers)
   Around a command:  node tools/perf_lock.cjs run --pkg w1-p1 -- lighthouse …   (tools/lh_gate.sh does this)
                      node tools/perf_lock.cjs status

   CINEMA_PERF_LOCK overrides the folder (tests). */
"use strict";
const fs = require("fs"), os = require("os"), path = require("path"), cp = require("child_process");

const LOCK = process.env.CINEMA_PERF_LOCK || "C:/Users/requi/.cinema-perf.lock";
const STALE_MS = 20 * 60e3;

function alive(pid) {
  try { process.kill(pid, 0); return true; } catch (e) { return e.code === "EPERM"; }
}
function owner() {
  try { return JSON.parse(fs.readFileSync(path.join(LOCK, "owner.json"), "utf-8")); } catch (e) { return null; }
}
function age() {
  try { return Date.now() - fs.statSync(LOCK).mtimeMs; } catch (e) { return 0; }
}
function tryTake(pkg) {
  try { fs.mkdirSync(LOCK); } catch (e) { if (e.code === "EEXIST") return false; throw e; }
  fs.writeFileSync(path.join(LOCK, "owner.json"), JSON.stringify({ pkg, pid: process.pid, host: os.hostname(), at: new Date().toISOString() }));
  return true;
}
function stale() {
  const o = owner();
  const old = o ? Date.now() - Date.parse(o.at) > STALE_MS : age() > STALE_MS;
  return old && !(o && alive(o.pid));
}

/* resolves with {release, waitedMs, owner} once this process holds the lock */
async function acquire(pkg, opts) {
  opts = opts || {};
  const t0 = Date.now(), poll = opts.pollMs || 2000, timeout = opts.timeoutMs || 90 * 60e3, log = opts.log || ((s) => console.error(s));
  let said = false;
  for (;;) {
    if (tryTake(pkg)) break;
    if (stale()) {
      const o = owner();
      log(`perf lock: taking over a stale lock (${o ? o.pkg + " pid " + o.pid + " since " + o.at : "no owner file"})`);
      try { fs.rmSync(LOCK, { recursive: true, force: true }); } catch (e) {}
      continue;
    }
    if (!said) { const o = owner(); log(`perf lock: waiting for ${o ? o.pkg + " (pid " + o.pid + ", since " + o.at + ")" : "another run"}`); said = true; }
    if (Date.now() - t0 > timeout) throw new Error("perf lock: gave up after " + Math.round((Date.now() - t0) / 1000) + " s");
    await new Promise((r) => setTimeout(r, poll));
  }
  const waitedMs = Date.now() - t0;
  let held = true;
  const release = () => {
    if (!held) return; held = false;
    const o = owner();
    if (o && o.pid === process.pid) { try { fs.rmSync(LOCK, { recursive: true, force: true }); } catch (e) {} }
  };
  process.once("exit", release);
  for (const sig of ["SIGINT", "SIGTERM"]) process.once(sig, () => { release(); process.exit(130); });
  if (said || waitedMs > 50) log(`perf lock: held by ${pkg} after waiting ${(waitedMs / 1000).toFixed(1)} s`);
  return { release, waitedMs, owner: owner() };
}

/* the machine's load when a number was taken (Windows: CPU % from wmic is slow; os.loadavg() is 0 there, so the
   one-second CPU sample of os.cpus() is reported instead) */
async function load() {
  const snap = () => os.cpus().map((c) => c.times);
  const a = snap(); await new Promise((r) => setTimeout(r, 1000)); const b = snap();
  let idle = 0, total = 0;
  b.forEach((t, i) => { const d = (k) => t[k] - a[i][k]; idle += d("idle"); total += d("user") + d("nice") + d("sys") + d("idle") + d("irq"); });
  return { cpuBusyPct: Math.round(100 * (1 - idle / total)), loadavg: os.loadavg().map((x) => +x.toFixed(2)), cpus: os.cpus().length };
}

module.exports = { acquire, load, LOCK, STALE_MS };

if (require.main === module) {
  const argv = process.argv.slice(2);
  const cmd = argv[0];
  if (cmd === "status") {
    const o = owner();
    console.log(o ? `held by ${o.pkg} pid ${o.pid} (${alive(o.pid) ? "alive" : "gone"}) since ${o.at}` + (stale() ? " — stale" : "") : fs.existsSync(LOCK) ? "a lock folder with no owner file" : "free");
  } else if (cmd === "run") {
    const k = argv.indexOf("--pkg"), sep = argv.indexOf("--");
    const pkg = k >= 0 ? argv[k + 1] : process.env.CINEMA_PKG || "unknown";
    const child = argv.slice(sep + 1);
    if (sep < 0 || !child.length) { console.error("usage: perf_lock.cjs run --pkg NAME -- command args…"); process.exit(2); }
    acquire(pkg).then(async (l) => {
      const ld = await load();
      console.error(`perf lock: waited ${(l.waitedMs / 1000).toFixed(1)} s; machine ${ld.cpuBusyPct}% busy on ${ld.cpus} threads`);
      /* no shell: the command is an executable path (node, python, bash.exe) and its arguments pass as they are */
      const r = cp.spawnSync(child[0], child.slice(1), { stdio: "inherit", env: Object.assign({}, process.env, { CINEMA_PERF_LOCK_HELD: "1" }) });
      if (r.error) console.error("perf lock: could not start " + child[0] + ": " + r.error.message);
      l.release();
      process.exit(r.status == null ? 1 : r.status);
    }).catch((e) => { console.error(String(e)); process.exit(1); });
  } else {
    console.error("usage: perf_lock.cjs run --pkg NAME -- command args…  |  perf_lock.cjs status"); process.exit(2);
  }
}
