#!/usr/bin/env bash
# Lighthouse mobile, median of N runs, on home, the heaviest film page and a cinema page (W1-P1 tool; MASTER-PLAN §7.3 #1
# and §7.4). Gates: home ≥ 92, film ≥ 92, cinema ≥ 90, accessibility ≥ 95 on each (--assert); --expect compares the
# medians with a baseline (±3). One perf run at a time on this laptop: it runs under the perf lock (tools/perf_lock.cjs),
# serves the build with tools/serve.py on the package's own port and asserts X-Served-By before the first run.
#
#   bash tools/lh_gate.sh --out out [--port 8111] [--name w1-p1] [--runs 5] [--now 2026-09-26T22:56]
#                         [--film heart-of-the-beast] [--cinema dubai/reel-dubai-mall] [--pages home,film,cinema]
#                         [--assert] [--expect home=96,film=97] [--json FILE] [--posters DIR]
#
# Lighthouse: the `lighthouse` CLI on PATH (npm i -g lighthouse; 13.5 on this laptop), its default mobile emulation and
# simulated throttling, headless Chrome. --now adds ?now= to every URL (the page's own UAE clock), so a build from
# another day's data is measured as that day's evening, not as a page whose every show has passed.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
OUT="$ROOT/out"; PORT=8111; NAME="${CINEMA_PKG:-w1-p1}"; RUNS=5; NOW=""; FILM="heart-of-the-beast"; CINEMA="dubai/reel-dubai-mall"
PAGES="home,film,cinema"; ASSERT=0; EXPECT=""; JSON=""; POSTERS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2;; --port) PORT="$2"; shift 2;; --name) NAME="$2"; shift 2;; --runs) RUNS="$2"; shift 2;;
    --now) NOW="$2"; shift 2;; --film) FILM="$2"; shift 2;; --cinema) CINEMA="$2"; shift 2;; --pages) PAGES="$2"; shift 2;;
    --assert) ASSERT=1; shift;; --expect) EXPECT="$2"; shift 2;; --json) JSON="$2"; shift 2;; --posters) POSTERS="$2"; shift 2;;
    *) echo "unknown argument $1" >&2; exit 2;;
  esac
done

# one perf run at a time: re-run this script under the lock unless it already holds it
if [ -z "${CINEMA_PERF_LOCK_HELD:-}" ]; then
  SELF_BASH="$BASH"; command -v cygpath >/dev/null 2>&1 && SELF_BASH="$(cygpath -w "$BASH")"   # node spawns it: a Windows path there
  exec node "$HERE/perf_lock.cjs" run --pkg "$NAME" -- "$SELF_BASH" "$0" --out "$OUT" --port "$PORT" --name "$NAME" --runs "$RUNS" \
    ${NOW:+--now "$NOW"} --film "$FILM" --cinema "$CINEMA" --pages "$PAGES" $([ "$ASSERT" = 1 ] && echo --assert) ${EXPECT:+--expect "$EXPECT"} ${JSON:+--json "$JSON"} \
    ${POSTERS:+--posters "$POSTERS"}
fi

TMP="$(mktemp -d)"
python "$HERE/serve.py" --out "$OUT" --port "$PORT" --name "$NAME" ${POSTERS:+--posters "$POSTERS"} > "$TMP/serve.log" 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null; rm -rf "$TMP"' EXIT
for _ in $(seq 1 100); do grep -q serving "$TMP/serve.log" 2>/dev/null && break; kill -0 $SRV 2>/dev/null || break; sleep 0.2; done
if ! grep -q serving "$TMP/serve.log"; then echo "FAIL the server did not start: $(cat "$TMP/serve.log")"; exit 1; fi
STAMP="$(sed -n 's/.* as \([^ ]*\).*/\1/p' "$TMP/serve.log" | head -1)"
BASE="http://127.0.0.1:$PORT"
for u in "$BASE/" "$BASE/assets/cinema.css"; do
  got="$(curl -s -o /dev/null -D - "$u" | tr -d '\r' | sed -n 's/^[Xx]-[Ss]erved-[Bb]y: //p')"
  if [ "$got" != "$STAMP" ]; then echo "FAIL X-Served-By on $u is '$got', not '$STAMP': another server answered, nothing measured"; exit 1; fi
done
echo "PASS X-Served-By $STAMP on the document and an asset"

Q=""; [ -n "$NOW" ] && Q="?now=$NOW"
declare -A URL=( [home]="$BASE/$Q" [film]="$BASE/film/$FILM/$Q" [cinema]="$BASE/$CINEMA/$Q" )
IFS=',' read -ra LIST <<< "$PAGES"
for key in "${LIST[@]}"; do
  for i in $(seq 1 "$RUNS"); do
    lighthouse "${URL[$key]}" --quiet --only-categories=performance,accessibility --output=json --output-path="$TMP/lh-$key-$i.json" \
      --chrome-flags="--headless=new --no-first-run --no-default-browser-check" --max-wait-for-load=60000 >/dev/null 2>"$TMP/lh-$key-$i.err"
    # on Windows Lighthouse often exits 1 after writing its report (it can't delete Chrome's temp profile): only a
    # missing report is a failed run
    [ -s "$TMP/lh-$key-$i.json" ] || echo "INFO lighthouse run $key $i wrote no report: $(tail -2 "$TMP/lh-$key-$i.err")"
  done
done

node - "$TMP" "$PAGES" "$RUNS" "$ASSERT" "$EXPECT" "$JSON" "$FILM" "$CINEMA" <<'EOF'
const fs = require("fs"), path = require("path");
const [tmp, pages, runs, assert, expect, json, film, cinema] = process.argv.slice(2);
const GATE = { home: 92, film: 92, cinema: 90 }, A11Y = 95;
const exp = Object.fromEntries((expect || "").split(",").filter(Boolean).map((x) => x.split("=")).map(([k, v]) => [k, +v]));
const med = (a) => { const s = a.filter((x) => x != null).sort((p, q) => p - q); return s.length ? s[Math.floor(s.length / 2)] : null; };
let fail = 0; const out = {};
for (const key of pages.split(",")) {
  const rs = [];
  for (let i = 1; i <= +runs; i++) {
    try {
      const j = JSON.parse(fs.readFileSync(path.join(tmp, `lh-${key}-${i}.json`), "utf-8")), a = j.audits;
      rs.push({ perf: Math.round(j.categories.performance.score * 100), a11y: Math.round(j.categories.accessibility.score * 100),
        lcp: a["largest-contentful-paint"].numericValue, tbt: a["total-blocking-time"].numericValue, cls: a["cumulative-layout-shift"].numericValue });
    } catch (e) { rs.push(null); }
  }
  const ok = rs.filter(Boolean);
  const m = { runs: rs.map((r) => (r ? r.perf : null)), perf: med(ok.map((r) => r.perf)), a11y: med(ok.map((r) => r.a11y)),
    lcp: med(ok.map((r) => r.lcp)), tbt: med(ok.map((r) => r.tbt)), cls: med(ok.map((r) => r.cls)) };
  out[key] = m;
  const label = `${key}${key === "film" ? " (" + film + ")" : key === "cinema" ? " (" + cinema + ")" : ""}: performance median ${m.perf} (${m.runs.join("/")}), accessibility ${m.a11y}, LCP ${(m.lcp / 1000).toFixed(2)} s, TBT ${Math.round(m.tbt)} ms, CLS ${m.cls != null ? m.cls.toFixed(3) : "n/a"}`;
  if (assert === "1") {
    const pass = m.perf != null && m.perf >= GATE[key] && m.a11y >= A11Y;
    console.log((pass ? "PASS " : "FAIL ") + label + ` (gate ≥ ${GATE[key]}, a11y ≥ ${A11Y})`); if (!pass) fail = 1;
  } else console.log("INFO " + label);
  if (exp[key] != null) {
    const pass = m.perf != null && Math.abs(m.perf - exp[key]) <= 3;
    console.log((pass ? "PASS " : "FAIL ") + `${key} reproduces its baseline ${exp[key]} ±3 (median ${m.perf})`); if (!pass) fail = 1;
  }
}
if (json) fs.writeFileSync(json, JSON.stringify(out, null, 1));
process.exit(fail);
EOF
